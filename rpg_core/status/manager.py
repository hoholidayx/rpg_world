"""Thin agent-facing adapter for session status tables."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from rpg_data.models import STATUS_KEY_COLUMN, STATUS_VALUE_COLUMN, StatusRowRef
from rpg_data.services import get_data_service_gateway

if TYPE_CHECKING:
    from rpg_data.models import SessionStatusTable
    from rpg_data.services.status import StatusTableService


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
        return [
            status_type.name
            for status_type in self._service.list_session_types(self.session_id)
        ]

    def list_tables(self, type_name: str) -> list[str]:
        return [
            table.name
            for table in self._service.list_tables(self.session_id, type_name)
        ]

    def list_context_tables(self) -> list[dict[str, object]]:
        return [
            _table_to_dict(table)
            for table in self._service.list_context_tables(self.session_id)
        ]

    def get_table(self, type_name: str, table_name: str) -> dict[str, object]:
        return _table_to_dict(
            self._service.get_table(self.session_id, type_name, table_name)
        )

    def get_table_by_id(self, table_id: int) -> dict[str, object]:
        return _table_to_dict(self._service.get_table_by_id(table_id))

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
        return table.id, (table.type_name, table.name)

    def get_scene_attrs(self) -> dict[str, str] | None:
        return self._service.get_scene_attrs(self.session_id)


def _table_to_dict(table: "SessionStatusTable") -> dict[str, object]:
    return table.to_dict()
