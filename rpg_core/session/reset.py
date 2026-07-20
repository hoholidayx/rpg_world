"""Atomic Session gameplay reset application service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rpg_core.session.role import SessionRoleService
from rpg_core.session.status import SessionStatusLifecycleService

if TYPE_CHECKING:
    from rpg_data.services.gateway import DataServiceGateway


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

    def __init__(self, gateway: "DataServiceGateway") -> None:
        self._gateway = gateway

    def reset(self, session_id: str) -> SessionResetResult:
        normalized_session_id = str(session_id)
        if self._gateway.catalog.get_session(normalized_session_id) is None:
            raise FileNotFoundError(f"Session not found: {normalized_session_id}")

        with self._gateway.transaction():
            messages_cleared = self._gateway.messages.clear(normalized_session_id)
            outcomes_cleared = self._gateway.narrative_outcomes.clear(
                normalized_session_id
            )
            plot_decisions_cleared = self._gateway.plot_scheduling.clear_decisions(
                normalized_session_id
            )
            story_memories_cleared = self._gateway.story_memory.clear(
                normalized_session_id
            )
            dream_result = self._gateway.dream.clear(normalized_session_id)
            status_result = SessionStatusLifecycleService(self._gateway).reset(
                normalized_session_id
            )
            media_result = self._gateway.media.clear_session_runtime(
                normalized_session_id
            )
            opening_result = SessionRoleService(self._gateway).replay_opening_for_reset(
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
