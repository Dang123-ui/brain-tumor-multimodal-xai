import re
from typing import Any, Optional

from sqlalchemy.orm import Session

import crud
import models


def _stored_data_url(path: str | None) -> str | None:
    if not path:
        return None
    try:
        from routers.analysis import _stored_image_to_data_url

        return _stored_image_to_data_url(path)
    except Exception:
        return None


def _latest_task(db: Session, task_type: str, target_id: int) -> Optional[models.InferenceTask]:
    return (
        db.query(models.InferenceTask)
        .filter(
            models.InferenceTask.task_type == task_type,
            models.InferenceTask.target_id == target_id,
        )
        .order_by(models.InferenceTask.created_at.desc())
        .first()
    )


def _task_id_from_analysis_paths(analysis: models.AnalysisResult) -> int | None:
    for path in (
        analysis.mask_path,
        analysis.odam_path,
        analysis.seg_eigen_cam_path,
        analysis.finer_cam_path,
        analysis.gradcam_path,
        analysis.xai_3_panel_path,
    ):
        if not path:
            continue
        match = re.search(r"/task-(\d+)/", path)
        if match:
            return int(match.group(1))
    return None


def _matching_prognosis_task(
    db: Session,
    analysis: models.AnalysisResult,
) -> Optional[models.InferenceTask]:
    task_id = _task_id_from_analysis_paths(analysis)
    tasks = (
        db.query(models.InferenceTask)
        .filter(
            models.InferenceTask.task_type == "prognosis",
            models.InferenceTask.target_id == analysis.patient_id,
        )
        .order_by(models.InferenceTask.created_at.desc())
        .all()
    )

    for task in tasks:
        if task_id and task.id == task_id:
            return task

    for task in tasks:
        result = task.result if isinstance(task.result, dict) else {}
        for key in ("image_id", "mri_image_id", "source_image_id", "target_image_id"):
            if str(result.get(key)) == str(analysis.image_id):
                return task

    return None


def _fallback_segmentation_overlays(
    image: models.Image | None,
    bbox: list[int] | None,
    seg_mask_path: str | None,
) -> tuple[str | None, str | None]:
    if not image or not bbox or not seg_mask_path:
        return None, None
    try:
        from routers.analysis import _build_segmentation_overlays, _load_image_from_minio

        return _build_segmentation_overlays(
            original_image_bgr=_load_image_from_minio(image.file_path),
            bbox=bbox,
            seg_mask_path=seg_mask_path,
        )
    except Exception:
        return None, None


def resolve_patient(db: Session, patient_id: Optional[str]) -> Optional[models.Patient]:
    if not patient_id:
        return None
    return crud.get_patient_by_id_or_external(db, patient_id)


def serialize_patient(patient: Optional[models.Patient]) -> Optional[dict[str, Any]]:
    if not patient:
        return None
    return {
        "id": patient.id,
        "patient_external_id": patient.patient_external_id,
        "name": patient.name,
        "age": patient.age,
        "gender": patient.gender,
    }


def get_patient_profile(db: Session, patient_id: Optional[str]) -> dict[str, Any]:
    patient = resolve_patient(db, patient_id)
    if not patient:
        return {"found": False, "patient": None}

    images = (
        db.query(models.Image)
        .filter(models.Image.patient_id == patient.id)
        .order_by(models.Image.scan_date.desc())
        .limit(10)
        .all()
    )
    latest_analysis = (
        db.query(models.AnalysisResult)
        .filter(models.AnalysisResult.patient_id == patient.id)
        .order_by(models.AnalysisResult.created_at.desc())
        .first()
    )

    return {
        "found": True,
        "patient": serialize_patient(patient),
        "image_count": len(patient.images or []),
        "recent_images": [
            {
                "id": image.id,
                "modality": image.modality,
                "scan_date": image.scan_date.isoformat() if image.scan_date else None,
                "is_series": image.is_series,
                "num_slices": image.num_slices,
            }
            for image in images
        ],
        "latest_analysis": serialize_analysis_with_visuals(db, latest_analysis),
    }


def serialize_analysis(analysis: Optional[models.AnalysisResult]) -> Optional[dict[str, Any]]:
    if not analysis:
        return None
    return {
        "image_id": analysis.image_id,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "no_tumor_detected": analysis.no_tumor_detected,
        "tumor_label": analysis.tumor_label,
        "classification_confidence": analysis.classification_confidence,
        "risk_score": analysis.risk_score,
        "risk_group": analysis.risk_group,
    }


def serialize_analysis_with_visuals(
    db: Session,
    analysis: Optional[models.AnalysisResult],
) -> Optional[dict[str, Any]]:
    item = serialize_analysis(analysis)
    if not item or not analysis:
        return item

    image = db.query(models.Image).filter(models.Image.id == analysis.image_id).first()
    mri_task = _latest_task(db, "mri_pipeline", analysis.image_id)
    prognosis_task = _matching_prognosis_task(db, analysis)
    payload: dict[str, Any] = {}
    if mri_task and isinstance(mri_task.result, dict):
        payload.update(mri_task.result)
    if prognosis_task and isinstance(prognosis_task.result, dict):
        for key in (
            "bbox",
            "bbox_confidence",
            "original_image_path",
            "bbox_image_path",
            "seg_mask_path",
            "mask_overlay_path",
            "contour_overlay_path",
            "risk_score",
            "risk_group",
            "survival_curve_data",
            "multimodal_risk_xai_path",
            "gradcam_heatmap_path",
        ):
            if key in prognosis_task.result and not payload.get(key):
                payload[key] = prognosis_task.result[key]

    bbox = payload.get("bbox")
    seg_mask_path = payload.get("seg_mask_path") or analysis.mask_path
    mask_overlay = _stored_data_url(payload.get("mask_overlay_path"))
    contour_overlay = _stored_data_url(payload.get("contour_overlay_path"))
    if mask_overlay is None or contour_overlay is None:
        fallback_mask, fallback_contour = _fallback_segmentation_overlays(
            image=image,
            bbox=bbox,
            seg_mask_path=seg_mask_path,
        )
        mask_overlay = mask_overlay or fallback_mask
        contour_overlay = contour_overlay or fallback_contour

    visuals = [
        {"label": "Detection (BBox)", "url": _stored_data_url(payload.get("bbox_image_path"))},
        {"label": "Segmentation (Mask)", "url": mask_overlay},
        {"label": "Tumor contour", "url": contour_overlay},
    ]

    item["scan_date"] = image.scan_date.isoformat() if image and image.scan_date else item.get("created_at")
    item["modality"] = image.modality if image else None
    item["bbox"] = bbox
    item["bbox_confidence"] = payload.get("bbox_confidence")
    item["risk_score"] = None if item.get("no_tumor_detected") else (payload.get("risk_score") if payload.get("risk_score") is not None else item.get("risk_score"))
    item["risk_group"] = None if item.get("no_tumor_detected") else (payload.get("risk_group") or item.get("risk_group"))
    item["visuals"] = [visual for visual in visuals if visual.get("url")]
    item["has_visuals"] = bool(item["visuals"])
    return item


def get_patient_diagnosis_history(db: Session, patient_id: Optional[str]) -> dict[str, Any]:
    patient = resolve_patient(db, patient_id)
    if not patient:
        return {"found": False, "patient": None, "items": []}

    results = (
        db.query(models.AnalysisResult)
        .filter(models.AnalysisResult.patient_id == patient.id)
        .order_by(models.AnalysisResult.created_at.desc())
        .all()
    )

    return {
        "found": True,
        "patient": serialize_patient(patient),
        "items": [serialize_analysis_with_visuals(db, result) for result in results],
    }
