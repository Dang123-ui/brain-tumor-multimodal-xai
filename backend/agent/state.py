from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    thread_id: str
    user_id: Optional[int]
    role: Optional[str]
    patient_id: Optional[str]
    resolved_patient_id: Optional[int]
    image_id: Optional[int]
    selected_region: Optional[dict[str, Any]]
    message: str
    intent: str
    actions: list[dict[str, Any]]
    tool_results: dict[str, Any]
    long_memory: list[dict[str, Any]]
    final_response: str
    error: Optional[str]
