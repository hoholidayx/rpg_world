"""Atomic Session gameplay reset application service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ContextManager, Protocol

from rpg_core.session.role import SessionRoleDataPort, SessionRoleService
from rpg_core.session.status import (
    SessionStatusDataPort,
    SessionStatusLifecycleService,
)
from rpg_data import models as data_models
from rpg_data.model.memory import DreamResetResult
from rpg_data.model.session import Session


class SessionResetDataPort(SessionRoleDataPort, SessionStatusDataPort, Protocol):
    def transaction(self) -> ContextManager[None]: ...

    def get_session(self, session_id: str) -> Session | None: ...

    def clear_messages(self, session_id: str) -> int: ...

    def clear_narrative_outcomes(self, session_id: str) -> int: ...

    def clear_plot_decisions(self, session_id: str) -> int: ...

    def clear_story_memories(self, session_id: str) -> int: ...

    def clear_dream_memory(self, session_id: str) -> DreamResetResult: ...

    def clear_media_runtime(
        self,
        session_id: str,
    ) -> data_models.SessionMediaResetResult: ...


@dataclass(frozen=True)
class SessionResetResult:
    session_id: str
    messages_cleared: int = 0
    narrative_outcomes_cleared: int = 0
    plot_schedule_decisions_cleared: int = 0
    story_memories_cleared: int = 0
    dream_memories_cleared: int = 0
    dream_proposals_cleared: int = 0
    template_status_tables_cleared: int = 0
    template_status_tables_initialized: int = 0
    session_native_status_tables_reset: int = 0
    deferred_progress_cleared: int = 0
    media_jobs_cleared: int = 0
    media_gallery_items_cleared: int = 0
    media_backgrounds_cleared: int = 0
    first_message: str = ""


class SessionResetService:
    """Choose and atomically apply the complete ``/clear`` mutation matrix."""

    def __init__(self, data: SessionResetDataPort) -> None:
        self._data = data

    def reset(self, session_id: str) -> SessionResetResult:
        normalized_session_id = str(session_id)
        if self._data.get_session(normalized_session_id) is None:
            raise FileNotFoundError(f"Session not found: {normalized_session_id}")

        with self._data.transaction():
            messages_cleared = self._data.clear_messages(normalized_session_id)
            outcomes_cleared = self._data.clear_narrative_outcomes(
                normalized_session_id
            )
            plot_decisions_cleared = self._data.clear_plot_decisions(
                normalized_session_id
            )
            story_memories_cleared = self._data.clear_story_memories(
                normalized_session_id
            )
            dream_result = self._data.clear_dream_memory(normalized_session_id)
            status_result = SessionStatusLifecycleService(self._data).reset(
                normalized_session_id
            )
            media_result = self._data.clear_media_runtime(
                normalized_session_id
            )
            opening_result = SessionRoleService(self._data).replay_opening_for_reset(
                normalized_session_id
            )

        return SessionResetResult(
            session_id=normalized_session_id,
            messages_cleared=messages_cleared,
            narrative_outcomes_cleared=outcomes_cleared,
            plot_schedule_decisions_cleared=plot_decisions_cleared,
            story_memories_cleared=story_memories_cleared,
            dream_memories_cleared=dream_result.memories_cleared,
            dream_proposals_cleared=dream_result.proposals_cleared,
            template_status_tables_cleared=status_result.template_tables_cleared,
            template_status_tables_initialized=(
                status_result.template_tables_initialized
            ),
            session_native_status_tables_reset=status_result.native_tables_reset,
            deferred_progress_cleared=status_result.deferred_progress_cleared,
            media_jobs_cleared=media_result.jobs_cleared,
            media_gallery_items_cleared=media_result.gallery_items_cleared,
            media_backgrounds_cleared=media_result.backgrounds_cleared,
            first_message=opening_result.first_message,
        )


__all__ = ["SessionResetResult", "SessionResetService"]
