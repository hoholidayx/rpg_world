"""LLM tools for value-only updates to normal session status tables."""

from __future__ import annotations

import json
import logging
from typing import Protocol

from rpg_core.agent.tools.base import BaseTool
from rpg_core.status.manager import StatusValueUpdateResult

STATUS_TABLE_SET_VALUES_TOOL_NAME = "status_table_set_values"

logger = logging.getLogger("rpg_core.status.tools")


class StatusTableRuntime(Protocol):
    session_id: str

    def list_context_tables(self) -> list[dict[str, object]]: ...

    def runtime_set_existing_values(
        self,
        table_id: int,
        updates: list[tuple[str, str]],
    ) -> StatusValueUpdateResult: ...


class StatusTableSetValuesTool(BaseTool):
    name = STATUS_TABLE_SET_VALUES_TOOL_NAME
    description = (
        "批量修改当前 session 普通状态表中已有键的值。"
        "table_id 必须使用状态表上下文给出的运行时表 ID。"
        "只能修改已有键的 value，不能新增、删除或重命名 key；不确定时不要调用。"
    )

    def __init__(self, runtime: StatusTableRuntime) -> None:
        self._runtime = runtime

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "table_id": {
                    "type": "integer",
                    "description": "状态表上下文中标注的运行时表 ID。",
                },
                "updates": {
                    "type": "array",
                    "minItems": 1,
                    "description": "需要修改的已有键和值；同一个键只能出现一次。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "description": "状态表中已经存在的键。"},
                            "value": {"type": "string", "description": "该键的新值，可为空字符串。"},
                        },
                        "required": ["key", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["table_id", "updates"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        table_id: object = None,
        updates: object = None,
        **extra: object,
    ) -> str:
        try:
            if extra:
                raise ValueError(f"不支持的参数：{', '.join(sorted(extra))}")
            normalized_id, normalized_updates = _normalize_arguments(table_id, updates)
            result = self._runtime.runtime_set_existing_values(normalized_id, normalized_updates)
        except FileNotFoundError as exc:
            logger.warning(
                "status table tool rejected inaccessible table session_id=%s table_id=%s detail=%s",
                self._runtime.session_id,
                table_id,
                exc,
            )
            return _error("table_unavailable", "状态表不存在或当前 session 无权访问")
        except PermissionError as exc:
            logger.warning(
                "status table tool rejected non-normal table session_id=%s table_id=%s detail=%s",
                self._runtime.session_id,
                table_id,
                exc,
            )
            return _error("unsupported_table_kind", "该工具只能修改普通状态表，场景表请使用 scene 工具")
        except KeyError as exc:
            return _error("key_not_found", str(exc.args[0] if exc.args else exc))
        except (TypeError, ValueError) as exc:
            return _error("invalid_arguments", str(exc))
        except Exception:
            logger.exception(
                "status table tool failed session_id=%s table_id=%s",
                self._runtime.session_id,
                table_id,
            )
            return _error("internal_error", "状态表更新失败，请稍后重试")

        return json.dumps(
            {
                "ok": True,
                "tableId": result.table_id,
                "tableName": result.table_name,
                "changed": result.changed,
                "changes": [
                    {
                        "key": change.key,
                        "oldValue": change.old_value,
                        "newValue": change.new_value,
                    }
                    for change in result.changes
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


class StatusTableToolProvider:
    """Expose the generic writer only when at least one key can be updated."""

    def __init__(self, runtime: StatusTableRuntime) -> None:
        self._runtime = runtime

    def get_tools(self) -> list[BaseTool]:
        try:
            has_keys = any(table.get("rows") for table in self._runtime.list_context_tables())
        except Exception as exc:
            logger.warning(
                "failed to inspect writable status tables session_id=%s detail=%s",
                self._runtime.session_id,
                exc,
            )
            return []
        return [StatusTableSetValuesTool(self._runtime)] if has_keys else []


def _normalize_arguments(
    table_id: object,
    updates: object,
) -> tuple[int, list[tuple[str, str]]]:
    if isinstance(table_id, bool) or not isinstance(table_id, int):
        raise TypeError("table_id 必须是整数")
    if not isinstance(updates, list) or not updates:
        raise ValueError("updates 至少需要包含一项")

    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in updates:
        if not isinstance(item, dict):
            raise TypeError("updates 中的每一项都必须是对象")
        if set(item) != {"key", "value"}:
            raise ValueError("updates 中的每一项只能包含 key 和 value")
        key = item["key"]
        value = item["value"]
        if not isinstance(key, str) or not key:
            raise TypeError("update.key 必须是非空字符串")
        if not isinstance(value, str):
            raise TypeError("update.value 必须是字符串")
        if key in seen:
            raise ValueError(f"updates 包含重复 key：{key}")
        seen.add(key)
        normalized.append((key, value))
    return table_id, normalized


def _error(code: str, message: str) -> str:
    return json.dumps(
        {"ok": False, "changed": False, "changes": [], "errorCode": code, "message": message},
        ensure_ascii=False,
        separators=(",", ":"),
    )
