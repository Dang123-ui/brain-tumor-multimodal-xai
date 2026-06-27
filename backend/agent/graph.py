import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from agent.checkpoint import (
    get_postgres_checkpointer,
    get_postgres_store,
    retrieve_long_memory,
    save_long_memory,
)
from agent.executor import make_execute_tools
from agent.llm import get_agent_model
from agent.memory import (
    get_or_create_conversation,
    load_recent_messages,
    save_audit_log,
    save_message,
)
from agent.planner import plan_tools
from agent.state import AgentState
from agent.tools.patient_tools import resolve_patient
from agent.validator import validate_tools


SYSTEM_PROMPT = """Bạn là NeuroDiagnosis Agent trong hệ thống NeuroDiagnosis AI.

Nguyên tắc bắt buộc:
- Trả lời bằng tiếng Việt tự nhiên, ngắn gọn, rõ ý.
- Không bịa dữ liệu bệnh nhân. Nếu tool không trả dữ liệu thì nói là chưa có dữ liệu.
- Không tự đưa chẩn đoán cuối cùng thay bác sĩ.
- Không tự chỉnh nhãn nếu chưa có xác nhận của bác sĩ.
- Luôn phân biệt AI label, expert label, final label và review status nếu có.
- Nếu no_tumor_detected = true thì không nói risk score như một kết quả hợp lệ.
- Heatmap/XAI giải thích hành vi mô hình, không phải bằng chứng mô bệnh học.
"""


def _safe_user_id(current_user: dict[str, Any]) -> int | None:
    raw = current_user.get("user_id") or current_user.get("sub") or current_user.get("id")
    try:
        return int(raw)
    except Exception:
        return None


def _long_memory_namespace(user_id: int | None) -> tuple[str, ...]:
    return ("neurodiagnosis_agent", "user", str(user_id or "anonymous"))


def _serialize_store_items(items: list[Any]) -> list[dict[str, Any]]:
    serialized = []
    for item in items:
        serialized.append(
            {
                "namespace": list(getattr(item, "namespace", []) or []),
                "key": getattr(item, "key", None),
                "value": getattr(item, "value", None),
                "score": getattr(item, "score", None),
            }
        )
    return serialized


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
    if isinstance(content, dict):
        text = content.get("text") or content.get("content")
        return str(text if text is not None else content)
    return str(content)


def _strip_visual_data(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key == "url" and isinstance(item, str) and item.startswith("data:image/"):
                cleaned[key] = "[image_data_url omitted]"
            else:
                cleaned[key] = _strip_visual_data(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_visual_data(item) for item in value]
    return value


def _make_generate_response(db: Session):
    def _generate_response(state: AgentState) -> AgentState:
        thread_id = state["thread_id"]
        recent_messages = load_recent_messages(db, thread_id, limit=10)
        long_memory = _serialize_store_items(
            retrieve_long_memory(_long_memory_namespace(state.get("user_id")), limit=5)
        )
        state["long_memory"] = long_memory
        context_payload = {
            "answer_mode": state.get("answer_mode"),
            "planner_reason": state.get("planner_reason"),
            "intent": state.get("intent"),
            "current_page": state.get("current_page"),
            "patient_id": state.get("patient_id"),
            "image_id": state.get("image_id"),
            "selected_region": state.get("selected_region"),
            "planned_tools": state.get("planned_tools", []),
            "validated_tools": state.get("validated_tools", []),
            "tool_errors": state.get("tool_errors", []),
            "tool_results": _strip_visual_data(state.get("tool_results", {})),
            "recent_messages": recent_messages,
            "long_memory": long_memory,
        }

        prompt = (
            f"Tin nhắn bác sĩ: {state.get('message')}\n\n"
            "Dữ liệu tool/context JSON:\n"
            f"{json.dumps(context_payload, ensure_ascii=False, default=str)}\n\n"
            "Hãy trả lời Markdown đẹp, ngắn gọn, dựa trên dữ liệu tool nếu có. "
            "Nếu tool_errors báo thiếu patient_id/image_id, hãy hỏi lại bác sĩ cần chọn bệnh nhân/ảnh nào. "
            "Nếu không có tool_results vì câu hỏi là kiến thức chung, trả lời kiến thức chung. "
            "Không bịa dữ liệu bệnh nhân."
        )

        try:
            model = get_agent_model()
            response = model.invoke(
                [
                    ("system", SYSTEM_PROMPT),
                    ("human", prompt),
                ]
            )
            content = _content_to_text(getattr(response, "content", response))
        except Exception as exc:
            content = (
                "Agent LLM chưa sẵn sàng. "
                f"Lỗi cấu hình hoặc dependency: {exc}. "
                "Tuy nhiên tool context đã được nạp, hãy kiểm tra GOOGLE_API_KEY/GEMINI_API_KEY và backend requirements."
            )

        state["final_response"] = content
        return state

    return _generate_response


def _build_graph(db: Session):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("Missing dependency langgraph. Rebuild/install backend requirements.") from exc

    graph = StateGraph(AgentState)
    graph.add_node("plan_tools", plan_tools)
    graph.add_node("validate_tools", validate_tools)
    graph.add_node("execute_tools", make_execute_tools(db))
    graph.add_node("generate_response", _make_generate_response(db))
    graph.add_edge(START, "plan_tools")
    graph.add_edge("plan_tools", "validate_tools")
    graph.add_edge("validate_tools", "execute_tools")
    graph.add_edge("execute_tools", "generate_response")
    graph.add_edge("generate_response", END)

    checkpointer = get_postgres_checkpointer()
    store = get_postgres_store()
    return graph.compile(checkpointer=checkpointer, store=store)


def get_agent_graph(db: Session):
    return _build_graph(db)


def run_agent(
    *,
    db: Session,
    current_user: dict[str, Any],
    message: str,
    thread_id: str | None = None,
    current_page: str | None = None,
    patient_id: str | None = None,
    image_id: int | None = None,
    selected_region: dict[str, Any] | None = None,
) -> AgentState:
    resolved_thread_id = thread_id or str(uuid.uuid4())
    user_id = _safe_user_id(current_user)
    patient = resolve_patient(db, patient_id)
    get_or_create_conversation(
        db,
        thread_id=resolved_thread_id,
        user_id=user_id,
        patient_id=patient.id if patient else None,
        image_id=image_id,
    )
    save_message(
        db,
        thread_id=resolved_thread_id,
        user_id=user_id,
        role="user",
        content=message,
        metadata={
            "current_page": current_page,
            "patient_id": patient_id,
            "image_id": image_id,
            "selected_region": selected_region,
        },
    )

    initial_state: AgentState = {
        "thread_id": resolved_thread_id,
        "user_id": user_id,
        "role": current_user.get("role"),
        "current_page": current_page,
        "patient_id": patient_id,
        "image_id": image_id,
        "selected_region": selected_region,
        "message": message,
        "actions": [],
        "tool_results": {},
    }
    result: AgentState = get_agent_graph(db).invoke(
        initial_state,
        config={"configurable": {"thread_id": resolved_thread_id}},
    )

    save_message(
        db,
        thread_id=resolved_thread_id,
        user_id=user_id,
        role="assistant",
        content=result.get("final_response") or "",
        metadata={"intent": result.get("intent"), "tool_results": result.get("tool_results")},
    )
    try:
        save_audit_log(
            db,
            user_id=user_id,
            patient_id=patient.id if patient else None,
            image_id=image_id,
            thread_id=resolved_thread_id,
            action="agent_chat",
            tool_name=result.get("intent"),
            metadata={
                "message": message,
                "current_page": current_page,
                "actions": result.get("actions") or [],
                "planned_tools": result.get("planned_tools") or [],
                "validated_tools": result.get("validated_tools") or [],
                "has_selected_region": bool(selected_region),
            },
        )
    except Exception as exc:
        print(f"[AGENT] Audit log skipped: {exc}")
    save_long_memory(
        _long_memory_namespace(user_id),
        f"{resolved_thread_id}:{uuid.uuid4().hex[:8]}",
        {
            "thread_id": resolved_thread_id,
            "patient_id": patient_id,
            "image_id": image_id,
            "intent": result.get("intent"),
            "planner_reason": result.get("planner_reason"),
            "user_message": message[:1000],
            "assistant_message": (result.get("final_response") or "")[:1000],
        },
    )
    return result
