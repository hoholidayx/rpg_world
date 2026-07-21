"""Typed persistence service for the Session business aggregate."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Mapping

from peewee import Database, IntegrityError

from commons.types import JsonValue
from rpg_data import models
from rpg_data.model.status import (
    SessionStatusResetPlan,
    SessionStatusResetResult,
    SessionStatusTable,
    StoryStatusTable,
)
from rpg_data.model.rp_modules import SessionRPModuleOverride
from rpg_data.services._message_store import MessageInput
from rpg_data.repositories._utils import (
    serialize_rp_module_config,
    to_story_opening,
)
from rpg_data.repositories.records import (
    CharacterRecord,
    SessionBackupMessageRecord,
    SessionMessageRecord,
    SessionRPModuleOverrideRecord,
    StoryCharacterRecord,
    StoryOpeningRecord,
    bind_database,
)
from rpg_data.repositories.session_derivation_repo import (
    SessionDerivationRepository,
)
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.services.backup import BackupService
from rpg_data.services.catalog import CatalogService
from rpg_data.services.dream_memory import DreamMemoryDataService
from rpg_data.services.media import MediaDataService
from rpg_data.services.message import MessageDataService
from rpg_data.services.narrative_outcome import NarrativeOutcomeDataService
from rpg_data.services.plot_scheduling import PlotSchedulingDataService
from rpg_data.services.rp_modules import RPModuleDataService
from rpg_data.services.session_composer import SessionComposerDataService
from rpg_data.services.status import StatusDataService
from rpg_data.services.story_memory import StoryMemoryDataService

__all__ = [
    "SessionDataConflictError",
    "SessionDataService",
]


class SessionDataConflictError(RuntimeError):
    """A conditional or unique Session write was rejected."""


class SessionDataService:
    """Aggregate typed Session persistence without owning Session policy."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)
        self._sessions = SessionRepository(database)
        self._derivations = SessionDerivationRepository(database)
        self._catalog = CatalogService(database)
        self._messages = MessageDataService(database)
        self._backup = BackupService(database)
        self._outcomes = NarrativeOutcomeDataService(database)
        self._plot = PlotSchedulingDataService(database)
        self._rp_modules = RPModuleDataService(database)
        self._composer = SessionComposerDataService(database)
        self._story_memory = StoryMemoryDataService(database)
        self._dream_memory = DreamMemoryDataService(database)
        self._status = StatusDataService(database)
        self._media = MediaDataService(database)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._database.atomic():
            yield

    # Catalog primitives -------------------------------------------------

    def get_story(self, workspace_id: str, story_id: int) -> models.Story | None:
        return self._catalog.get_story(str(workspace_id), int(story_id))

    def list_sessions(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.Session] | None:
        return self._catalog.list_sessions(str(workspace_id), int(story_id))

    def create_story(
        self,
        workspace_id: str,
        *,
        title: str,
        summary: str = "",
        story_prompt: str = "",
        openings: Sequence[models.StoryOpeningInput] = (),
    ) -> models.Story | None:
        return self._catalog.create_story(
            str(workspace_id),
            title=title,
            summary=summary,
            story_prompt=story_prompt,
            openings=openings,
        )

    def update_story(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        story_prompt: str | None = None,
        openings: Sequence[models.StoryOpeningInput] | None = None,
    ) -> models.Story | None:
        return self._catalog.update_story(
            str(workspace_id),
            int(story_id),
            title=title,
            summary=summary,
            story_prompt=story_prompt,
            openings=openings,
        )

    def create_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        session_id: str | None = None,
        title: str = "",
        description: str = "",
        player_character_id: int | None = None,
        player_character_snapshot_json: str = "{}",
        story_opening_id: int | None = None,
        lifecycle: str = models.SESSION_LIFECYCLE_READY,
    ) -> models.Session | None:
        return self._catalog.create_session(
            str(workspace_id),
            int(story_id),
            session_id=session_id,
            title=title,
            description=description,
            player_character_id=player_character_id,
            player_character_snapshot_json=player_character_snapshot_json,
            story_opening_id=story_opening_id,
            lifecycle=lifecycle,
        )

    def get_session(self, session_id: str) -> models.Session | None:
        return self._catalog.get_session(str(session_id))

    def get_session_story(self, session_id: str) -> models.Story | None:
        return self._catalog.get_session_story(str(session_id))

    def set_session_main_llm_provider_key(
        self,
        session_id: str,
        provider_key: str | None,
    ) -> models.Session | None:
        return self._catalog.set_session_main_llm_provider_key(
            str(session_id),
            provider_key,
        )

    def set_session_lifecycle(
        self,
        session_id: str,
        lifecycle: str,
    ) -> models.Session | None:
        return self._catalog.set_session_lifecycle(str(session_id), str(lifecycle))

    def resolve_session_runtime_dir(self, session_id: str) -> Path:
        return self._catalog.resolve_session_runtime_dir(str(session_id))

    def list_rp_module_catalog(self) -> list[models.RPModuleCatalogEntry]:
        return self._rp_modules.list_catalog()

    def set_story_rp_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
        *,
        enabled: bool,
        config: Mapping[str, JsonValue],
    ) -> models.StoryRPModule | None:
        return self._rp_modules.upsert_story_module(
            str(workspace_id),
            int(story_id),
            module_name,
            enabled=enabled,
            config=config,
        )

    def list_narrative_styles(
        self,
        workspace_id: str,
    ) -> list[models.NarrativeStyle] | None:
        return self._composer.list_styles(str(workspace_id))

    def mount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        style_id: int,
    ) -> models.StoryNarrativeStyle | None:
        return self._composer.mount_story_style(
            str(workspace_id),
            int(story_id),
            int(style_id),
        )

    # Player role and Opening primitives --------------------------------

    def list_character_mounts(
        self,
        session_id: str,
    ) -> list[models.SessionCharacterMount]:
        session = self._require_session(session_id)
        rows = (
            StoryCharacterRecord.select(StoryCharacterRecord, CharacterRecord)
            .join(CharacterRecord)
            .where(
                (StoryCharacterRecord.workspace == session.workspace_id)
                & (StoryCharacterRecord.story == session.story_id)
            )
            .order_by(StoryCharacterRecord.sort_order, StoryCharacterRecord.id)
        )
        return [
            models.SessionCharacterMount(
                workspace_id=str(row.workspace_id),
                story_id=int(row.story_id),
                mount_id=int(row.id),
                character_id=int(row.character_id),
                name=str(row.character.name),
                personality=str(row.character.personality or ""),
                content=str(row.character.content or ""),
                metadata_json=str(row.character.metadata_json or "{}"),
                character_updated_at=str(row.character.updated_at),
            )
            for row in rows
        ]

    def list_story_openings(self, session_id: str) -> list[models.StoryOpening]:
        session = self._require_session(session_id)
        rows = (
            StoryOpeningRecord.select()
            .where(StoryOpeningRecord.story == int(session.story_id))
            .order_by(StoryOpeningRecord.sort_order, StoryOpeningRecord.id)
        )
        return [to_story_opening(row) for row in rows]

    def count_messages(self, session_id: str) -> int:
        return self._messages.count(str(session_id))

    def list_messages(self, session_id: str) -> list[models.SessionMessage]:
        return self._messages.list(str(session_id))

    def list_messages_filtered(
        self,
        session_id: str,
        *,
        excluded_roles: Collection[str] = (),
        summary_processed: bool | None = None,
        story_memory_processed: bool | None = None,
    ) -> list[models.SessionMessage]:
        return self._messages.list_filtered(
            str(session_id),
            excluded_roles=excluded_roles,
            summary_processed=summary_processed,
            story_memory_processed=story_memory_processed,
        )

    def count_message_turns_filtered(
        self,
        session_id: str,
        *,
        excluded_roles: Collection[str] = (),
        summary_processed: bool | None = None,
        story_memory_processed: bool | None = None,
    ) -> int:
        return self._messages.count_distinct_turns(
            str(session_id),
            excluded_roles=excluded_roles,
            summary_processed=summary_processed,
            story_memory_processed=story_memory_processed,
        )

    def latest_message_turn_id(self, session_id: str) -> int:
        return self._messages.latest_turn_id(str(session_id))

    def get_message_for_session(
        self,
        session_id: str,
        message_id: int,
    ) -> models.SessionMessage | None:
        return self._messages.get_for_session(str(session_id), int(message_id))

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        mode: str,
        turn_id: int,
        seq_in_turn: int,
        metadata_json: str,
    ) -> models.SessionMessage:
        return self._messages.append(
            str(session_id),
            role,
            content,
            mode=mode,
            turn_id=turn_id,
            seq_in_turn=seq_in_turn,
            metadata_json=metadata_json,
        )

    def append_backup_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        mode: str,
        turn_id: int,
        seq_in_turn: int,
        metadata_json: str,
    ) -> models.SessionMessage:
        return self._backup.messages.append(
            str(session_id),
            role,
            content,
            mode=mode,
            turn_id=turn_id,
            seq_in_turn=seq_in_turn,
            metadata_json=metadata_json,
        )

    def update_message_content(
        self,
        message_id: int,
        content: str,
    ) -> models.SessionMessage | None:
        return self._messages.update(int(message_id), content=str(content))

    def delete_message_for_session(self, session_id: str, message_id: int) -> bool:
        return self._messages.delete_for_session(str(session_id), int(message_id))

    def replace_messages(
        self,
        session_id: str,
        messages: Iterable[MessageInput],
    ) -> list[models.SessionMessage]:
        return self._messages.replace(str(session_id), messages)

    def truncate_messages_before_id(self, session_id: str, boundary_id: int) -> int:
        return self._messages.truncate_before_id(
            str(session_id),
            int(boundary_id),
        )

    def truncate_messages_from_turn(self, session_id: str, turn_id: int) -> int:
        return self._messages.truncate_from_turn(str(session_id), int(turn_id))

    def mark_summary_messages_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
        *,
        batch_id: int | None,
    ) -> int:
        return self._messages.mark_summary_processed(
            str(session_id),
            message_ids,
            batch_id=batch_id,
        )

    def mark_summary_message_batches_processed(
        self,
        session_id: str,
        batches: Iterable[tuple[Iterable[int], int]],
    ) -> int:
        return self._messages.mark_summary_batches_processed(str(session_id), batches)

    def mark_story_memory_messages_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int:
        return self._messages.mark_story_memory_processed(
            str(session_id),
            message_ids,
        )

    def reset_message_processing(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int:
        return self._messages.reset_processing_for_messages(
            str(session_id),
            message_ids,
        )

    def delete_narrative_outcomes_for_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int:
        return self._outcomes.delete_for_turn(str(session_id), int(turn_id))

    def delete_narrative_outcomes_from_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int:
        return self._outcomes.delete_from_turn(str(session_id), int(turn_id))

    def retain_narrative_outcome_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> int:
        return self._outcomes.retain_turns(str(session_id), turn_ids)

    def delete_plot_decisions_for_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int:
        return self._plot.delete_decisions_for_turn(str(session_id), int(turn_id))

    def delete_plot_decisions_from_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int:
        return self._plot.delete_decisions_from_turn(str(session_id), int(turn_id))

    def retain_plot_decision_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> int:
        return self._plot.retain_decision_turns(str(session_id), turn_ids)

    def update_player_character(
        self,
        session_id: str,
        *,
        player_character_id: int,
        player_character_snapshot_json: str,
    ) -> models.Session | None:
        return self._sessions.update_player_character(
            str(session_id),
            player_character_id=int(player_character_id),
            player_character_snapshot_json=str(player_character_snapshot_json),
        )

    def update_player_character_and_opening(
        self,
        session_id: str,
        *,
        player_character_id: int,
        player_character_snapshot_json: str,
        story_opening_id: int | None,
    ) -> models.Session | None:
        return self._sessions.update_player_character_and_opening(
            str(session_id),
            player_character_id=int(player_character_id),
            player_character_snapshot_json=str(player_character_snapshot_json),
            story_opening_id=(
                int(story_opening_id) if story_opening_id is not None else None
            ),
        )

    def update_story_opening(
        self,
        session_id: str,
        story_opening_id: int | None,
    ) -> models.Session | None:
        return self._sessions.update_story_opening(
            str(session_id),
            int(story_opening_id) if story_opening_id is not None else None,
        )

    # Status lifecycle primitives ---------------------------------------

    def list_status_tables(
        self,
        session_id: str,
    ) -> list[SessionStatusTable]:
        return self._status.list_tables(str(session_id))

    def list_story_status_mounts(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryStatusTable]:
        return self._status.list_story_mounts(str(workspace_id), int(story_id))

    def copy_story_status_mounts(
        self,
        session_id: str,
        mount_ids: Iterable[int],
    ) -> list[SessionStatusTable]:
        return self._status.copy_story_mounts_to_session(
            str(session_id),
            mount_ids,
        )

    def apply_status_reset_plan(
        self,
        session_id: str,
        plan: SessionStatusResetPlan,
    ) -> SessionStatusResetResult:
        return self._status.apply_session_reset_plan(str(session_id), plan)

    # Reset primitives ---------------------------------------------------

    def clear_messages(self, session_id: str) -> int:
        return self._messages.clear(str(session_id))

    def clear_narrative_outcomes(self, session_id: str) -> int:
        return self._outcomes.clear(str(session_id))

    def clear_plot_decisions(self, session_id: str) -> int:
        return self._plot.clear_decisions(str(session_id))

    def clear_story_memories(self, session_id: str) -> int:
        return self._story_memory.clear(str(session_id))

    def clear_dream_memory(self, session_id: str) -> models.DreamResetResult:
        return self._dream_memory.clear(str(session_id))

    def clear_media_runtime(self, session_id: str) -> models.SessionMediaResetResult:
        return self._media.clear_session_runtime(str(session_id))

    # Derivation primitives ---------------------------------------------

    def create_derivation_job(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        requested_title: str = "",
    ) -> models.SessionDerivationJob:
        try:
            return self._derivations.create(
                str(source_session_id),
                int(branch_turn_id),
                requested_title=str(requested_title),
            )
        except IntegrityError as exc:
            raise SessionDataConflictError(
                "derivation job write violated data constraints"
            ) from exc

    def get_derivation_job(
        self,
        job_id: str,
    ) -> models.SessionDerivationJob | None:
        return self._derivations.get(str(job_id))

    def list_derivation_jobs(
        self,
        *statuses: str,
    ) -> list[models.SessionDerivationJob]:
        for status in statuses:
            if status not in models.SESSION_DERIVATION_JOB_STATUSES:
                raise ValueError(f"Unsupported derivation status: {status}")
        return self._derivations.list_by_status(*statuses)

    def has_active_derivation_for_source(self, session_id: str) -> bool:
        return self._derivations.has_active_for_source(str(session_id))

    def has_active_derivation_for_target(self, session_id: str) -> bool:
        return self._derivations.has_active_for_target(str(session_id))

    def update_derivation_job(
        self,
        job_id: str,
        update: models.SessionDerivationJobUpdate,
    ) -> models.SessionDerivationJob | None:
        return self._derivations.update(str(job_id), update)

    def update_derivation_job_if_status(
        self,
        job_id: str,
        expected_status: str,
        update: models.SessionDerivationJobUpdate,
    ) -> models.SessionDerivationJob | None:
        return self._derivations.update_if_status(
            str(job_id),
            str(expected_status),
            update,
        )

    def list_messages_through_turn(
        self,
        session_id: str,
        through_turn_id: int,
    ) -> list[models.SessionMessage]:
        rows = (
            SessionMessageRecord.select()
            .where(
                (SessionMessageRecord.session == str(session_id))
                & (SessionMessageRecord.turn_id <= int(through_turn_id))
            )
            .order_by(
                SessionMessageRecord.turn_id,
                SessionMessageRecord.seq_in_turn,
                SessionMessageRecord.id,
            )
        )
        return [_to_session_message(row) for row in rows]

    def copy_messages(
        self,
        target_session_id: str,
        messages: Iterable[models.SessionMessage],
    ) -> int:
        copied = 0
        for source in messages:
            _insert_message_copy(
                SessionMessageRecord,
                str(target_session_id),
                source,
                include_processing=True,
            )
            _insert_message_copy(
                SessionBackupMessageRecord,
                str(target_session_id),
                source,
                include_processing=False,
            )
            copied += 1
        return copied

    @staticmethod
    def copy_rp_module_overrides(
        target_session_id: str,
        overrides: Iterable[SessionRPModuleOverride],
    ) -> int:
        copied = 0
        for override in overrides:
            SessionRPModuleOverrideRecord.create(
                session=str(target_session_id),
                module_name=override.module_name,
                enabled=override.enabled,
                config_json=serialize_rp_module_config(override.config),
            )
            copied += 1
        return copied

    def list_session_rp_module_overrides(
        self,
        session_id: str,
    ) -> list[SessionRPModuleOverride] | None:
        return self._rp_modules.list_session_overrides(str(session_id))

    def copy_plot_overrides(
        self,
        source_session_id: str,
        target_session_id: str,
    ) -> None:
        self._plot.copy_overrides(str(source_session_id), str(target_session_id))

    def copy_plot_decisions(
        self,
        source_session_id: str,
        target_session_id: str,
        through_turn_id: int,
        *,
        decision_statuses: Collection[str],
    ) -> int:
        return self._plot.copy_decisions(
            str(source_session_id),
            str(target_session_id),
            int(through_turn_id),
            decision_statuses=decision_statuses,
        )

    # Conditional deletion primitives ----------------------------------

    def delete_session(self, session_id: str) -> bool:
        return self._sessions.delete(str(session_id))

    def delete_ready_without_active_derivation(self, session_id: str) -> bool:
        return self._sessions.delete_ready_without_active_derivation(
            str(session_id)
        )

    def delete_provisioning_for_derivation(
        self,
        session_id: str,
        job_id: str,
    ) -> bool:
        return self._sessions.delete_provisioning_for_derivation(
            str(session_id),
            str(job_id),
        )

    def _require_session(self, session_id: str) -> models.Session:
        session = self._sessions.get(str(session_id))
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return session


def _insert_message_copy(
    record_type: type[SessionMessageRecord] | type[SessionBackupMessageRecord],
    target_session_id: str,
    source: models.SessionMessage,
    *,
    include_processing: bool,
) -> None:
    if include_processing:
        record_type.create(
            session=target_session_id,
            role=source.role,
            content=source.content,
            mode=source.mode,
            turn_id=source.turn_id,
            seq_in_turn=source.seq_in_turn,
            tool_call_id=source.tool_call_id,
            tool_calls_json=source.tool_calls_json,
            metadata_json=source.metadata_json,
            summary_processed=False,
            summary_batch_id=None,
            summary_processed_at=None,
            story_memory_processed=False,
            story_memory_processed_at=None,
            version=1,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
        return
    record_type.create(
        session=target_session_id,
        role=source.role,
        content=source.content,
        mode=source.mode,
        turn_id=source.turn_id,
        seq_in_turn=source.seq_in_turn,
        tool_call_id=source.tool_call_id,
        tool_calls_json=source.tool_calls_json,
        metadata_json=source.metadata_json,
        version=1,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _to_session_message(row: SessionMessageRecord) -> models.SessionMessage:
    return models.SessionMessage(
        id=int(row.id),
        session_id=str(row.session_id),
        role=str(row.role),
        content=str(row.content),
        mode=str(row.mode),
        turn_id=int(row.turn_id),
        seq_in_turn=int(row.seq_in_turn),
        tool_call_id=str(row.tool_call_id),
        tool_calls_json=str(row.tool_calls_json),
        metadata_json=str(row.metadata_json),
        summary_processed=bool(row.summary_processed),
        summary_batch_id=(
            int(row.summary_batch_id) if row.summary_batch_id is not None else None
        ),
        summary_processed_at=str(row.summary_processed_at or ""),
        story_memory_processed=bool(row.story_memory_processed),
        story_memory_processed_at=str(row.story_memory_processed_at or ""),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )
