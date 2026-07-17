"""Tool-call normalization helpers for the status workflow."""

from __future__ import annotations

import json


def tool_result_succeeded(tool_result: str) -> bool:
    if tool_result.startswith("Error:") or tool_result.startswith("Error executing"):
        return False
    try:
        payload = json.loads(tool_result)
    except (TypeError, ValueError):
        return not tool_result.startswith("设置失败：")
    if isinstance(payload, dict) and isinstance(payload.get("ok"), bool):
        return bool(payload["ok"])
    return True


def normalize_tool_call(tool_call: object) -> tuple[str, str]:
    if not isinstance(tool_call, dict):
        return "", "{}"
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return "", "{}"
    name = str(function.get("name", "") or "")
    arguments = function.get("arguments", "{}")
    if isinstance(arguments, str):
        return name, arguments
    return name, json.dumps(arguments, ensure_ascii=False)


def tool_result_reports_change(tool_result: str, *, success: bool) -> bool:
    if not success:
        return False
    try:
        payload = json.loads(tool_result)
    except (TypeError, ValueError):
        return True
    if isinstance(payload, dict) and isinstance(payload.get("changed"), bool):
        return bool(payload["changed"])
    return True
