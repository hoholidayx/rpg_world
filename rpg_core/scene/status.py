"""Scene status-table policy and active-table selection."""

from __future__ import annotations

from typing import Protocol

from rpg_data.model.status import (
    STATUS_KIND_SCENE,
    STATUS_UPDATE_FREQUENCY_REALTIME,
    SessionStatusTable,
    StatusKind,
    StatusTableDocument,
    StatusTableRow,
    validate_status_kind,
)

SCENE_TIME_ATTR = "时间"
SCENE_LOCATION_ATTR = "位置"
SCENE_PRESENT_CHARACTERS_ATTR = "在场人物"
SCENE_DEFAULT_LOCKED_KEYS = frozenset({
    SCENE_TIME_ATTR,
    SCENE_LOCATION_ATTR,
    SCENE_PRESENT_CHARACTERS_ATTR,
})


class SceneStatusDataPort(Protocol):
    def list_tables(
        self,
        session_id: str,
        status_kind: str | None = None,
    ) -> list[SessionStatusTable]: ...


class SceneStatusPolicyError(ValueError):
    """A Scene document violates runtime-facing Scene policy."""


class SceneStatusService:
    """Own Scene document rules and active Scene interpretation."""

    def __init__(self, data: SceneStatusDataPort) -> None:
        self._data = data

    def get_active_table(self, session_id: str) -> SessionStatusTable | None:
        tables = self._data.list_tables(
            str(session_id),
            status_kind=STATUS_KIND_SCENE,
        )
        return tables[0] if tables else None

    def get_attrs(self, session_id: str) -> dict[str, str] | None:
        table = self.get_active_table(session_id)
        return None if table is None else document_attrs(table.document)

    @staticmethod
    def prepare_document(
        status_kind: str | StatusKind,
        document: StatusTableDocument,
    ) -> StatusTableDocument:
        kind = validate_status_kind(status_kind)
        if kind is not STATUS_KIND_SCENE:
            return document.validated()
        rows = tuple(
            StatusTableRow(
                key=row.key,
                value=row.value,
                runtime_key_locked=(
                    row.runtime_key_locked or row.key in SCENE_DEFAULT_LOCKED_KEYS
                ),
                metadata=dict(row.metadata),
                update_frequency=row.update_frequency,
                update_rule=row.update_rule,
                deferred_interval_turns=row.deferred_interval_turns,
            )
            for row in document.rows
        )
        if any(
            row.update_frequency is not STATUS_UPDATE_FREQUENCY_REALTIME
            for row in rows
        ):
            raise SceneStatusPolicyError(
                "scene status fields must use realtime updateFrequency"
            )
        return StatusTableDocument(
            schema_version=document.schema_version,
            kind=document.kind,
            mode=document.mode,
            key_column=document.key_column,
            value_column=document.value_column,
            rows=rows,
            metadata=dict(document.metadata),
        ).validated()


def document_attrs(document: StatusTableDocument) -> dict[str, str]:
    return {row.key: row.value for row in document.rows}


__all__ = [
    "SCENE_DEFAULT_LOCKED_KEYS",
    "SCENE_LOCATION_ATTR",
    "SCENE_PRESENT_CHARACTERS_ATTR",
    "SCENE_TIME_ATTR",
    "SceneStatusDataPort",
    "SceneStatusPolicyError",
    "SceneStatusService",
    "document_attrs",
]
