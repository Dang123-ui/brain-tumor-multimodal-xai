from typing import Any

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


def get_notifications(db: Session) -> dict[str, Any]:
    low_confidence = (
        db.query(models.AnalysisResult)
        .filter(
            models.AnalysisResult.no_tumor_detected.is_(False),
            models.AnalysisResult.classification_confidence.isnot(None),
            models.AnalysisResult.classification_confidence < 0.95,
        )
        .count()
    )
    stale_risk = (
        db.query(models.AnalysisResult)
        .filter(
            models.AnalysisResult.no_tumor_detected.is_(True),
            models.AnalysisResult.risk_score.isnot(None),
        )
        .count()
    )

    items = []
    if low_confidence:
        items.append({"type": "review_required", "message": f"Có {low_confidence} ca confidence thấp cần review."})
    if stale_risk:
        items.append({"type": "stale_risk", "message": f"Có {stale_risk} ca không phát hiện u nhưng vẫn có risk score."})
    return {"items": items}


def execute_registered_tool(db: Session, name: str, args: dict[str, Any]) -> Any:
    if name == "get_patient_profile":
        return get_patient_profile(db, args.get("patient_id"))
    if name == "get_patient_diagnosis_history":
        return get_patient_diagnosis_history(db, args.get("patient_id"))
    if name == "get_image_analysis":
        return get_image_analysis(db, args.get("image_id"))
    if name == "get_notifications":
        return get_notifications(db)
    raise ValueError(f"Tool không được hỗ trợ: {name}")
