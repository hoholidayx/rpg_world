"""Thin agent-facing adapter for session status tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from rpg_data.models import STATUS_KEY_COLUMN, STATUS_KIND_NORMAL, STATUS_KIND_SCENE, STATUS_VALUE_COLUMN, StatusRowRef
from rpg_data.services import get_data_service_gateway

if TYPE_CHECKING:
    from rpg_data.models import SessionStatusTable, StatusDeferredProgress, StatusTableDocument
    from rpg_core.agent.transaction.status_scratch import StatusDocumentChange
    from rpg_data.services.status import StatusTableService


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
    """Read and update status tables copied for one session."""

    def __init__(
        self,
        session_id: str,
        service: "StatusTableService | None" = None,
    ) -> None:
        self.session_id = session_id
        self._service = service or get_data_service_gateway().status

    # ------------------------------------------------------------------
    # Reads used by context building
    # ------------------------------------------------------------------

    def list_types(self) -> list[str]:
        return [STATUS_KIND_NORMAL, STATUS_KIND_SCENE]

    def list_tables(self, status_kind: str | None = None) -> list[str]:
        return [
            table.name
            for table in self._service.list_tables(self.session_id, status_kind)
        ]

    def list_context_tables(self) -> list[dict[str, object]]:
        return [
            _table_to_dict(table)
            for table in self._service.list_context_tables(self.session_id)
        ]

    def get_table(self, table_name: str, status_kind: str | None = None) -> dict[str, object]:
        return _table_to_dict(self._service.get_table(self.session_id, table_name, status_kind))

    def get_table_by_id(self, table_id: int) -> dict[str, object]:
        return _table_to_dict(self._service.get_table_for_session(self.session_id, table_id))

    def get_table_document_by_id(self, table_id: int) -> "StatusTableDocument":
        return self._service.get_table_for_session(self.session_id, table_id).document

    def save_table_document(
        self,
        table_id: int,
        document: "StatusTableDocument",
        *,
        expected_status_kind: str | None = None,
        base_document: "StatusTableDocument | None" = None,
        write_source: str = "agent_turn",
    ) -> dict[str, object]:
        table = self._service.get_table_for_session(self.session_id, table_id)
        return _table_to_dict(
            self._service.save_table_for_session(
                self.session_id,
                table_id,
                document,
                expected_status_kind=expected_status_kind or table.status_kind,
                base_document=base_document,
                write_source=write_source,
            )
        )

    def list_deferred_progress(self) -> list["StatusDeferredProgress"]:
        return self._service.list_deferred_progress(self.session_id)

    def clamp_deferred_progress(self, max_turn_id: int) -> int:
        return self._service.clamp_deferred_progress(
            self.session_id,
            max_turn_id,
        )

    def commit_deferred_update(
        self,
        table_id: int,
        document: "StatusTableDocument",
        *,
        processed_keys: Iterable[str],
        last_processed_turn_id: int,
        base_document: "StatusTableDocument | None" = None,
    ) -> dict[str, object]:
        return _table_to_dict(
            self._service.commit_deferred_update(
                self.session_id,
                table_id,
                document,
                processed_keys=processed_keys,
                last_processed_turn_id=last_processed_turn_id,
                base_document=base_document,
            )
        )

    def commit_bootstrap_state(
        self,
        changes: Iterable["StatusDocumentChange"],
        *,
        deferred_progress: dict[int, tuple[str, ...]],
        boundary_turn_id: int,
    ) -> list[dict[str, object]]:
        """Publish all bootstrap state and deferred markers in one SQL transaction."""
        from rpg_data.models import StatusBootstrapDocument

        documents = tuple(
            StatusBootstrapDocument(
                table_id=change.table_id,
                status_kind=change.status_kind,
                document=change.document,
                base_document=change.base_document,
            )
            for change in changes
        )
        return [
            _table_to_dict(table)
            for table in self._service.commit_bootstrap_state(
                self.session_id,
                documents,
                deferred_progress=deferred_progress,
                boundary_turn_id=boundary_turn_id,
            )
        ]

    # ------------------------------------------------------------------
    # Generic table writes
    # ------------------------------------------------------------------

    def set_cell(
        self,
        table_id: int,
        row: int | StatusRowRef,
        column: int | str,
        value: str,
    ) -> dict[str, object]:
        return _table_to_dict(
            self._service.set_cell(table_id, row, column, value)
        )

    def append_row(
        self,
        table_id: int,
        values: Iterable[str],
    ) -> dict[str, object]:
        return _table_to_dict(self._service.append_row(table_id, values))

    def replace_row(
        self,
        table_id: int,
        row: int | StatusRowRef,
        values: Iterable[str],
    ) -> dict[str, object]:
        return _table_to_dict(
            self._service.replace_row(table_id, row, values)
        )

    def delete_row(
        self,
        table_id: int,
        row: int | StatusRowRef,
    ) -> dict[str, object]:
        return _table_to_dict(self._service.delete_row(table_id, row))

    def set_key_value(
        self,
        table_id: int,
        key: str,
        value: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
        value_column: int | str = STATUS_VALUE_COLUMN,
    ) -> dict[str, object]:
        return _table_to_dict(
            self._service.set_key_value(
                table_id,
                key,
                value,
                key_column=key_column,
                value_column=value_column,
            )
        )

    def delete_key_value(
        self,
        table_id: int,
        key: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
    ) -> dict[str, object]:
        return _table_to_dict(
            self._service.delete_key_value(
                table_id,
                key,
                key_column=key_column,
            )
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
        return _table_to_dict(
            self._service.runtime_set_key_value(
                table_id,
                key,
                value,
                key_column=key_column,
                value_column=value_column,
            )
        )

    def runtime_delete_key_value(
        self,
        table_id: int,
        key: str,
        *,
        key_column: int | str = STATUS_KEY_COLUMN,
    ) -> dict[str, object]:
        return _table_to_dict(
            self._service.runtime_delete_key_value(
                table_id,
                key,
                key_column=key_column,
            )
        )

    def runtime_set_existing_values(
        self,
        table_id: int,
        updates: list[tuple[str, str]],
    ) -> StatusValueUpdateResult:
        table = self._service.get_table_for_session(self.session_id, table_id)
        if table.status_kind != STATUS_KIND_NORMAL:
            raise PermissionError("Generic status table updates only support normal tables")
        try:
            updated_document = table.document.with_existing_values(updates)
        except FileNotFoundError as exc:
            raise KeyError(str(exc)) from exc
        changes = collect_value_changes(table.document, updated_document, updates)
        if changes:
            self._service.save_table_for_session(
                self.session_id,
                table_id,
                updated_document,
                expected_status_kind=STATUS_KIND_NORMAL,
                base_document=table.document,
                write_source="runtime_tool",
            )
        return StatusValueUpdateResult(table.id, table.name, changes)

    # ------------------------------------------------------------------
    # Scene helpers
    # ------------------------------------------------------------------

    def get_active_scene_table(self) -> dict[str, object] | None:
        table = self._service.get_active_scene_table(self.session_id)
        return _table_to_dict(table) if table is not None else None

    def get_active_scene_table_ref(self) -> tuple[int, tuple[str, str]] | None:
        table = self._service.get_active_scene_table(self.session_id)
        if table is None:
            return None
        return table.id, (table.status_kind, table.name)

    def get_scene_attrs(self) -> dict[str, str] | None:
        return self._service.get_scene_attrs(self.session_id)


def _table_to_dict(table: "SessionStatusTable") -> dict[str, object]:
    return table.to_dict()


def collect_value_changes(
    current: "StatusTableDocument",
    updated: "StatusTableDocument",
    requested_updates: list[tuple[str, str]],
) -> tuple[StatusValueChange, ...]:
    current_by_key = {row.key: row.value for row in current.rows}
    updated_by_key = {row.key: row.value for row in updated.rows}
    return tuple(
        StatusValueChange(key, current_by_key[key], updated_by_key[key])
        for key, _value in requested_updates
        if current_by_key[key] != updated_by_key[key]
    )
