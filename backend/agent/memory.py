from typing import Any, Optional

from sqlalchemy.orm import Session

import models


def get_or_create_conversation(
    db: Session,
    *,
    thread_id: str,
    user_id: Optional[int],
    patient_id: Optional[int] = None,
    image_id: Optional[int] = None,
) -> models.AgentConversation:
    conversation = (
        db.query(models.AgentConversation)
        .filter(models.AgentConversation.thread_id == thread_id)
        .first()
    )
    if conversation:
        changed = False
        if patient_id and not conversation.patient_id:
            conversation.patient_id = patient_id
            changed = True
        if image_id and not conversation.image_id:
            conversation.image_id = image_id
            changed = True
        if changed:
            db.commit()
            db.refresh(conversation)
        return conversation

    conversation = models.AgentConversation(
        thread_id=thread_id,
        user_id=user_id,
        patient_id=patient_id,
        image_id=image_id,
        status="active",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def save_message(
    db: Session,
    *,
    thread_id: str,
    user_id: Optional[int],
    role: str,
    content: str,
    message_type: str = "text",
    metadata: Optional[dict[str, Any]] = None,
) -> models.AgentMessage:
    message = models.AgentMessage(
        thread_id=thread_id,
        user_id=user_id,
        role=role,
        content=content,
        message_type=message_type,
        metadata_json=metadata,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def load_recent_messages(db: Session, thread_id: str, limit: int = 12) -> list[dict[str, Any]]:
    rows = (
        db.query(models.AgentMessage)
        .filter(
            models.AgentMessage.thread_id == thread_id,
            models.AgentMessage.deleted_at.is_(None),
        )
        .order_by(models.AgentMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "role": row.role,
            "content": row.content,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "metadata": row.metadata_json,
        }
        for row in reversed(rows)
    ]

