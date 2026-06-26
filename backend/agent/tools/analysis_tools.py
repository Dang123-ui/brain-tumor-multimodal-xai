from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from agent.tools.patient_tools import serialize_analysis_with_visuals


def get_image_analysis(db: Session, image_id: Optional[int]) -> dict[str, Any]:
    if not image_id:
        return {"found": False, "analysis": None}

    image = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not image:
        return {"found": False, "analysis": None, "error": "image_not_found"}

    analysis = (
        db.query(models.AnalysisResult)
        .filter(models.AnalysisResult.image_id == image_id)
        .first()
    )

    return {
        "found": bool(analysis),
        "image": {
            "id": image.id,
            "patient_id": image.patient_id,
            "modality": image.modality,
            "scan_date": image.scan_date.isoformat() if image.scan_date else None,
            "is_series": image.is_series,
            "num_slices": image.num_slices,
        },
        "analysis": serialize_analysis_with_visuals(db, analysis),
    }
