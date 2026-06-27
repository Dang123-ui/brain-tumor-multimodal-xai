from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    current_page: Optional[str] = None
    patient_id: Optional[str] = None
    image_id: Optional[int] = None
    selected_region: Optional[dict[str, Any]] = None


class AgentChatResponse(BaseModel):
    thread_id: str
    message: str
    intent: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)


class AgentConversationResponse(BaseModel):
    thread_id: str
    patient_id: Optional[int] = None
    image_id: Optional[int] = None
    title: Optional[str] = None
    status: str = "active"
    summary: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgentMessageResponse(BaseModel):
    id: int
    thread_id: str
    role: str
    content: Optional[str] = None
    message_type: str = "text"
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime
