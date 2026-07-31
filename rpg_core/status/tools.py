"""LLM tools for field-level updates to normal Session status tables."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from rpg_core.tooling.base import BaseTool
from rpg_data.model.status import STATUS_KIND_NORMAL
from rpg_core.status.manager import (
    StatusFieldConflictError,
    StatusFieldEditError,
    StatusFieldEditResult,
    StatusFieldKeyNotFoundError,
    StatusFieldLockedError,
    StatusValueUpdateResult,
)

STATUS_TABLE_SET_VALUES_TOOL_NAME = "status_table_set_values"
STATUS_TABLE_EDIT_FIELDS_TOOL_NAME = "status_table_edit_fields"

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

    def runtime_edit_fields(
        self,
        table_id: int,
        *,
        creates: list[tuple[str, str]],
        renames: list[tuple[str, str]],
        deletes: list[str],
    ) -> StatusFieldEditResult: ...


@dataclass(frozen=True)
class StatusWritePolicy:
    """Code-enforced table/key boundary for one tool binding."""

    allowed_keys: dict[int, frozenset[str]] | None = None
    allowed_structure_table_ids: frozenset[int] | None = None

    def validate_values(
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
        existing_keys = {
            str(row.get("key", ""))
            for row in rows
            if isinstance(row, dict) and str(row.get("key", ""))
        }
        scoped_keys = (
            self.allowed_keys.get(table_id, frozenset())
            if self.allowed_keys is not None
            else None
        )
        for key, _value in updates:
            if scoped_keys is not None and key not in scoped_keys:
                raise StatusWritePolicyError(f"字段不在本阶段写入范围：{key}")
            if key not in existing_keys:
                raise KeyError(f"Status table key not found: {key}")

    def validate_structure(
        self,
        runtime: StatusTableRuntime,
        table_id: int,
        *,
        renames: list[tuple[str, str]],
        deletes: list[str],
    ) -> None:
        table = runtime.get_table_by_id(table_id)
        if self.allowed_structure_table_ids is not None:
            if table_id not in self.allowed_structure_table_ids:
                raise StatusWritePolicyError(
                    f"状态表不在本阶段结构写入范围：{table_id}"
                )
        if self.allowed_keys is None:
            return
        if table_id not in self.allowed_keys:
            raise StatusWritePolicyError(
                f"状态表不在本阶段结构写入范围：{table_id}"
            )
        scoped_keys = self.allowed_keys.get(table_id, frozenset())
        for key in [
            *(source for source, _target in renames),
            *deletes,
        ]:
            if key not in scoped_keys:
                raise StatusWritePolicyError(f"字段不在本阶段写入范围：{key}")
        raw_document = table.get("document")
        rows = raw_document.get("rows") if isinstance(raw_document, dict) else None
        if not isinstance(rows, list):
            raise StatusWritePolicyError("状态表缺少可验证的 rows")


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
            self._write_policy.validate_values(
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


class StatusTableEditFieldsTool(BaseTool):
    name = STATUS_TABLE_EDIT_FIELDS_TOOL_NAME
    description = (
        "在当前 session 已有的普通状态表内原子新增、重命名或删除字段。"
        "table_id 必须使用状态表上下文给出的运行时表 ID。"
        "creates、renames、deletes 至少一项非空；未使用的操作数组可省略。"
        "新字段追加到表尾；重命名保留原值、位置和作者策略。"
        "runtimeKeyLocked=true 的字段不能重命名或删除，但仍可用 "
        "status_table_set_values 修改 value。不能修改锁、updateRule 或 metadata。"
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
                    "description": "状态表上下文中标注的运行时普通表 ID。",
                },
                "creates": {
                    "type": "array",
                    "description": "新增字段；新字段使用默认未锁定结构策略。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "description": "尚不存在的新字段名。"},
                            "value": {"type": "string", "description": "字段初始值，可为空字符串。"},
                        },
                        "required": ["key", "value"],
                        "additionalProperties": False,
                    },
                },
                "renames": {
                    "type": "array",
                    "description": "重命名已有且未锁定的字段。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "description": "已有字段名。"},
                            "new_key": {"type": "string", "description": "尚不存在的新字段名。"},
                        },
                        "required": ["key", "new_key"],
                        "additionalProperties": False,
                    },
                },
                "deletes": {
                    "type": "array",
                    "description": "删除已有且未锁定的字段名。",
                    "items": {"type": "string"},
                },
            },
            "required": ["table_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        table_id: object = None,
        creates: object = None,
        renames: object = None,
        deletes: object = None,
        **extra: object,
    ) -> str:
        try:
            if extra:
                raise ValueError(f"不支持的参数：{', '.join(sorted(extra))}")
            (
                normalized_id,
                normalized_creates,
                normalized_renames,
                normalized_deletes,
            ) = _normalize_field_edit_arguments(
                table_id,
                creates,
                renames,
                deletes,
            )
            self._write_policy.validate_structure(
                self._runtime,
                normalized_id,
                renames=normalized_renames,
                deletes=normalized_deletes,
            )
            result = self._runtime.runtime_edit_fields(
                normalized_id,
                creates=normalized_creates,
                renames=normalized_renames,
                deletes=normalized_deletes,
            )
        except FileNotFoundError as exc:
            logger.warning(
                "status field tool rejected inaccessible table session_id=%s table_id=%s detail=%s",
                self._runtime.session_id,
                table_id,
                exc,
            )
            return _field_error(
                "table_unavailable",
                "状态表不存在或当前 session 无权访问",
            )
        except StatusWritePolicyError as exc:
            return _field_error("write_not_allowed", str(exc))
        except PermissionError as exc:
            logger.warning(
                "status field tool rejected non-normal table session_id=%s table_id=%s detail=%s",
                self._runtime.session_id,
                table_id,
                exc,
            )
            return _field_error(
                "unsupported_table_kind",
                "该工具只能修改普通状态表结构，场景表请使用 scene 工具",
            )
        except StatusFieldLockedError as exc:
            return _field_error("field_locked", str(exc))
        except StatusFieldKeyNotFoundError as exc:
            return _field_error("key_not_found", str(exc))
        except StatusFieldConflictError as exc:
            return _field_error("key_conflict", str(exc))
        except StatusFieldEditError as exc:
            return _field_error("invalid_arguments", str(exc))
        except (TypeError, ValueError) as exc:
            return _field_error("invalid_arguments", str(exc))
        except Exception:
            logger.exception(
                "status field tool failed session_id=%s table_id=%s",
                self._runtime.session_id,
                table_id,
            )
            return _field_error(
                "internal_error",
                "状态表结构更新失败，请稍后重试",
            )

        return json.dumps(
            {
                "ok": True,
                "tableId": result.table_id,
                "tableName": result.table_name,
                "changed": result.changed,
                "created": [
                    {"key": item.key, "value": item.value}
                    for item in result.created
                ],
                "renamed": [
                    {"key": item.key, "newKey": item.new_key}
                    for item in result.renamed
                ],
                "deleted": [
                    {"key": item.key, "oldValue": item.old_value}
                    for item in result.deleted
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


class StatusTableToolProvider:
    """Expose value and structure writers for available normal tables."""

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
            normal_tables = [
                table
                for table in self._runtime.list_context_tables()
                if _is_normal_table(table)
            ]
        except Exception as exc:
            logger.warning(
                "failed to inspect writable status tables session_id=%s detail=%s",
                self._runtime.session_id,
                exc,
            )
            return []
        if not normal_tables:
            return []
        tools: list[BaseTool] = []
        if any(_has_status_field(table) for table in normal_tables):
            tools.append(StatusTableSetValuesTool(
                self._runtime,
                write_policy=self._write_policy,
            ))
        tools.append(StatusTableEditFieldsTool(
            self._runtime,
            write_policy=self._write_policy,
        ))
        return tools


def _is_normal_table(table: dict[str, object]) -> bool:
    return str(table.get("status_kind", "")) == str(STATUS_KIND_NORMAL)


def _has_status_field(table: dict[str, object]) -> bool:
    document = table.get("document")
    rows = document.get("rows") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        return False
    return any(
        isinstance(row, dict) and bool(str(row.get("key", "")))
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


def _normalize_field_edit_arguments(
    table_id: object,
    creates: object,
    renames: object,
    deletes: object,
) -> tuple[
    int,
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[str],
]:
    if isinstance(table_id, bool) or not isinstance(table_id, int):
        raise TypeError("table_id 必须是整数")
    creates = [] if creates is None else creates
    renames = [] if renames is None else renames
    deletes = [] if deletes is None else deletes
    if not isinstance(creates, list):
        raise TypeError("creates 必须是数组")
    if not isinstance(renames, list):
        raise TypeError("renames 必须是数组")
    if not isinstance(deletes, list):
        raise TypeError("deletes 必须是数组")
    if not (creates or renames or deletes):
        raise ValueError("creates、renames、deletes 至少需要一项操作")

    normalized_creates = _normalize_pair_items(
        creates,
        item_name="creates",
        value_name="value",
    )
    normalized_renames = _normalize_pair_items(
        renames,
        item_name="renames",
        value_name="new_key",
    )
    normalized_deletes: list[str] = []
    seen_deletes: set[str] = set()
    for key in deletes:
        if not isinstance(key, str) or not key:
            raise TypeError("deletes 中的字段名必须是非空字符串")
        if key in seen_deletes:
            raise ValueError(f"deletes 包含重复 key：{key}")
        seen_deletes.add(key)
        normalized_deletes.append(key)
    return (
        table_id,
        normalized_creates,
        normalized_renames,
        normalized_deletes,
    )


def _normalize_pair_items(
    items: list[object],
    *,
    item_name: str,
    value_name: str,
) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    expected_keys = {"key", value_name}
    for item in items:
        if not isinstance(item, dict):
            raise TypeError(f"{item_name} 中的每一项都必须是对象")
        if set(item) != expected_keys:
            raise ValueError(
                f"{item_name} 中的每一项只能包含 key 和 {value_name}"
            )
        key = item["key"]
        value = item[value_name]
        if not isinstance(key, str) or not key:
            raise TypeError(f"{item_name}.key 必须是非空字符串")
        if not isinstance(value, str):
            raise TypeError(f"{item_name}.{value_name} 必须是字符串")
        if value_name == "new_key" and not value:
            raise TypeError(f"{item_name}.new_key 必须是非空字符串")
        if key in seen:
            raise ValueError(f"{item_name} 包含重复 key：{key}")
        seen.add(key)
        normalized.append((key, value))
    return normalized


def _error(code: str, message: str) -> str:
    return json.dumps(
        {"ok": False, "changed": False, "changes": [], "errorCode": code, "message": message},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _field_error(code: str, message: str) -> str:
    return json.dumps(
        {
            "ok": False,
            "changed": False,
            "created": [],
            "renamed": [],
            "deleted": [],
            "errorCode": code,
            "message": message,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
