"""LLM tools for value-only updates to normal session status tables."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from rpg_data import models
from rpg_core.tooling.base import BaseTool
from rpg_core.status.manager import StatusValueUpdateResult

STATUS_TABLE_SET_VALUES_TOOL_NAME = "status_table_set_values"

logger = logging.getLogger("rpg_core.status.tools")


class StatusWritePolicyError(PermissionError):
    """The requested field is outside the phase-bound write policy."""


class StatusTableRuntime(Protocol):
    session_id: str

    def list_context_tables(self) -> list[dict[str, object]]: ...

    def get_table_by_id(self, table_id: int) -> dict[str, object]: ...

    def runtime_set_existing_values(
        self,
        table_id: int,
        updates: list[tuple[str, str]],
    ) -> StatusValueUpdateResult: ...


@dataclass(frozen=True)
class StatusWritePolicy:
    """Code-enforced table/key/frequency boundary for one tool binding."""

    allowed_frequencies: frozenset[str] = frozenset({
        models.STATUS_UPDATE_FREQUENCY_REALTIME,
        models.STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
    })
    allowed_keys: dict[int, frozenset[str]] | None = None

    def validate(
        self,
        runtime: StatusTableRuntime,
        table_id: int,
        updates: list[tuple[str, str]],
    ) -> None:
        table = runtime.get_table_by_id(table_id)
        raw_document = table.get("document")
        if not isinstance(raw_document, dict):
            raise StatusWritePolicyError("状态表缺少可验证的 document")
        rows = raw_document.get("rows")
        if not isinstance(rows, list):
            raise StatusWritePolicyError("状态表缺少可验证的 rows")
        policies = {
            str(row.get("key", "")): str(
                row.get(models.STATUS_ROW_UPDATE_FREQUENCY_KEY)
                or models.STATUS_UPDATE_FREQUENCY_REALTIME
            )
            for row in rows
            if isinstance(row, dict)
        }
        scoped_keys = (
            self.allowed_keys.get(table_id, frozenset())
            if self.allowed_keys is not None
            else None
        )
        for key, _value in updates:
            if scoped_keys is not None and key not in scoped_keys:
                raise StatusWritePolicyError(f"字段不在本阶段写入范围：{key}")
            frequency = policies.get(key)
            if frequency is None:
                raise KeyError(f"Status table key not found: {key}")
            if frequency not in self.allowed_frequencies:
                raise StatusWritePolicyError(
                    f"字段更新频率不允许在本阶段写入：{key}/{frequency}"
                )


class StatusTableSetValuesTool(BaseTool):
    name = STATUS_TABLE_SET_VALUES_TOOL_NAME
    description = (
        "批量修改当前 session 普通状态表中已有键的值。"
        "table_id 必须使用状态表上下文给出的运行时表 ID。"
        "只能修改已有键的 value，不能新增、删除或重命名 key；不确定时不要调用。"
    )

    def __init__(
        self,
        runtime: StatusTableRuntime,
        *,
        write_policy: StatusWritePolicy | None = None,
    ) -> None:
        self._runtime = runtime
        self._write_policy = write_policy or StatusWritePolicy()

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
            self._write_policy.validate(
                self._runtime,
                normalized_id,
                normalized_updates,
            )
            result = self._runtime.runtime_set_existing_values(normalized_id, normalized_updates)
        except FileNotFoundError as exc:
            logger.warning(
                "status table tool rejected inaccessible table session_id=%s table_id=%s detail=%s",
                self._runtime.session_id,
                table_id,
                exc,
            )
            return _error("table_unavailable", "状态表不存在或当前 session 无权访问")
        except StatusWritePolicyError as exc:
            return _error("write_not_allowed", str(exc))
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

    def __init__(
        self,
        runtime: StatusTableRuntime,
        *,
        write_policy: StatusWritePolicy | None = None,
    ) -> None:
        self._runtime = runtime
        self._write_policy = write_policy

    def get_tools(self) -> list[BaseTool]:
        try:
            has_keys = any(
                _has_llm_writable_field(table)
                for table in self._runtime.list_context_tables()
            )
        except Exception as exc:
            logger.warning(
                "failed to inspect writable status tables session_id=%s detail=%s",
                self._runtime.session_id,
                exc,
            )
            return []
        return [
            StatusTableSetValuesTool(
                self._runtime,
                write_policy=self._write_policy,
            )
        ] if has_keys else []


def _has_llm_writable_field(table: dict[str, object]) -> bool:
    document = table.get("document")
    rows = document.get("rows") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        return False
    return any(
        isinstance(row, dict)
        and str(
            row.get(models.STATUS_ROW_UPDATE_FREQUENCY_KEY)
            or models.STATUS_UPDATE_FREQUENCY_REALTIME
        ) in {
            models.STATUS_UPDATE_FREQUENCY_REALTIME,
            models.STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
        }
        for row in rows
    )


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
