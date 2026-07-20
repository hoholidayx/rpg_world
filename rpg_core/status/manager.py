"""Session-scoped Agent facade for Status and Scene tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Protocol

from rpg_core.scene.status import SceneStatusService
from rpg_core.status.context_service import StatusContextService
from rpg_data.model.status import (
    STATUS_KEY_COLUMN,
    STATUS_KIND_NORMAL,
    STATUS_KIND_SCENE,
    STATUS_UPDATE_FREQUENCY_DEFERRED,
    STATUS_VALUE_COLUMN,
    SessionStatusMetadata,
    SessionStatusTable,
    StatusContextCandidate,
    StatusDeferredProgress,
    StatusDocumentBatchResult,
    StatusDocumentSaveResult,
    StatusDocumentWrite,
    StatusProgressWrite,
    StatusRowRef,
    StatusTableDocument,
)

if TYPE_CHECKING:
    from rpg_core.agent.turn.transaction.status_scratch import StatusDocumentChange


class StatusRuntimeDataPort(Protocol):
    """Persistence capabilities required by the Agent-facing Status facade."""

    def list_tables(
        self,
        session_id: str,
        status_kind: str | None = None,
    ) -> list[SessionStatusTable]: ...

    def list_context_candidates(
        self,
        session_id: str,
    ) -> list[StatusContextCandidate]: ...

    def update_table_metadata_for_session(
        self,
        session_id: str,
        table_id: int,
        metadata: SessionStatusMetadata,
    ) -> SessionStatusTable: ...

    def get_table(
        self,
        session_id: str,
        table_name: str,
        status_kind: str | None = None,
    ) -> SessionStatusTable: ...

    def get_table_for_session(
        self,
        session_id: str,
        table_id: int,
    ) -> SessionStatusTable: ...

    def save_table_for_session(
        self,
        session_id: str,
        table_id: int,
        document: StatusTableDocument,
        *,
        expected_status_kind: str,
        base_document: StatusTableDocument | None = None,
    ) -> StatusDocumentSaveResult: ...

    def list_deferred_progress(
        self,
        session_id: str,
    ) -> list[StatusDeferredProgress]: ...

    def clamp_deferred_progress(
        self,
        session_id: str,
        max_turn_id: int,
    ) -> int: ...

    def commit_document_batch(
        self,
        session_id: str,
        document_writes: Iterable[StatusDocumentWrite],
        progress_writes: Iterable[StatusProgressWrite] = (),
    ) -> StatusDocumentBatchResult: ...


@dataclass(frozen=True)
class StatusValueChange:
    key: str
    old_value: str
    new_value: str


@dataclass(frozen=True)
class StatusValueUpdateResult:
    table_id: int
    table_name: str
    changes: tuple[StatusValueChange, ...]

    @property
    def changed(self) -> bool:
        return bool(self.changes)


class StatusManager:
    """Read and mutate one Session through an explicitly injected data service."""

    def __init__(self, session_id: str, service: StatusRuntimeDataPort) -> None:
        self.session_id = str(session_id)
        self._service = service
        self._context = StatusContextService(service)
        self._scene = SceneStatusService(service)

    def list_types(self) -> list[str]:
        return [str(STATUS_KIND_NORMAL), str(STATUS_KIND_SCENE)]

    def list_tables(self, status_kind: str | None = None) -> list[str]:
        return [
            table.name
            for table in self._service.list_tables(self.session_id, status_kind)
        ]

    def list_context_tables(self) -> list[dict[str, object]]:
        return [
            _table_to_dict(table)
            for table in self._context.list_tables(self.session_id)
        ]

    def get_table(
        self,
        table_name: str,
        status_kind: str | None = None,
    ) -> dict[str, object]:
        return _table_to_dict(
            self._service.get_table(self.session_id, table_name, status_kind)
        )

    def get_table_by_id(self, table_id: int) -> dict[str, object]:
        return _table_to_dict(
            self._service.get_table_for_session(self.session_id, table_id)
        )

    def get_table_document_by_id(self, table_id: int) -> StatusTableDocument:
        return self._service.get_table_for_session(
            self.session_id,
            table_id,
        ).document

    def save_table_document(
        self,
        table_id: int,
        document: StatusTableDocument,
        *,
        expected_status_kind: str | None = None,
        base_document: StatusTableDocument | None = None,
        write_source: str = "agent_turn",
    ) -> dict[str, object]:
        del write_source
        table = self._service.get_table_for_session(self.session_id, table_id)
        return self._save_document(
            table,
            document,
            expected_status_kind=expected_status_kind or table.status_kind,
            base_document=base_document,
        )

    def list_deferred_progress(self) -> list[StatusDeferredProgress]:
        return self._service.list_deferred_progress(self.session_id)

    def clamp_deferred_progress(self, max_turn_id: int) -> int:
        return self._service.clamp_deferred_progress(
            self.session_id,
            max_turn_id,
        )

    def commit_deferred_update(
        self,
        table_id: int,
        document: StatusTableDocument,
        *,
        processed_keys: Iterable[str],
        last_processed_turn_id: int,
        base_document: StatusTableDocument | None = None,
    ) -> dict[str, object]:
        if last_processed_turn_id <= 0:
            raise ValueError("last_processed_turn_id must be positive")
        keys = tuple(dict.fromkeys(str(key) for key in processed_keys if str(key)))
        if not keys:
            raise ValueError("processed_keys must not be empty")
        table = self._service.get_table_for_session(self.session_id, table_id)
        if table.status_kind is not STATUS_KIND_NORMAL:
            raise PermissionError("Deferred updates only support normal status tables")
        validated = document.validated()
        _require_deferred_keys(validated, keys)
        result = self._service.commit_document_batch(
            self.session_id,
            (
                StatusDocumentWrite(
                    table_id=table_id,
                    expected_status_kind=STATUS_KIND_NORMAL,
                    document=validated,
                    base_document=base_document,
                ),
            ),
            tuple(
                StatusProgressWrite(
                    table_id=table_id,
                    field_key=key,
                    last_processed_turn_id=last_processed_turn_id,
                )
                for key in keys
            ),
        )
        return _table_to_dict(result.tables[0])

    def commit_bootstrap_state(
        self,
        changes: Iterable["StatusDocumentChange"],
        *,
        deferred_progress: dict[int, tuple[str, ...]],
        boundary_turn_id: int,
    ) -> list[dict[str, object]]:
        if boundary_turn_id <= 0:
            raise ValueError("boundary_turn_id must be positive")
        staged = tuple(changes)
        if len({change.table_id for change in staged}) != len(staged):
            raise ValueError("bootstrap documents contain duplicate table IDs")
        documents_by_table = {
            change.table_id: SceneStatusService.prepare_document(
                change.status_kind,
                change.document,
            )
            for change in staged
        }
        document_writes = tuple(
            StatusDocumentWrite(
                table_id=change.table_id,
                expected_status_kind=change.status_kind,
                document=documents_by_table[change.table_id],
                base_document=change.base_document,
            )
            for change in staged
        )
        progress_writes: list[StatusProgressWrite] = []
        for table_id, raw_keys in deferred_progress.items():
            keys = tuple(dict.fromkeys(str(key) for key in raw_keys if str(key)))
            table = self._service.get_table_for_session(self.session_id, table_id)
            if table.status_kind is not STATUS_KIND_NORMAL:
                raise PermissionError(
                    "Deferred bootstrap progress only supports normal status tables"
                )
            document = documents_by_table.get(table_id, table.document)
            _require_deferred_keys(document, keys)
            progress_writes.extend(
                StatusProgressWrite(
                    table_id=table_id,
                    field_key=key,
                    last_processed_turn_id=boundary_turn_id,
                )
                for key in keys
            )
        result = self._service.commit_document_batch(
            self.session_id,
            document_writes,
            progress_writes,
        )
        return [_table_to_dict(table) for table in result.tables]

    def set_cell(
        self,
        table_id: int,
        row: int | StatusRowRef,
        column: int | str,
        value: str,
    ) -> dict[str, object]:
        table = self._require_table(table_id)
        updated = table.document.with_data(
            table.data.with_cell(row, column, value)
        )
        return self._save_document(table, updated, base_document=table.document)

    def append_row(
        self,
        table_id: int,
        values: Iterable[str],
    ) -> dict[str, object]:
        table = self._require_table(table_id)
        updated = table.document.with_data(table.data.with_appended_row(values))
        return self._save_document(table, updated, base_document=table.document)

    def replace_row(
        self,
        table_id: int,
        row: int | StatusRowRef,
        values: Iterable[str],
    ) -> dict[str, object]:
        table = self._require_table(table_id)
        updated = table.document.with_data(
            table.data.with_replaced_row(row, values)
        )
        return self._save_document(table, updated, base_document=table.document)

    def delete_row(
        self,
        table_id: int,
        row: int | StatusRowRef,
    ) -> dict[str, object]:
        table = self._require_table(table_id)
        updated = table.document.with_data(table.data.with_deleted_row(row))
        return self._save_document(table, updated, base_document=table.document)

    def set_key_value(
        self,
        table_id: int,
        key: str,
        value: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
        value_column: int | str = STATUS_VALUE_COLUMN,
    ) -> dict[str, object]:
        table = self._require_table(table_id)
        if key_column == STATUS_KEY_COLUMN and value_column == STATUS_VALUE_COLUMN:
            updated = table.document.with_key_value(key, value)
        else:
            updated = table.document.with_data(
                table.data.with_key_value(
                    key,
                    value,
                    key_column=key_column,
                    value_column=value_column,
                )
            )
        return self._save_document(
            table,
            updated,
            base_document=table.document,
        )

    def delete_key_value(
        self,
        table_id: int,
        key: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
    ) -> dict[str, object]:
        table = self._require_table(table_id)
        if key_column == STATUS_KEY_COLUMN:
            updated = table.document.without_key(key)
        else:
            updated = table.document.with_data(
                table.data.without_key(key, key_column=key_column)
            )
        return self._save_document(
            table,
            updated,
            base_document=table.document,
        )

    def runtime_set_key_value(
        self,
        table_id: int,
        key: str,
        value: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
        value_column: int | str = STATUS_VALUE_COLUMN,
    ) -> dict[str, object]:
        return self.set_key_value(
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
        table = self._require_table(table_id)
        document_row = table.document.row_for_key(key)
        if document_row is None:
            raise FileNotFoundError(f"Status table key not found: {key}")
        if document_row.runtime_key_locked:
            raise PermissionError(f"Status key is runtime locked: {key}")
        return self.delete_key_value(table_id, key, key_column=key_column)

    def runtime_set_existing_values(
        self,
        table_id: int,
        updates: list[tuple[str, str]],
    ) -> StatusValueUpdateResult:
        table = self._require_table(table_id)
        if table.status_kind is not STATUS_KIND_NORMAL:
            raise PermissionError(
                "Generic status table updates only support normal tables"
            )
        try:
            updated_document = table.document.with_existing_values(updates)
        except FileNotFoundError as exc:
            raise KeyError(str(exc)) from exc
        changes = collect_value_changes(table.document, updated_document, updates)
        if changes:
            self._save_document(
                table,
                updated_document,
                expected_status_kind=STATUS_KIND_NORMAL,
                base_document=table.document,
            )
        return StatusValueUpdateResult(table.id, table.name, changes)

    def get_active_scene_table(self) -> dict[str, object] | None:
        table = self._scene.get_active_table(self.session_id)
        return _table_to_dict(table) if table is not None else None

    def get_active_scene_table_ref(self) -> tuple[int, tuple[str, str]] | None:
        table = self._scene.get_active_table(self.session_id)
        if table is None:
            return None
        return table.id, (str(table.status_kind), table.name)

    def get_scene_attrs(self) -> dict[str, str] | None:
        return self._scene.get_attrs(self.session_id)

    def _require_table(self, table_id: int) -> SessionStatusTable:
        return self._service.get_table_for_session(self.session_id, table_id)

    def _save_document(
        self,
        table: SessionStatusTable,
        document: StatusTableDocument,
        *,
        expected_status_kind: str | None = None,
        base_document: StatusTableDocument | None = None,
    ) -> dict[str, object]:
        prepared = SceneStatusService.prepare_document(
            table.status_kind,
            document,
        )
        result = self._service.save_table_for_session(
            self.session_id,
            table.id,
            prepared,
            expected_status_kind=expected_status_kind or table.status_kind,
            base_document=base_document,
        )
        return _table_to_dict(result.table)


def _table_to_dict(table: SessionStatusTable) -> dict[str, object]:
    return table.to_dict()


def _require_deferred_keys(
    document: StatusTableDocument,
    keys: Iterable[str],
) -> None:
    for key in keys:
        field = document.row_for_key(key)
        if field is None:
            raise KeyError(f"Status table key not found: {key}")
        if field.update_frequency is not STATUS_UPDATE_FREQUENCY_DEFERRED:
            raise PermissionError(f"Status field is not deferred: {key}")


def collect_value_changes(
    current: StatusTableDocument,
    updated: StatusTableDocument,
    requested_updates: list[tuple[str, str]],
) -> tuple[StatusValueChange, ...]:
    current_by_key = {row.key: row.value for row in current.rows}
    updated_by_key = {row.key: row.value for row in updated.rows}
    return tuple(
        StatusValueChange(key, current_by_key[key], updated_by_key[key])
        for key, _value in requested_updates
        if current_by_key[key] != updated_by_key[key]
    )


__all__ = [
    "StatusManager",
    "StatusRuntimeDataPort",
    "StatusValueChange",
    "StatusValueUpdateResult",
    "collect_value_changes",
]
