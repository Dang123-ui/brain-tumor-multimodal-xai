from typing import Any

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

import models
from agent.tools.analysis_tools import get_image_analysis
from agent.tools.patient_tools import get_patient_diagnosis_history, get_patient_profile


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "get_patient_profile": {
        "description": "Lấy hồ sơ hành chính/lâm sàng tổng quan của một bệnh nhân.",
        "required_args": ["patient_id"],
    },
    "get_patient_diagnosis_history": {
        "description": "Lấy lịch sử các lần chẩn đoán MRI và kết quả theo thời gian của một bệnh nhân.",
        "required_args": ["patient_id"],
    },
    "get_image_analysis": {
        "description": "Lấy kết quả phân tích của một ảnh MRI cụ thể theo image_id.",
        "required_args": ["image_id"],
    },
    "get_notifications": {
        "description": "Lấy các cảnh báo/tác vụ cần bác sĩ xem xét trên toàn hệ thống.",
        "required_args": [],
    },
    "get_system_statistics": {
        "description": "Lấy thống kê tổng quan: bệnh nhân, ảnh, chẩn đoán, RNA và review.",
        "required_args": [],
    },
    "get_patient_statistics": {
        "description": "Thống kê bệnh nhân, gồm tổng số và số bệnh nhân từng có nhãn u cụ thể.",
        "required_args": [],
    },
    "get_diagnosis_statistics": {
        "description": "Thống kê chẩn đoán/analysis, phân biệt diagnosis count, image count và distinct patient count.",
        "required_args": [],
    },
    "get_review_statistics": {
        "description": "Thống kê review: low-confidence, pending doctor review và completed review.",
        "required_args": [],
    },
    "get_diagnoses_requiring_review": {
        "description": "Số chẩn đoán cần bác sĩ phân tích lại: confidence < threshold và chưa có review.",
        "required_args": [],
    },
}


def get_tool_catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "required_args": spec["required_args"],
        }
        for name, spec in TOOL_SPECS.items()
    ]


def get_notifications(db: Session, owner_user_id: int | None = None) -> dict[str, Any]:
    low_confidence_query = (
        db.query(models.AnalysisResult)
        .join(models.Patient, models.AnalysisResult.patient_id == models.Patient.id)
        .filter(
            models.AnalysisResult.no_tumor_detected.is_(False),
            models.AnalysisResult.classification_confidence.isnot(None),
            models.AnalysisResult.classification_confidence < 0.95,
        )
    )
    stale_risk_query = (
        db.query(models.AnalysisResult)
        .join(models.Patient, models.AnalysisResult.patient_id == models.Patient.id)
        .filter(
            models.AnalysisResult.no_tumor_detected.is_(True),
            models.AnalysisResult.risk_score.isnot(None),
        )
    )
    low_confidence = _patient_scope(low_confidence_query, owner_user_id).count()
    stale_risk = _patient_scope(stale_risk_query, owner_user_id).count()

    items = []
    if low_confidence:
        items.append({"type": "review_required", "message": f"Có {low_confidence} ca confidence thấp cần review."})
    if stale_risk:
        items.append({"type": "stale_risk", "message": f"Có {stale_risk} ca không phát hiện u nhưng vẫn có risk score."})
    return {"items": items}


def _patient_scope(query, owner_user_id: int | None):
    if owner_user_id is not None:
        return query.filter(models.Patient.owner_user_id == owner_user_id)
    return query


def _analysis_scope(query, owner_user_id: int | None):
    query = query.join(models.Patient, models.AnalysisResult.patient_id == models.Patient.id)
    return _patient_scope(query, owner_user_id)


def _label_filter(query, label: str | None):
    if not label:
        return query
    return query.filter(func.lower(models.AnalysisResult.tumor_label) == label.strip().lower())


def _latest_review_subquery(db: Session):
    return (
        db.query(
            models.ClassificationReview.image_id.label("image_id"),
            func.max(models.ClassificationReview.created_at).label("reviewed_at"),
        )
        .group_by(models.ClassificationReview.image_id)
        .subquery()
    )


def get_patient_statistics(
    db: Session,
    filters: dict[str, Any] | None = None,
    owner_user_id: int | None = None,
) -> dict[str, Any]:
    filters = filters or {}
    label = filters.get("label") or filters.get("tumor_label")
    total_patients = _patient_scope(db.query(models.Patient), owner_user_id).count()
    patients_with_rna = (
        _patient_scope(
            db.query(func.count(distinct(models.RnaData.patient_id))).join(
                models.Patient, models.RnaData.patient_id == models.Patient.id
            ),
            owner_user_id,
        ).scalar()
        or 0
    )
    patients_with_label = None
    if label:
        patients_with_label = (
            _label_filter(
                _analysis_scope(
                    db.query(func.count(distinct(models.AnalysisResult.patient_id))),
                    owner_user_id,
                ).filter(models.AnalysisResult.no_tumor_detected.is_(False)),
                label,
            ).scalar()
            or 0
        )
    return {
        "scope": "current_user" if owner_user_id is not None else "all",
        "total_patients": total_patients,
        "patients_with_rna": patients_with_rna,
        "label_filter": label,
        "patients_with_label": patients_with_label,
    }


def get_diagnosis_statistics(
    db: Session,
    filters: dict[str, Any] | None = None,
    owner_user_id: int | None = None,
) -> dict[str, Any]:
    filters = filters or {}
    label = filters.get("label") or filters.get("tumor_label")
    base = _analysis_scope(db.query(models.AnalysisResult), owner_user_id)
    label_rows = (
        _analysis_scope(
            db.query(models.AnalysisResult.tumor_label, func.count(models.AnalysisResult.id)),
            owner_user_id,
        )
        .filter(models.AnalysisResult.no_tumor_detected.is_(False))
        .group_by(models.AnalysisResult.tumor_label)
        .all()
    )
    diagnosis_count_for_label = None
    patient_count_for_label = None
    if label:
        diagnosis_count_for_label = (
            _label_filter(
                _analysis_scope(db.query(models.AnalysisResult), owner_user_id).filter(
                    models.AnalysisResult.no_tumor_detected.is_(False)
                ),
                label,
            ).count()
        )
        patient_count_for_label = (
            _label_filter(
                _analysis_scope(
                    db.query(func.count(distinct(models.AnalysisResult.patient_id))),
                    owner_user_id,
                ).filter(models.AnalysisResult.no_tumor_detected.is_(False)),
                label,
            ).scalar()
            or 0
        )
    return {
        "scope": "current_user" if owner_user_id is not None else "all",
        "total_diagnoses": base.count(),
        "total_images_with_analysis": _analysis_scope(
            db.query(func.count(distinct(models.AnalysisResult.image_id))),
            owner_user_id,
        ).scalar()
        or 0,
        "total_patients_with_diagnosis": _analysis_scope(
            db.query(func.count(distinct(models.AnalysisResult.patient_id))),
            owner_user_id,
        ).scalar()
        or 0,
        "no_tumor_diagnoses": base.filter(models.AnalysisResult.no_tumor_detected.is_(True)).count(),
        "label_counts": {label_name or "unknown": count for label_name, count in label_rows},
        "label_filter": label,
        "diagnosis_count_for_label": diagnosis_count_for_label,
        "patient_count_for_label": patient_count_for_label,
    }


def get_review_statistics(
    db: Session,
    filters: dict[str, Any] | None = None,
    owner_user_id: int | None = None,
) -> dict[str, Any]:
    filters = filters or {}
    threshold = float(filters.get("confidence_threshold") or 0.95)
    review_subq = _latest_review_subquery(db)
    low_confidence_query = (
        _analysis_scope(db.query(models.AnalysisResult), owner_user_id)
        .filter(
            models.AnalysisResult.no_tumor_detected.is_(False),
            models.AnalysisResult.classification_confidence.isnot(None),
            models.AnalysisResult.classification_confidence < threshold,
        )
    )
    pending_review_diagnoses = (
        low_confidence_query.outerjoin(review_subq, review_subq.c.image_id == models.AnalysisResult.image_id)
        .filter(review_subq.c.image_id.is_(None))
        .count()
    )
    completed_reviews = db.query(models.ClassificationReview).join(
        models.Patient, models.ClassificationReview.patient_id == models.Patient.id
    )
    return {
        "scope": "current_user" if owner_user_id is not None else "all",
        "confidence_threshold": threshold,
        "low_confidence_diagnoses": low_confidence_query.count(),
        "pending_doctor_review": pending_review_diagnoses,
        "completed_reviews": _patient_scope(completed_reviews, owner_user_id).count(),
        "definition": "pending_doctor_review = classification_confidence < threshold AND no completed classification review exists",
    }


def get_diagnoses_requiring_review(
    db: Session,
    confidence_threshold: float = 0.95,
    status: str = "pending",
    owner_user_id: int | None = None,
) -> dict[str, Any]:
    stats = get_review_statistics(
        db,
        {"confidence_threshold": confidence_threshold},
        owner_user_id=owner_user_id,
    )
    return {
        "count": stats["pending_doctor_review"] if status == "pending" else stats["low_confidence_diagnoses"],
        "status": status,
        "confidence_threshold": confidence_threshold,
        "low_confidence_diagnoses": stats["low_confidence_diagnoses"],
        "pending_doctor_review": stats["pending_doctor_review"],
        "definition": stats["definition"],
    }


def get_system_statistics(db: Session, owner_user_id: int | None = None) -> dict[str, Any]:
    return {
        "scope": "current_user" if owner_user_id is not None else "all",
        "patients": get_patient_statistics(db, owner_user_id=owner_user_id),
        "diagnoses": get_diagnosis_statistics(db, owner_user_id=owner_user_id),
        "review": get_review_statistics(db, owner_user_id=owner_user_id),
    }


def execute_registered_tool(
    db: Session,
    name: str,
    args: dict[str, Any],
    owner_user_id: int | None = None,
) -> Any:
    if name == "get_patient_profile":
        return get_patient_profile(db, args.get("patient_id"), owner_user_id=owner_user_id)
    if name == "get_patient_diagnosis_history":
        return get_patient_diagnosis_history(db, args.get("patient_id"), owner_user_id=owner_user_id)
    if name == "get_image_analysis":
        return get_image_analysis(db, args.get("image_id"), owner_user_id=owner_user_id)
    if name == "get_notifications":
        return get_notifications(db, owner_user_id=owner_user_id)
    if name == "get_system_statistics":
        return get_system_statistics(db, owner_user_id=owner_user_id)
    if name == "get_patient_statistics":
        return get_patient_statistics(db, args.get("filters"), owner_user_id=owner_user_id)
    if name == "get_diagnosis_statistics":
        return get_diagnosis_statistics(db, args.get("filters"), owner_user_id=owner_user_id)
    if name == "get_review_statistics":
        return get_review_statistics(db, args.get("filters"), owner_user_id=owner_user_id)
    if name == "get_diagnoses_requiring_review":
        return get_diagnoses_requiring_review(
            db,
            confidence_threshold=float(args.get("confidence_threshold") or 0.95),
            status=args.get("status") or "pending",
            owner_user_id=owner_user_id,
        )
    raise ValueError(f"Tool không được hỗ trợ: {name}")
