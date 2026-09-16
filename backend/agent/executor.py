from typing import Any

from sqlalchemy.orm import Session

from agent.state import AgentState
from agent.tool_registry import execute_registered_tool


def make_execute_tools(db: Session):
    def execute_tools(state: AgentState) -> AgentState:
        tool_results: dict[str, Any] = {}
        errors = list(state.get("tool_errors") or [])

        for call in state.get("validated_tools", []):
            name = call["name"]
            try:
                owner_user_id = None if state.get("role") in {"admin", "researcher"} else state.get("user_id")
                tool_results[name] = execute_registered_tool(
                    db,
                    name,
                    call.get("args") or {},
                    owner_user_id=owner_user_id,
                )
            except Exception as exc:
                errors.append({"tool": name, "error": str(exc)})

        state["tool_results"] = tool_results
        state["tool_errors"] = errors
        return state

    return execute_tools
