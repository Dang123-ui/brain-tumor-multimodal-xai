from typing import Any, Optional

from sqlalchemy.orm import Session

import crud
import models


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
        "latest_analysis": serialize_analysis(latest_analysis),
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
        "items": [serialize_analysis(result) for result in results],
    }

