"""Atomic reset of mutable runtime data owned by one catalog session."""

from __future__ import annotations

from peewee import Database

from rpg_data import models
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.services.dream_memory import DreamMemoryService
from rpg_data.services.message import MessageService
from rpg_data.services.media import MediaDataService
from rpg_data.services.narrative_outcome import NarrativeOutcomeService
from rpg_data.services.plot_scheduling import PlotSchedulingService
from rpg_data.services.session_role import SessionRoleService
from rpg_data.services.story_memory import StoryMemoryService
from rpg_data.services.status import StatusTableService

__all__ = ["SessionResetService"]


class SessionResetService:
    """Reset gameplay data while preserving the catalog session and profile."""

    def __init__(
        self,
        database: Database,
        *,
        messages: MessageService | None = None,
        narrative_outcomes: NarrativeOutcomeService | None = None,
        plot_scheduling: PlotSchedulingService | None = None,
        session_roles: SessionRoleService | None = None,
        story_memory: StoryMemoryService | None = None,
        dream: DreamMemoryService | None = None,
        status: StatusTableService | None = None,
        media: MediaDataService | None = None,
    ) -> None:
        self._database = database
        self._sessions = SessionRepository(database)
        self._messages = messages or MessageService(database)
        self._narrative_outcomes = narrative_outcomes or NarrativeOutcomeService(database)
        self._plot_scheduling = plot_scheduling or PlotSchedulingService(database)
        self._session_roles = session_roles or SessionRoleService(database)
        self._story_memory = story_memory or StoryMemoryService(database)
        self._dream = dream or DreamMemoryService(database)
        self._status = status or StatusTableService(database)
        self._media = media or MediaDataService(database)

    def reset(self, session_id: str) -> models.SessionResetResult:
        """Clear mutable gameplay rows and recreate status copies atomically.

        Existing append-only backup history and session profile/configuration
        are preserved. A newly rendered Story opening may be appended.
        """

        normalized_session_id = str(session_id)
        if self._sessions.get(normalized_session_id) is None:
            raise FileNotFoundError(f"Session not found: {normalized_session_id}")

        with self._database.atomic():
            messages_cleared = self._messages.clear(normalized_session_id)
            outcomes_cleared = self._narrative_outcomes.clear(normalized_session_id)
            plot_decisions_cleared = self._plot_scheduling.clear_session_decisions(
                normalized_session_id
            )
            story_memories_cleared = self._story_memory.clear(normalized_session_id)
            dream_result = self._dream.clear(normalized_session_id)
            status_result = self._status.reset_session_tables(
                normalized_session_id
            )
            media_result = self._media.clear_session_runtime(normalized_session_id)
            first_message = self._session_roles.append_first_message_for_reset(
                normalized_session_id
            )

        return models.SessionResetResult(
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
            first_message=first_message,
        )
