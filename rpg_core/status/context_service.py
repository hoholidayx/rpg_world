"""Business policy for status-table character grouping and Context visibility."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Protocol

from rpg_data.model.status import (
    STATUS_ORIGIN_STORY_COPY,
    SessionStatusMetadata,
    SessionStatusTable,
    StatusContextCandidate,
    parse_session_status_metadata,
)

logger = logging.getLogger("rpg_core.status.context_service")


class StatusContextDataPort(Protocol):
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


class StatusContextService:
    """Resolve copied-table character identity before LLM Context rendering."""

    def __init__(self, data: StatusContextDataPort) -> None:
        self._data = data

    def list_tables(self, session_id: str) -> list[SessionStatusTable]:
        prepared: list[SessionStatusTable] = []
        for candidate in self._data.list_context_candidates(str(session_id)):
            table = self._prepare_candidate(candidate)
            if table is not None:
                prepared.append(table)
        return prepared

    def _prepare_candidate(
        self,
        candidate: StatusContextCandidate,
    ) -> SessionStatusTable | None:
        table = candidate.table
        if table.origin is not STATUS_ORIGIN_STORY_COPY:
            return table
        metadata = parse_session_status_metadata(table.metadata_json)
        source = metadata.story_source
        if source is None or not source.has_character_binding:
            return table
        if (source.character_name or "").strip():
            return table

        identity = candidate.referenced_character
        if (
            identity is None
            and source.character_id is not None
            and candidate.current_story_table is not None
            and source.story_status_table_id
            == candidate.current_story_table.story_status_table_id
        ):
            identity = candidate.current_story_table.character

        if (
            identity is None
            or not identity.character_name.strip()
            or (
                source.character_id is not None
                and identity.character_id != source.character_id
            )
        ):
            logger.warning(
                "excluded character-bound status table from context because "
                "character name is unresolved session_id=%s table_id=%s "
                "character_id=%s",
                table.session_id,
                table.id,
                source.character_id,
            )
            return None

        repaired_source = replace(
            source,
            character_id=identity.character_id,
            character_name=identity.character_name,
        )
        repaired = self._data.update_table_metadata_for_session(
            table.session_id,
            table.id,
            metadata.with_story_source(repaired_source),
        )
        logger.warning(
            "backfilled missing status table character name session_id=%s "
            "table_id=%s character_id=%s character_name=%s",
            table.session_id,
            table.id,
            identity.character_id,
            identity.character_name,
        )
        return repaired


__all__ = [
    "StatusContextDataPort",
    "StatusContextService",
]
