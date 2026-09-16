from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

import models


def _clinical_summary(db: Session, post: models.NeuroPost) -> dict[str, Any] | None:
    if post.post_type != "clinical_case" or post.image_id is None:
        return None

    analysis = (
        db.query(models.AnalysisResult)
        .filter(models.AnalysisResult.image_id == post.image_id)
        .first()
    )
    if analysis is None:
        return {
            "image_id": post.image_id,
            "ai_label": None,
            "confidence": None,
            "risk_score": None,
            "risk_group": None,
            "no_tumor_detected": False,
        }

    return {
        "image_id": post.image_id,
        "ai_label": analysis.tumor_label,
        "confidence": analysis.classification_confidence,
        "risk_score": analysis.risk_score,
        "risk_group": analysis.risk_group,
        "no_tumor_detected": bool(analysis.no_tumor_detected),
    }


def serialize_post(
    db: Session,
    post: models.NeuroPost,
    viewer_user_id: int,
) -> dict[str, Any]:
    """Serialize a post without leaking patient identity to non-authors."""
    author = db.query(models.User).filter(models.User.id == post.author_id).first()
    reaction_count = (
        db.query(func.count(models.NeuroPostReaction.id))
        .filter(models.NeuroPostReaction.post_id == post.id)
        .scalar()
        or 0
    )
    comment_count = (
        db.query(func.count(models.NeuroPostComment.id))
        .filter(
            models.NeuroPostComment.post_id == post.id,
            models.NeuroPostComment.deleted_at.is_(None),
        )
        .scalar()
        or 0
    )
    viewer_reaction = (
        db.query(models.NeuroPostReaction)
        .filter(
            models.NeuroPostReaction.post_id == post.id,
            models.NeuroPostReaction.user_id == viewer_user_id,
        )
        .first()
    )
    viewer_saved = (
        db.query(models.NeuroPostSave.id)
        .filter(
            models.NeuroPostSave.post_id == post.id,
            models.NeuroPostSave.user_id == viewer_user_id,
        )
        .first()
        is not None
    )

    payload: dict[str, Any] = {
        "id": post.id,
        "post_type": post.post_type,
        "content": post.content,
        "anonymous_case_code": post.anonymous_case_code,
        "author": {
            "id": author.id if author else post.author_id,
            "username": author.username if author else "unknown",
        },
        "is_owner": post.author_id == viewer_user_id,
        "clinical_summary": _clinical_summary(db, post),
        "attachments": [
            {
                "id": attachment.id,
                "object_path": attachment.object_path,
                "content_type": attachment.content_type,
                "original_name": attachment.original_name,
                "sort_order": attachment.sort_order,
            }
            for attachment in post.attachments
        ],
        "reaction_count": int(reaction_count),
        "comment_count": int(comment_count),
        "viewer_reaction": viewer_reaction.reaction_type if viewer_reaction else None,
        "viewer_saved": viewer_saved,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }

    if post.author_id == viewer_user_id and post.patient_id is not None:
        patient = db.query(models.Patient).filter(models.Patient.id == post.patient_id).first()
        payload.update(
            {
                "patient_id": post.patient_id,
                "patient_name": patient.name if patient else None,
                "patient_external_id": patient.patient_external_id if patient else None,
            }
        )

    return payload
