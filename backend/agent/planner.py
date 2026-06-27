import json
import re
from typing import Any

from agent.llm import get_agent_model
from agent.state import AgentState
from agent.tool_registry import get_tool_catalog


PLANNER_SYSTEM_PROMPT = """Bạn là Planner của NeuroDiagnosis Agent.

Nhiệm vụ: quyết định câu hỏi của bác sĩ cần gọi tool dữ liệu hay chỉ trả lời kiến thức chung.

Quy tắc:
- patient_id/image_id/current_page chỉ là ngữ cảnh, không bắt buộc gọi tool.
- Chỉ gọi tool bệnh nhân khi câu hỏi nhắc tới bệnh nhân này, hồ sơ, bệnh án, lịch sử, chẩn đoán, kết quả, risk, confidence.
- Chỉ gọi get_image_analysis khi câu hỏi nhắc tới ảnh này/kết quả ảnh/mask/bbox/contour/heatmap và có image_id.
- Nếu hỏi kiến thức chung như "Finer-CAM là gì?", không gọi tool.
- Nếu cần tool nhưng thiếu patient_id/image_id, vẫn plan tool đó với args rỗng để bước Validate hỏi lại.
- Trả về JSON thuần, không markdown.
"""


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content)


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


def _fallback_plan(state: AgentState, error: str | None = None) -> dict[str, Any]:
    message = (state.get("message") or "").lower()
    tool_calls: list[dict[str, Any]] = []
    answer_mode = "general_knowledge"

    if any(k in message for k in ["bệnh án", "benh an", "hồ sơ", "ho so", "bệnh nhân này", "benh nhan nay", "lịch sử", "lich su", "tóm tắt", "tom tat"]):
        answer_mode = "patient_context"
        tool_calls = [
            {"name": "get_patient_profile", "args": {"patient_id": state.get("patient_id")}},
            {"name": "get_patient_diagnosis_history", "args": {"patient_id": state.get("patient_id")}},
        ]
    elif any(k in message for k in ["ảnh này", "anh nay", "bbox", "mask", "contour", "heatmap", "kết quả ảnh", "ket qua anh"]):
        answer_mode = "image_context"
        tool_calls = [{"name": "get_image_analysis", "args": {"image_id": state.get("image_id")}}]
    elif any(k in message for k in ["thông báo", "notification", "cảnh báo", "canh bao", "review"]):
        answer_mode = "notification"
        tool_calls = [{"name": "get_notifications", "args": {}}]

    return {
        "answer_mode": answer_mode,
        "reason": error or "Fallback planner rule.",
        "tool_calls": tool_calls,
    }


def plan_tools(state: AgentState) -> AgentState:
    payload = {
        "message": state.get("message"),
        "current_page": state.get("current_page"),
        "patient_id": state.get("patient_id"),
        "image_id": state.get("image_id"),
        "selected_region": state.get("selected_region"),
        "available_tools": get_tool_catalog(),
    }
    prompt = (
        "Hãy lập kế hoạch tool cho request sau.\n"
        "Schema JSON bắt buộc:\n"
        "{\n"
        '  "answer_mode": "general_knowledge|patient_context|image_context|notification|quick_mri|other",\n'
        '  "reason": "lý do ngắn",\n'
        '  "tool_calls": [{"name": "tool_name", "args": {}}]\n'
        "}\n\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
    try:
        model = get_agent_model()
        response = model.invoke([("system", PLANNER_SYSTEM_PROMPT), ("human", prompt)])
        plan = _parse_json(_content_to_text(getattr(response, "content", response)))
    except Exception as exc:
        plan = _fallback_plan(state, error=f"Planner LLM fallback: {exc}")

    if not isinstance(plan.get("tool_calls"), list):
        plan["tool_calls"] = []
    state["planned_tools"] = plan.get("tool_calls") or []
    state["answer_mode"] = plan.get("answer_mode") or "general_knowledge"
    state["intent"] = state["answer_mode"]
    state["planner_reason"] = plan.get("reason")
    return state
