import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

import models


def title_from_message(message: str | None, max_length: int = 48) -> str | None:
    cleaned = " ".join((message or "").strip().split())
    if not cleaned:
        return None
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3].rstrip() + "..."


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
    conversation = (
        db.query(models.AgentConversation)
        .filter(models.AgentConversation.thread_id == thread_id)
        .first()
    )
    if conversation:
        conversation.updated_at = datetime.datetime.utcnow()
        if role == "user" and not conversation.title:
            conversation.title = title_from_message(content)
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


def list_conversations(db: Session, user_id: Optional[int], limit: int = 30) -> list[models.AgentConversation]:
    query = db.query(models.AgentConversation).filter(models.AgentConversation.deleted_at.is_(None))
    if user_id is not None:
        query = query.filter(models.AgentConversation.user_id == user_id)
    return query.order_by(models.AgentConversation.updated_at.desc()).limit(limit).all()


def get_conversation_by_thread(
    db: Session,
    thread_id: str,
    user_id: Optional[int] = None,
) -> models.AgentConversation | None:
    query = db.query(models.AgentConversation).filter(
        models.AgentConversation.thread_id == thread_id,
        models.AgentConversation.deleted_at.is_(None),
    )
    if user_id:
        query = query.filter(models.AgentConversation.user_id == user_id)
    return query.first()


def load_conversation_messages(
    db: Session,
    thread_id: str,
    limit: int = 100,
    user_id: Optional[int] = None,
) -> list[models.AgentMessage]:
    if not get_conversation_by_thread(db, thread_id, user_id=user_id):
        return []
    return (
        db.query(models.AgentMessage)
        .filter(
            models.AgentMessage.thread_id == thread_id,
            models.AgentMessage.deleted_at.is_(None),
        )
        .order_by(models.AgentMessage.created_at.asc())
        .limit(limit)
        .all()
    )


def soft_delete_conversation(db: Session, thread_id: str, user_id: Optional[int] = None) -> bool:
    now = datetime.datetime.utcnow()
    conversation = get_conversation_by_thread(db, thread_id, user_id=user_id)
    if not conversation:
        return False
    conversation.deleted_at = now
    (
        db.query(models.AgentMessage)
        .filter(models.AgentMessage.thread_id == thread_id)
        .update({"deleted_at": now}, synchronize_session=False)
    )
    db.commit()
    return True


def trim_messages(db: Session, thread_id: str, keep_last: int = 20) -> int:
    rows = (
        db.query(models.AgentMessage)
        .filter(
            models.AgentMessage.thread_id == thread_id,
            models.AgentMessage.deleted_at.is_(None),
        )
        .order_by(models.AgentMessage.created_at.desc())
        .all()
    )
    to_delete = rows[keep_last:]
    now = datetime.datetime.utcnow()
    for row in to_delete:
        row.deleted_at = now
    db.commit()
    return len(to_delete)


def update_conversation_summary(db: Session, thread_id: str, summary: str) -> bool:
    conversation = (
        db.query(models.AgentConversation)
        .filter(models.AgentConversation.thread_id == thread_id)
        .first()
    )
    if not conversation:
        return False
    conversation.summary = summary
    conversation.updated_at = datetime.datetime.utcnow()
    db.commit()
    return True


def save_audit_log(
    db: Session,
    *,
    user_id: Optional[int],
    patient_id: Optional[int] = None,
    image_id: Optional[int] = None,
    thread_id: Optional[str] = None,
    action: str,
    tool_name: Optional[str] = None,
    before_value: Optional[dict[str, Any]] = None,
    after_value: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> models.AgentAuditLog:
    row = models.AgentAuditLog(
        user_id=user_id,
        patient_id=patient_id,
        image_id=image_id,
        thread_id=thread_id,
        action=action,
        tool_name=tool_name,
        before_value=before_value,
        after_value=after_value,
        metadata_json=metadata,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
