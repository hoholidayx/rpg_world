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
    STATUS_VALUE_COLUMN,
    SessionStatusMetadata,
    SessionStatusTable,
    StatusContextCandidate,
    StatusDocumentBatchResult,
    StatusDocumentSaveResult,
    StatusDocumentWrite,
    StatusRowRef,
    StatusTableDocument,
    StatusTableRow,
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

    def commit_document_batch(
        self,
        session_id: str,
        document_writes: Iterable[StatusDocumentWrite],
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


class StatusFieldEditError(ValueError):
    """Base error for one rejected normal-table structure edit."""


class StatusFieldLockedError(StatusFieldEditError):
    """A rename or delete targeted a runtime-locked field."""


class StatusFieldKeyNotFoundError(StatusFieldEditError):
    """A rename or delete targeted an unknown field."""


class StatusFieldConflictError(StatusFieldEditError):
    """One edit request contains conflicting field identities."""


@dataclass(frozen=True)
class StatusFieldCreated:
    key: str
    value: str


@dataclass(frozen=True)
class StatusFieldRenamed:
    key: str
    new_key: str


@dataclass(frozen=True)
class StatusFieldDeleted:
    key: str
    old_value: str


@dataclass(frozen=True)
class StatusFieldEditResult:
    table_id: int
    table_name: str
    created: tuple[StatusFieldCreated, ...] = ()
    renamed: tuple[StatusFieldRenamed, ...] = ()
    deleted: tuple[StatusFieldDeleted, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.created or self.renamed or self.deleted)


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

    def commit_bootstrap_state(
        self,
        changes: Iterable["StatusDocumentChange"],
    ) -> list[dict[str, object]]:
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
        result = self._service.commit_document_batch(
            self.session_id,
            document_writes,
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
        if table.status_kind != STATUS_KIND_NORMAL:
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

    def runtime_edit_fields(
        self,
        table_id: int,
        *,
        creates: list[tuple[str, str]],
        renames: list[tuple[str, str]],
        deletes: list[str],
    ) -> StatusFieldEditResult:
        table = self._require_table(table_id)
        if table.status_kind != STATUS_KIND_NORMAL:
            raise PermissionError(
                "Generic status field edits only support normal tables"
            )
        updated_document, result = apply_status_field_edits(
            table.document,
            table_id=table.id,
            table_name=table.name,
            creates=creates,
            renames=renames,
            deletes=deletes,
        )
        self._save_document(
            table,
            updated_document,
            expected_status_kind=STATUS_KIND_NORMAL,
            base_document=table.document,
        )
        return result

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

    def get_scene_update_rules(self) -> dict[str, str] | None:
        return self._scene.get_update_rules(self.session_id)

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


def apply_status_field_edits(
    current: StatusTableDocument,
    *,
    table_id: int,
    table_name: str,
    creates: list[tuple[str, str]],
    renames: list[tuple[str, str]],
    deletes: list[str],
) -> tuple[StatusTableDocument, StatusFieldEditResult]:
    """Validate and apply one atomic normal-table field edit in memory."""

    normalized_creates = [(str(key), str(value)) for key, value in creates]
    normalized_renames = [(str(key), str(new_key)) for key, new_key in renames]
    normalized_deletes = [str(key) for key in deletes]
    if not (normalized_creates or normalized_renames or normalized_deletes):
        raise StatusFieldEditError("Status field edits must not be empty")

    all_keys = [
        key
        for key, _value in normalized_creates
    ] + [
        key
        for key, _new_key in normalized_renames
    ] + normalized_deletes
    rename_targets = [new_key for _key, new_key in normalized_renames]
    if any(not key for key in all_keys + rename_targets):
        raise StatusFieldEditError("Status field keys must not be empty")

    create_keys = [key for key, _value in normalized_creates]
    rename_sources = [key for key, _new_key in normalized_renames]
    if len(set(create_keys)) != len(create_keys):
        raise StatusFieldConflictError("Status field creates contain duplicate keys")
    if len(set(rename_sources)) != len(rename_sources):
        raise StatusFieldConflictError("Status field renames contain duplicate source keys")
    if len(set(normalized_deletes)) != len(normalized_deletes):
        raise StatusFieldConflictError("Status field deletes contain duplicate keys")
    if set(rename_sources).intersection(normalized_deletes):
        raise StatusFieldConflictError(
            "A status field cannot be renamed and deleted in the same edit"
        )

    target_keys = create_keys + rename_targets
    if len(set(target_keys)) != len(target_keys):
        raise StatusFieldConflictError(
            "Status field create and rename targets must be unique"
        )

    rows_by_key = {row.key: row for row in current.rows}
    existing_keys = set(rows_by_key)
    for source_key in rename_sources + normalized_deletes:
        if source_key not in existing_keys:
            raise StatusFieldKeyNotFoundError(
                f"Status table key not found: {source_key}"
            )
        if rows_by_key[source_key].runtime_key_locked:
            raise StatusFieldLockedError(
                f"Status key is runtime locked: {source_key}"
            )
    conflicting_targets = [
        target_key for target_key in target_keys if target_key in existing_keys
    ]
    if conflicting_targets:
        raise StatusFieldConflictError(
            f"Status field target already exists: {conflicting_targets[0]}"
        )

    rename_by_source = dict(normalized_renames)
    deleted_keys = set(normalized_deletes)
    updated_rows: list[StatusTableRow] = []
    for row in current.rows:
        if row.key in deleted_keys:
            continue
        new_key = rename_by_source.get(row.key)
        if new_key is None:
            updated_rows.append(row)
            continue
        updated_rows.append(StatusTableRow(
            key=new_key,
            value=row.value,
            runtime_key_locked=row.runtime_key_locked,
            update_rule=row.update_rule,
            metadata=dict(row.metadata),
        ))
    updated_rows.extend(
        StatusTableRow(
            key=key,
            value=value,
            runtime_key_locked=False,
            update_rule="",
            metadata={},
        )
        for key, value in normalized_creates
    )
    updated = StatusTableDocument(
        schema_version=current.schema_version,
        kind=current.kind,
        mode=current.mode,
        key_column=current.key_column,
        value_column=current.value_column,
        rows=tuple(updated_rows),
        metadata=dict(current.metadata),
    ).validated()
    result = StatusFieldEditResult(
        table_id=int(table_id),
        table_name=str(table_name),
        created=tuple(
            StatusFieldCreated(key=key, value=value)
            for key, value in normalized_creates
        ),
        renamed=tuple(
            StatusFieldRenamed(key=key, new_key=new_key)
            for key, new_key in normalized_renames
        ),
        deleted=tuple(
            StatusFieldDeleted(key=key, old_value=rows_by_key[key].value)
            for key in normalized_deletes
        ),
    )
    return updated, result


__all__ = [
    "StatusFieldConflictError",
    "StatusFieldCreated",
    "StatusFieldDeleted",
    "StatusFieldEditError",
    "StatusFieldEditResult",
    "StatusFieldKeyNotFoundError",
    "StatusFieldLockedError",
    "StatusFieldRenamed",
    "StatusManager",
    "StatusRuntimeDataPort",
    "StatusValueChange",
    "StatusValueUpdateResult",
    "apply_status_field_edits",
    "collect_value_changes",
]
