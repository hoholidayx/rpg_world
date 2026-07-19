"""Data-layer history seeding for asynchronously derived sessions."""

from __future__ import annotations

import logging

from peewee import Database

from rpg_data import models
from rpg_data.repositories._utils import serialize_rp_module_config
from rpg_data.repositories.records import (
    SessionBackupMessageRecord,
    SessionMessageRecord,
    SessionRPModuleOverrideRecord,
    bind_database,
)
from rpg_data.repositories.rp_module_repo import RPModuleRepository
from rpg_data.repositories.session_derivation_repo import SessionDerivationRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.services.status import StatusTableService

__all__ = [
    "SessionDerivationDataError",
    "SessionDerivationProvisioningError",
    "SessionDerivationSourceBusyError",
    "SessionDerivationTargetBusyError",
    "SessionDerivationService",
]

logger = logging.getLogger("rpg_data.session_derivation")


class SessionDerivationDataError(ValueError):
    """A stable data-boundary failure suitable for service error mapping."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SessionDerivationSourceBusyError(SessionDerivationDataError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            "DERIVATION_SOURCE_BUSY",
            f"Session has an active derivation: {session_id}",
        )


class SessionDerivationTargetBusyError(SessionDerivationDataError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            "DERIVATION_TARGET_BUSY",
            f"Session is the target of an active derivation: {session_id}",
        )


class SessionDerivationProvisioningError(SessionDerivationDataError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            "DERIVATION_TARGET_PROVISIONING",
            f"Session is still provisioning: {session_id}",
        )


class SessionDerivationService:
    """Create jobs and seed provisioning sessions from mutable main history."""

    def __init__(
        self,
        database: Database,
        *,
        status: StatusTableService | None = None,
    ) -> None:
        self._database = database
        bind_database(database)
        self._jobs = SessionDerivationRepository(database)
        self._sessions = SessionRepository(database)
        self._rp_modules = RPModuleRepository(database)
        self._status = status or StatusTableService(database)

    def create_job(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        requested_title: str = "",
    ) -> models.SessionDerivationJob:
        turn_id = _positive_turn_id(branch_turn_id)
        with self._database.atomic():
            source = self._sessions.get(str(source_session_id))
            if source is None or source.lifecycle != models.SESSION_LIFECYCLE_READY:
                raise SessionDerivationDataError(
                    "DERIVATION_SOURCE_NOT_READY",
                    f"Ready source session not found: {source_session_id}",
                )
            self._require_complete_turn(source.id, turn_id)
            try:
                return self._jobs.create(
                    source.id,
                    turn_id,
                    requested_title=str(requested_title).strip(),
                )
            except ValueError as exc:
                raise SessionDerivationSourceBusyError(source.id) from exc

    def get_job(self, job_id: str) -> models.SessionDerivationJob | None:
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        *statuses: str,
    ) -> list[models.SessionDerivationJob]:
        for status in statuses:
            if status not in models.SESSION_DERIVATION_JOB_STATUSES:
                raise ValueError(f"Unsupported derivation status: {status}")
        return self._jobs.list_by_status(*statuses)

    def has_active_job(self, source_session_id: str) -> bool:
        return self._jobs.has_active_for_source(source_session_id)

    def start_job(self, job_id: str) -> models.SessionDerivationJob:
        updated = self._jobs.claim_queued(job_id)
        if updated is not None:
            return updated
        job = self._jobs.get(job_id)
        if job is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        if job.status != models.SESSION_DERIVATION_JOB_STATUS_QUEUED:
            raise SessionDerivationDataError(
                "DERIVATION_INVALID_STATE",
                f"Derivation job is not queued: {job.id}/{job.status}",
            )
        # A queued row that did not satisfy the conditional UPDATE changed
        # concurrently between the claim and this diagnostic read.
        raise SessionDerivationDataError(
            "DERIVATION_CLAIM_CONFLICT",
            f"Derivation job could not be claimed: {job.id}",
        )

    def set_stage(self, job_id: str, stage: str) -> models.SessionDerivationJob:
        job = self._require_running_job(job_id)
        if stage in {"queued", "ready", "failed", "interrupted"}:
            raise ValueError(f"Stage is not a running stage: {stage}")
        updated = self._jobs.update(job.id, stage=stage)
        if updated is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        return updated

    def seed_target_session(
        self,
        job_id: str,
    ) -> models.SessionDerivationSeedResult:
        with self._database.atomic():
            job = self._require_running_job(job_id)
            if job.target_session_id is not None:
                raise SessionDerivationDataError(
                    "DERIVATION_TARGET_ALREADY_CREATED",
                    f"Derivation target already exists: {job.target_session_id}",
                )
            # Source profile, history and session overrides must all come from
            # the same SQLite read snapshot as target creation.
            source = self._sessions.get(job.source_session_id)
            if source is None or source.lifecycle != models.SESSION_LIFECYCLE_READY:
                raise SessionDerivationDataError(
                    "DERIVATION_SOURCE_NOT_READY",
                    f"Ready source session not found: {job.source_session_id}",
                )
            messages = self._require_complete_turn(
                source.id,
                job.branch_turn_id,
                include_history=True,
            )
            title = job.requested_title or _derived_title(source.title)
            target = self._sessions.create(
                source.workspace_id,
                source.story_id,
                title=title,
                description="",
                player_character_id=source.player_character_id,
                player_character_snapshot_json=source.player_character_snapshot_json,
                story_opening_id=source.story_opening_id,
                lifecycle=models.SESSION_LIFECYCLE_PROVISIONING,
            )
            if source.main_llm_provider_key is not None:
                target = self._sessions.set_main_llm_provider_key(
                    target.id,
                    source.main_llm_provider_key,
                ) or target
            self._copy_rp_module_overrides(source.id, target.id)
            self._copy_messages(messages, target.id)
            self._status.initialize_session_tables(target.id)
            updated_job = self._jobs.update(
                job.id,
                target_session_id=target.id,
                stage="rebuilding_status",
            )
            if updated_job is None:
                raise RuntimeError(f"Derivation job disappeared: {job.id}")

        seeded = self._sessions.get(target.id)
        if seeded is None:
            raise RuntimeError(f"Seeded session disappeared: {target.id}")
        logger.info(
            "seeded derived session job_id=%s source_session_id=%s target_session_id=%s branch_turn_id=%s message_count=%s",
            job.id,
            source.id,
            seeded.id,
            job.branch_turn_id,
            len(messages),
        )
        return models.SessionDerivationSeedResult(
            job=updated_job,
            session=seeded,
            copied_message_count=len(messages),
        )

    def set_context_usage(
        self,
        job_id: str,
        *,
        used_tokens: int,
        context_limit: int,
        threshold_exceeded: bool,
    ) -> models.SessionDerivationJob:
        self._require_running_job(job_id)
        if int(used_tokens) < 0 or int(context_limit) <= 0:
            raise ValueError("Context usage must have used_tokens >= 0 and context_limit > 0")
        updated = self._jobs.update(
            job_id,
            context_used_tokens=int(used_tokens),
            context_limit=int(context_limit),
            context_threshold_exceeded=bool(threshold_exceeded),
        )
        if updated is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        return updated

    def complete_job(self, job_id: str) -> models.SessionDerivationJob:
        job = self._require_running_job(job_id)
        if job.target_session_id is None:
            raise SessionDerivationDataError(
                "DERIVATION_TARGET_MISSING",
                f"Derivation target has not been created: {job.id}",
            )
        with self._database.atomic():
            target = self._sessions.get(job.target_session_id)
            if target is None or target.lifecycle != models.SESSION_LIFECYCLE_PROVISIONING:
                raise SessionDerivationDataError(
                    "DERIVATION_TARGET_NOT_PROVISIONING",
                    f"Provisioning target session not found: {job.target_session_id}",
                )
            ready = self._sessions.set_lifecycle(
                target.id,
                models.SESSION_LIFECYCLE_READY,
            )
            if ready is None:
                raise RuntimeError(f"Derivation target disappeared: {target.id}")
            updated = self._jobs.update(
                job.id,
                status=models.SESSION_DERIVATION_JOB_STATUS_READY,
                stage="ready",
                error_code="",
                error_message="",
                finished=True,
            )
            if updated is None:
                raise RuntimeError(f"Derivation job disappeared: {job.id}")
        return updated

    def fail_job(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.SessionDerivationJob:
        job = self._require_job(job_id)
        if job.status not in {
            models.SESSION_DERIVATION_JOB_STATUS_QUEUED,
            models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
        }:
            raise SessionDerivationDataError(
                "DERIVATION_INVALID_STATE",
                f"Derivation job is already final: {job.id}/{job.status}",
            )
        self._require_target_absent(job)
        with self._database.atomic():
            updated = self._jobs.update(
                job.id,
                status=models.SESSION_DERIVATION_JOB_STATUS_FAILED,
                stage="failed",
                error_code=str(error_code),
                error_message=str(error_message),
                finished=True,
            )
            if updated is None:
                raise RuntimeError(f"Derivation job disappeared: {job.id}")
        return updated

    def interrupt_job(self, job_id: str) -> models.SessionDerivationJob:
        job = self._require_running_job(job_id)
        self._require_target_absent(job)
        with self._database.atomic():
            updated = self._jobs.update(
                job.id,
                status=models.SESSION_DERIVATION_JOB_STATUS_INTERRUPTED,
                stage="interrupted",
                error_code="DERIVATION_WORKER_RESTARTED",
                error_message="Derivation worker restarted while the job was running",
                finished=True,
            )
            if updated is None:
                raise RuntimeError(f"Derivation job disappeared: {job.id}")
        return updated

    def _require_target_absent(self, job: models.SessionDerivationJob) -> None:
        target_id = job.target_session_id
        if target_id is not None and self._sessions.get(target_id) is not None:
            raise SessionDerivationDataError(
                "DERIVATION_TARGET_CLEANUP_REQUIRED",
                f"Provisioning target must be quarantined before finalizing job: {target_id}",
            )

    def _require_job(self, job_id: str) -> models.SessionDerivationJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        return job

    def _require_running_job(self, job_id: str) -> models.SessionDerivationJob:
        job = self._require_job(job_id)
        if job.status != models.SESSION_DERIVATION_JOB_STATUS_RUNNING:
            raise SessionDerivationDataError(
                "DERIVATION_INVALID_STATE",
                f"Derivation job is not running: {job.id}/{job.status}",
            )
        return job

    @staticmethod
    def _require_complete_turn(
        session_id: str,
        turn_id: int,
        *,
        include_history: bool = False,
    ) -> list[SessionMessageRecord]:
        turn_rows = list(
            SessionMessageRecord.select()
            .where(
                (SessionMessageRecord.session == session_id)
                & (SessionMessageRecord.turn_id == turn_id)
            )
            .order_by(SessionMessageRecord.seq_in_turn, SessionMessageRecord.id)
        )
        if not turn_rows:
            raise SessionDerivationDataError(
                "DERIVATION_TURN_NOT_FOUND",
                f"Turn not found in current main history: {session_id}/{turn_id}",
            )
        sequences = [int(row.seq_in_turn) for row in turn_rows]
        has_non_increasing_sequence = any(
            current <= previous
            for previous, current in zip(sequences, sequences[1:])
        )
        if (
            has_non_increasing_sequence
            or str(turn_rows[-1].role) != models.MESSAGE_ROLE_ASSISTANT
        ):
            raise SessionDerivationDataError(
                "DERIVATION_TURN_INCOMPLETE",
                f"Turn is not a complete committed turn: {session_id}/{turn_id}",
            )
        if not include_history:
            return turn_rows
        return list(
            SessionMessageRecord.select()
            .where(
                (SessionMessageRecord.session == session_id)
                & (SessionMessageRecord.turn_id <= turn_id)
            )
            .order_by(
                SessionMessageRecord.turn_id,
                SessionMessageRecord.seq_in_turn,
                SessionMessageRecord.id,
            )
        )

    def _copy_rp_module_overrides(self, source_session_id: str, target_session_id: str) -> None:
        for override in self._rp_modules.list_session(source_session_id):
            SessionRPModuleOverrideRecord.create(
                session=target_session_id,
                module_name=override.module_name,
                enabled=override.enabled,
                config_json=serialize_rp_module_config(override.config),
            )

    @staticmethod
    def _copy_messages(messages: list[SessionMessageRecord], target_session_id: str) -> None:
        for source in messages:
            common = {
                "session": target_session_id,
                "role": str(source.role),
                "content": str(source.content),
                "mode": str(source.mode),
                "turn_id": int(source.turn_id),
                "seq_in_turn": int(source.seq_in_turn),
                "tool_call_id": str(source.tool_call_id),
                "tool_calls_json": str(source.tool_calls_json),
                "metadata_json": str(source.metadata_json),
                "version": 1,
                "created_at": str(source.created_at),
                "updated_at": str(source.updated_at),
            }
            SessionMessageRecord.create(
                **common,
                summary_processed=False,
                summary_batch_id=None,
                summary_processed_at=None,
                story_memory_processed=False,
                story_memory_processed_at=None,
            )
            SessionBackupMessageRecord.create(**common)


def _positive_turn_id(value: int) -> int:
    normalized = int(value)
    if normalized <= 0:
        raise SessionDerivationDataError(
            "DERIVATION_TURN_INVALID",
            "branch_turn_id must be a positive integer",
        )
    return normalized


def _derived_title(source_title: str) -> str:
    title = str(source_title).strip()
    return f"{title} - 分支" if title else "分支会话"
