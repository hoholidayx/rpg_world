"""Production-schema tools backed by an in-memory benchmark runtime."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from rpg_core.rp_modules.narrative_outcome.tools import NarrativeOutcomeTool
from rpg_core.status.manager import (
    StatusFieldConflictError,
    StatusFieldCreated,
    StatusFieldDeleted,
    StatusFieldEditResult,
    StatusFieldKeyNotFoundError,
    StatusFieldLockedError,
    StatusFieldRenamed,
    StatusValueChange,
    StatusValueUpdateResult,
)
from rpg_core.status.tools import (
    StatusTableEditFieldsTool,
    StatusTableSetValuesTool,
)
from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry
from rpg_data.model.status import STATUS_KIND_NORMAL
from tests.rp_model_benchmark.models import (
    BenchmarkToolName,
    OutcomeSpec,
    RPBenchmarkCase,
)


@dataclass
class BenchmarkToolState:
    outcome: OutcomeSpec | None
    outcome_staged: bool = False
    invocations: list[dict[str, object]] = field(default_factory=list)


class FixedOutcomeTool(BaseTool):
    """Expose the production Outcome schema but return a fixed gold result."""

    name = NarrativeOutcomeTool.name
    description = NarrativeOutcomeTool.description

    def __init__(self, state: BenchmarkToolState) -> None:
        self._state = state
        self._schema_source = NarrativeOutcomeTool(module=None)

    def parameters(self) -> dict[str, object]:
        return self._schema_source.parameters()

    async def execute(self, **kwargs: object) -> str:
        reason = str(kwargs.get("reason", "") or "").strip()
        if not reason:
            raise ValueError("reason must not be empty")
        if self._state.outcome is None:
            raise RuntimeError("benchmark case has no fixed Outcome")
        if self._state.outcome_staged:
            raise PermissionError("rp_story_outcome is no longer available")
        self._state.outcome_staged = True
        payload = self._state.outcome.tool_payload()
        # Preserve the model's actual target wording as evidence while keeping
        # the fixed result and gold boundary authoritative.
        payload["requestedReason"] = reason
        if actor := str(kwargs.get("actor", "") or "").strip():
            payload["requestedActor"] = actor
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class InMemoryStatusRuntime:
    """Small implementation of the production Status tool runtime Protocol."""

    session_id = "rp_model_benchmark"

    def __init__(self, case: RPBenchmarkCase) -> None:
        self._tables = {
            table.table_id: {
                "id": table.table_id,
                "name": table.name,
                "description": table.description,
                "status_kind": str(STATUS_KIND_NORMAL),
                "document": {
                    "schemaVersion": 2,
                    "rows": [
                        row.model_dump(by_alias=True)
                        for row in table.rows
                    ],
                },
            }
            for table in case.status_tables
        }

    def list_context_tables(self) -> list[dict[str, object]]:
        return copy.deepcopy(list(self._tables.values()))

    def get_table_by_id(self, table_id: int) -> dict[str, object]:
        try:
            return copy.deepcopy(self._tables[int(table_id)])
        except (KeyError, TypeError, ValueError) as exc:
            raise FileNotFoundError(table_id) from exc

    def runtime_set_existing_values(
        self,
        table_id: int,
        updates: list[tuple[str, str]],
    ) -> StatusValueUpdateResult:
        table = self._require_table(table_id)
        rows = self._rows(table)
        by_key = {str(row["key"]): row for row in rows}
        changes: list[StatusValueChange] = []
        for key, value in updates:
            if key not in by_key:
                raise KeyError(key)
            row = by_key[key]
            old = str(row.get("value", ""))
            if old == value:
                continue
            row["value"] = value
            changes.append(StatusValueChange(key, old, value))
        return StatusValueUpdateResult(
            table_id=table_id,
            table_name=str(table["name"]),
            changes=tuple(changes),
        )

    def runtime_edit_fields(
        self,
        table_id: int,
        *,
        creates: list[tuple[str, str]],
        renames: list[tuple[str, str]],
        deletes: list[str],
    ) -> StatusFieldEditResult:
        table = self._require_table(table_id)
        rows = self._rows(table)
        by_key = {str(row["key"]): row for row in rows}
        source_keys = [key for key, _ in renames] + list(deletes)
        if len(source_keys) != len(set(source_keys)):
            raise StatusFieldConflictError("同一字段不能同时重命名或删除")
        for key in source_keys:
            if key not in by_key:
                raise StatusFieldKeyNotFoundError(key)
            if bool(by_key[key].get("runtimeKeyLocked")):
                raise StatusFieldLockedError(key)
        targets = [key for key, _ in creates] + [target for _, target in renames]
        if len(targets) != len(set(targets)):
            raise StatusFieldConflictError("目标字段名重复")
        remaining = set(by_key).difference(source_keys)
        if remaining.intersection(targets):
            raise StatusFieldConflictError("目标字段已存在")

        renamed: list[StatusFieldRenamed] = []
        rename_map = dict(renames)
        for row in rows:
            key = str(row["key"])
            if key in rename_map:
                row["key"] = rename_map[key]
                renamed.append(StatusFieldRenamed(key, rename_map[key]))

        deleted: list[StatusFieldDeleted] = []
        delete_set = set(deletes)
        retained: list[dict[str, object]] = []
        for row in rows:
            original_key = next(
                (source for source, target in renames if target == row["key"]),
                str(row["key"]),
            )
            if original_key in delete_set:
                deleted.append(
                    StatusFieldDeleted(
                        original_key,
                        str(row.get("value", "")),
                    )
                )
            else:
                retained.append(row)
        rows[:] = retained

        created: list[StatusFieldCreated] = []
        for key, value in creates:
            rows.append({
                "key": key,
                "value": value,
                "runtimeKeyLocked": False,
                "updateRule": "",
                "metadata": {},
            })
            created.append(StatusFieldCreated(key, value))
        return StatusFieldEditResult(
            table_id=table_id,
            table_name=str(table["name"]),
            created=tuple(created),
            renamed=tuple(renamed),
            deleted=tuple(deleted),
        )

    def snapshot(self) -> list[dict[str, object]]:
        return self.list_context_tables()

    def _require_table(self, table_id: int) -> dict[str, object]:
        try:
            return self._tables[int(table_id)]
        except (KeyError, TypeError, ValueError) as exc:
            raise FileNotFoundError(table_id) from exc

    @staticmethod
    def _rows(table: dict[str, object]) -> list[dict[str, object]]:
        document = table.get("document")
        rows = document.get("rows") if isinstance(document, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError("invalid in-memory status table")
        return rows


class BenchmarkToolRuntime:
    def __init__(self, case: RPBenchmarkCase) -> None:
        self.state = BenchmarkToolState(case.tools.outcome)
        self.status = InMemoryStatusRuntime(case)
        self.registry = ToolRegistry()
        available = set(case.tools.available)
        if BenchmarkToolName.OUTCOME in available:
            self.registry.register(FixedOutcomeTool(self.state))
        if BenchmarkToolName.STATUS_VALUES in available:
            self.registry.register(StatusTableSetValuesTool(self.status))
        if BenchmarkToolName.STATUS_FIELDS in available:
            self.registry.register(StatusTableEditFieldsTool(self.status))

    def schemas(self) -> list[dict[str, object]] | None:
        schemas = self.registry.get_openai_schemas()
        if self.state.outcome_staged:
            schemas = [
                schema
                for schema in schemas
                if schema.get("function", {}).get("name")
                != BenchmarkToolName.OUTCOME.value
            ]
        return schemas or None

    async def execute(self, name: str, arguments: str) -> str:
        allowed = {
            str(schema.get("function", {}).get("name", ""))
            for schema in (self.schemas() or [])
        }
        if name not in allowed:
            result = f"Error: unknown tool {name!r}"
        else:
            result = await self.registry.execute(name, arguments)
        try:
            parsed_arguments: object = json.loads(arguments)
        except json.JSONDecodeError:
            parsed_arguments = arguments
        self.state.invocations.append({
            "name": name,
            "arguments": parsed_arguments,
            "result": result,
        })
        return result


__all__ = [
    "BenchmarkToolRuntime",
    "BenchmarkToolState",
    "FixedOutcomeTool",
    "InMemoryStatusRuntime",
]
