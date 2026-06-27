from typing import Any

from agent.state import AgentState
from agent.tool_registry import TOOL_SPECS


def validate_tools(state: AgentState) -> AgentState:
    validated: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for call in state.get("planned_tools", []):
        name = call.get("name")
        args = dict(call.get("args") or {})
        if name not in TOOL_SPECS:
            errors.append({"tool": name, "error": "Tool không được phép hoặc không tồn tại."})
            continue

        if name in {"get_patient_profile", "get_patient_diagnosis_history"} and not args.get("patient_id"):
            args["patient_id"] = state.get("patient_id")
        if name == "get_image_analysis" and not args.get("image_id"):
            args["image_id"] = state.get("image_id")
        image_id_value = args.get("image_id")
        if name == "get_image_analysis" and image_id_value is not None and image_id_value != "":
            try:
                args["image_id"] = int(args["image_id"])
            except Exception:
                errors.append(
                    {
                        "tool": name,
                        "error": "image_id không hợp lệ.",
                        "invalid_args": {"image_id": args.get("image_id")},
                    }
                )
                continue

        missing = []
        for key in TOOL_SPECS[name]["required_args"]:
            value = args.get(key)
            if value is None or value == "":
                missing.append(key)
        if missing:
            errors.append(
                {
                    "tool": name,
                    "error": "Thiếu tham số bắt buộc.",
                    "missing_args": missing,
                }
            )
            continue

        validated.append({"name": name, "args": args})

    state["validated_tools"] = validated
    state["tool_errors"] = errors
    return state
