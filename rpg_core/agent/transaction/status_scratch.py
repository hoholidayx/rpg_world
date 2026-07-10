"""Copy-on-write status-table scratch for one agent turn."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rpg_data.models import (
    STATUS_KEY_COLUMN,
    STATUS_KIND_NORMAL,
    STATUS_VALUE_COLUMN,
    StatusTableDocument,
    parse_status_document,
    serialize_status_document,
)
from rpg_core.status.manager import StatusValueUpdateResult, collect_value_changes

if TYPE_CHECKING:
    from rpg_core.status.manager import StatusManager


@dataclass(frozen=True)
class StatusDocumentChange:
    """One status table document staged by a turn."""

    table_id: int
    status_kind: str
    base_document: StatusTableDocument
    document: StatusTableDocument


def _attrs_from_document(document: StatusTableDocument) -> dict[str, str]:
    return {row.key: row.value for row in document.rows}


def _table_dict_with_document(table: dict[str, object], document: StatusTableDocument) -> dict[str, object]:
    updated = dict(table)
    updated["document"] = document.to_json_dict()
    updated["headers"] = list(document.headers)
    updated["rows"] = [list(row) for row in document.data_rows]
    return updated


def _validate_key_value_columns(
    document: StatusTableDocument,
    *,
    key_column: int | str,
    value_column: int | str,
) -> None:
    accepted_key_columns = {0, STATUS_KEY_COLUMN, document.key_column}
    accepted_value_columns = {1, STATUS_VALUE_COLUMN, document.value_column}
    if key_column not in accepted_key_columns or value_column not in accepted_value_columns:
        raise ValueError("Turn status scratch only supports key-value document columns")


class StatusDocumentScratch:
    """Memory-only COW scratch for status table documents."""

    def __init__(self, real_status_mgr: "StatusManager | None") -> None:
        self._real_status_mgr = real_status_mgr
        self._base_tables: dict[int, dict[str, object]] = {}
        self._base_documents: dict[int, StatusTableDocument] = {}
        self._staged_documents: dict[int, StatusTableDocument] = {}
        self._active_scene_id: int | None = None
        self._active_scene_key: tuple[str, str] | None = None
        if real_status_mgr is not None:
            scene_ref = real_status_mgr.get_active_scene_table_ref()
            if scene_ref is not None:
                self._active_scene_id, self._active_scene_key = scene_ref

    @property
    def staged_changes(self) -> list[StatusDocumentChange]:
        return [
            StatusDocumentChange(
                table_id=table_id,
                status_kind=str(self._base_table(table_id).get("status_kind", "")),
                base_document=self._base_document(table_id),
                document=document,
            )
            for table_id, document in self._staged_documents.items()
        ]

    @property
    def change_token(self) -> tuple[tuple[int, str], ...]:
        return tuple(
            (table_id, serialize_status_document(document))
            for table_id, document in sorted(self._staged_documents.items())
        )

    def list_context_tables(self) -> list[dict[str, object]]:
        if self._real_status_mgr is None:
            return []
        tables = self._real_status_mgr.list_context_tables()
        snapshot_tables: list[dict[str, object]] = []
        for table in tables:
            table_id = int(table.get("id", 0))
            if table_id > 0:
                self._cache_base_table(table_id, table)
                snapshot_tables.append(self._base_tables[table_id])
            else:
                snapshot_tables.append(table)
        return [self._table_with_staged_document(table) for table in snapshot_tables]

    def get_active_scene_table(self) -> dict[str, object] | None:
        if self._active_scene_id is None:
            return None
        return self.get_table_by_id(self._active_scene_id)

    def get_active_scene_table_ref(self) -> tuple[int, tuple[str, str]] | None:
        if self._active_scene_id is None or self._active_scene_key is None:
            return None
        return self._active_scene_id, self._active_scene_key

    def get_scene_attrs(self) -> dict[str, str] | None:
        if self._active_scene_id is None:
            return None
        return _attrs_from_document(self._current_document(self._active_scene_id))

    def get_table_by_id(self, table_id: int) -> dict[str, object]:
        table_id = int(table_id)
        table = self._base_table(table_id)
        return _table_dict_with_document(table, self._current_document(table_id))

    def runtime_set_key_value(
        self,
        table_id: int,
        key: str,
        value: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
        value_column: int | str = STATUS_VALUE_COLUMN,
    ) -> dict[str, object]:
        table_id = int(table_id)
        document = self._current_document(table_id)
        _validate_key_value_columns(document, key_column=key_column, value_column=value_column)
        self._stage_document(table_id, document.with_key_value(key, value))
        return self.get_table_by_id(table_id)

    def runtime_delete_key_value(
        self,
        table_id: int,
        key: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
    ) -> dict[str, object]:
        table_id = int(table_id)
        document = self._current_document(table_id)
        _validate_key_value_columns(document, key_column=key_column, value_column=document.value_column)
        document_row = document.row_for_key(key)
        if document_row is None:
            raise FileNotFoundError(f"Status table key not found: {key}")
        if document_row.runtime_key_locked:
            raise PermissionError(f"Status key is runtime locked: {key}")
        self._stage_document(table_id, document.without_key(key))
        return self.get_table_by_id(table_id)

    def runtime_set_existing_values(
        self,
        table_id: int,
        updates: list[tuple[str, str]],
    ) -> StatusValueUpdateResult:
        table_id = int(table_id)
        table = self._base_table(table_id)
        if str(table.get("status_kind", "")) != STATUS_KIND_NORMAL:
            raise PermissionError("Generic status table updates only support normal tables")
        current = self._current_document(table_id)
        try:
            updated = current.with_existing_values(updates)
        except FileNotFoundError as exc:
            raise KeyError(str(exc)) from exc
        changes = collect_value_changes(current, updated, updates)
        if changes:
            self._stage_document(table_id, updated)
        return StatusValueUpdateResult(
            table_id=table_id,
            table_name=str(table.get("name", "")),
            changes=changes,
        )

    def commit(self, real_status_mgr: "StatusManager | None" = None) -> list[StatusDocumentChange]:
        mgr = real_status_mgr or self._real_status_mgr
        if mgr is None:
            return []
        changes = self.staged_changes
        for change in changes:
            mgr.save_table_document(
                change.table_id,
                change.document,
                expected_status_kind=change.status_kind,
                base_document=change.base_document,
                write_source="agent_turn",
            )
        return changes

    def _stage_document(self, table_id: int, document: StatusTableDocument) -> None:
        if document == self._base_document(table_id):
            self._staged_documents.pop(table_id, None)
            return
        self._staged_documents[table_id] = document

    def _table_with_staged_document(self, table: dict[str, object]) -> dict[str, object]:
        table_id = int(table.get("id", 0))
        staged = self._staged_documents.get(table_id)
        if staged is None:
            return table
        return _table_dict_with_document(table, staged)

    def _base_table(self, table_id: int) -> dict[str, object]:
        if table_id not in self._base_tables:
            if self._real_status_mgr is None:
                raise FileNotFoundError(f"Status table not found: {table_id}")
            self._cache_base_table(table_id, self._real_status_mgr.get_table_by_id(table_id))
        return self._base_tables[table_id]

    def _cache_base_table(self, table_id: int, table: dict[str, object]) -> None:
        if table_id in self._base_tables:
            return
        self._base_tables[table_id] = table
        raw_document = table.get("document")
        if isinstance(raw_document, dict):
            self._base_documents[table_id] = parse_status_document(
                json.dumps(raw_document, ensure_ascii=False)
            )

    def _base_document(self, table_id: int) -> StatusTableDocument:
        if table_id not in self._base_documents:
            if self._real_status_mgr is None:
                raise FileNotFoundError(f"Status table not found: {table_id}")
            self._base_documents[table_id] = self._real_status_mgr.get_table_document_by_id(table_id)
        return self._base_documents[table_id]

    def _current_document(self, table_id: int) -> StatusTableDocument:
        staged = self._staged_documents.get(table_id)
        if staged is not None:
            return staged
        return self._base_document(table_id)


class ScratchStatusManager:
    """StatusManager-shaped adapter backed by a StatusDocumentScratch."""

    def __init__(self, real_status_mgr: "StatusManager | None", scratch: StatusDocumentScratch) -> None:
        self._real_status_mgr = real_status_mgr
        self._scratch = scratch
        self.session_id = real_status_mgr.session_id if real_status_mgr is not None else ""

    def list_types(self) -> list[str]:
        return self._real_status_mgr.list_types() if self._real_status_mgr is not None else []

    def list_tables(self, status_kind: str | None = None) -> list[str]:
        return self._real_status_mgr.list_tables(status_kind) if self._real_status_mgr is not None else []

    def list_context_tables(self) -> list[dict[str, object]]:
        return self._scratch.list_context_tables()

    def get_table(self, table_name: str, status_kind: str | None = None) -> dict[str, object]:
        if self._real_status_mgr is None:
            raise FileNotFoundError(f"Status table not found: {table_name}")
        table = self._real_status_mgr.get_table(table_name, status_kind)
        table_id = int(table.get("id", 0))
        return self._scratch.get_table_by_id(table_id)

    def get_table_by_id(self, table_id: int) -> dict[str, object]:
        return self._scratch.get_table_by_id(int(table_id))

    def get_active_scene_table(self) -> dict[str, object] | None:
        return self._scratch.get_active_scene_table()

    def get_active_scene_table_ref(self) -> tuple[int, tuple[str, str]] | None:
        return self._scratch.get_active_scene_table_ref()

    def get_scene_attrs(self) -> dict[str, str] | None:
        return self._scratch.get_scene_attrs()

    def runtime_set_key_value(
        self,
        table_id: int,
        key: str,
        value: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
        value_column: int | str = STATUS_VALUE_COLUMN,
    ) -> dict[str, object]:
        return self._scratch.runtime_set_key_value(
            table_id,
            key,
            value,
            key_column=key_column,
            value_column=value_column,
        )

    def runtime_delete_key_value(
        self,
        table_id: int,
        key: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
    ) -> dict[str, object]:
        return self._scratch.runtime_delete_key_value(table_id, key, key_column=key_column)

    def runtime_set_existing_values(
        self,
        table_id: int,
        updates: list[tuple[str, str]],
    ) -> StatusValueUpdateResult:
        return self._scratch.runtime_set_existing_values(table_id, updates)

    set_key_value = runtime_set_key_value
    delete_key_value = runtime_delete_key_value
