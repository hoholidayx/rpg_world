"""Typed CRUD facade for Session derivation jobs and copy primitives."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from peewee import Database, IntegrityError

from rpg_data import models
from rpg_data.repositories._utils import serialize_rp_module_config
from rpg_data.repositories.records import (
    SessionBackupMessageRecord,
    SessionMessageRecord,
    SessionRPModuleOverrideRecord,
    bind_database,
)
from rpg_data.repositories.session_derivation_repo import SessionDerivationRepository

__all__ = [
    "SessionDerivationDataConflictError",
    "SessionDerivationDataService",
]


class SessionDerivationDataConflictError(RuntimeError):
    """A conditional or unique derivation-ledger write was rejected."""


class SessionDerivationDataService:
    """Persist derivation rows and caller-selected Session data copies."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)
        self._jobs = SessionDerivationRepository(database)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._database.atomic():
            yield

    def create_job(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        requested_title: str = "",
    ) -> models.SessionDerivationJob:
        try:
            return self._jobs.create(
                str(source_session_id),
                int(branch_turn_id),
                requested_title=str(requested_title),
            )
        except IntegrityError as exc:
            raise SessionDerivationDataConflictError(
                "derivation job write violated data constraints"
            ) from exc

    def get_job(self, job_id: str) -> models.SessionDerivationJob | None:
        return self._jobs.get(str(job_id))

    def list_jobs(self, *statuses: str) -> list[models.SessionDerivationJob]:
        for status in statuses:
            if status not in models.SESSION_DERIVATION_JOB_STATUSES:
                raise ValueError(f"Unsupported derivation status: {status}")
        return self._jobs.list_by_status(*statuses)

    def has_active_for_source(self, session_id: str) -> bool:
        return self._jobs.has_active_for_source(str(session_id))

    def has_active_for_target(self, session_id: str) -> bool:
        return self._jobs.has_active_for_target(str(session_id))

    def update_job(
        self,
        job_id: str,
        update: models.SessionDerivationJobUpdate,
    ) -> models.SessionDerivationJob | None:
        return self._jobs.update(str(job_id), update)

    def update_job_if_status(
        self,
        job_id: str,
        expected_status: str,
        update: models.SessionDerivationJobUpdate,
    ) -> models.SessionDerivationJob | None:
        return self._jobs.update_if_status(
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
            SessionMessageRecord
            .select()
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
        overrides: Iterable[models.SessionRPModuleOverride],
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
