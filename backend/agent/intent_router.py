from agent.state import AgentState


INTENT_LABELS = {
    "patient_qa",
    "history_qa",
    "report_summary",
    "classification_xai",
    "human_review",
    "quick_mri",
    "multimodal_image_chat",
    "notification",
    "general",
}


def route_intent(state: AgentState) -> AgentState:
    """Phase 1 deterministic intent router.

    This is intentionally small and predictable. Later phases can replace this
    with an LLM classifier node while keeping the same state contract.
    """
    message = (state.get("message") or "").lower()
    intent = "general"

    if any(k in message for k in ["chẩn đoán", "chan doan", "mri", "pipeline", "upload ảnh"]):
        intent = "quick_mri"
    elif any(k in message for k in ["review", "xác nhận", "xac nhan", "chỉnh nhãn", "chinh nhan"]):
        intent = "human_review"
    elif any(k in message for k in ["finer-cam", "finer cam", "heatmap", "xai", "giải thích phân loại"]):
        intent = "classification_xai"
    elif any(k in message for k in ["lịch sử", "lich su", "timeline", "diễn tiến", "dien tien"]):
        intent = "history_qa"
    elif any(k in message for k in ["báo cáo", "bao cao", "tóm tắt", "tom tat"]):
        intent = "report_summary"
    elif any(k in message for k in ["thông báo", "notification", "nhắc", "canh bao", "cảnh báo"]):
        intent = "notification"
    elif state.get("patient_id"):
        intent = "patient_qa"

    state["intent"] = intent
    return state

