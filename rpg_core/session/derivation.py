"""Session derivation state machine and inheritance application service."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import ContextManager, Protocol

from rpg_core.rp_modules.plot_scheduler.ledger import PLOT_DERIVATION_COPY_POLICY
from rpg_core.session.catalog import SessionCatalogDataPort, SessionCatalogService
from rpg_data import models as data_models
from rpg_data.model.session import (
    MESSAGE_ROLE_ASSISTANT,
    SESSION_LIFECYCLE_PROVISIONING,
    SESSION_LIFECYCLE_READY,
    Session,
    SessionDerivationJob,
    SessionDerivationJobUpdate,
    SessionMessage,
)
from rpg_data.services.session import SessionDataConflictError


class SessionDerivationDataPort(SessionCatalogDataPort, Protocol):
    def transaction(self) -> ContextManager[None]: ...

    def create_derivation_job(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        requested_title: str,
    ) -> SessionDerivationJob: ...

    def get_derivation_job(
        self,
        job_id: str,
    ) -> SessionDerivationJob | None: ...

    def list_derivation_jobs(
        self,
        *statuses: str,
    ) -> list[SessionDerivationJob]: ...

    def has_active_derivation_for_source(self, session_id: str) -> bool: ...

    def update_derivation_job(
        self,
        job_id: str,
        update: SessionDerivationJobUpdate,
    ) -> SessionDerivationJob | None: ...

    def update_derivation_job_if_status(
        self,
        job_id: str,
        expected_status: str,
        update: SessionDerivationJobUpdate,
    ) -> SessionDerivationJob | None: ...

    def list_messages_through_turn(
        self,
        session_id: str,
        through_turn_id: int,
    ) -> list[SessionMessage]: ...

    def copy_messages(
        self,
        target_session_id: str,
        messages: Iterable[SessionMessage],
    ) -> int: ...

    def copy_rp_module_overrides(
        self,
        target_session_id: str,
        overrides: Iterable[data_models.SessionRPModuleOverride],
    ) -> int: ...

    def list_session_rp_module_overrides(
        self,
        session_id: str,
    ) -> list[data_models.SessionRPModuleOverride] | None: ...

    def copy_plot_overrides(
        self,
        source_session_id: str,
        target_session_id: str,
    ) -> None: ...

    def copy_plot_decisions(
        self,
        source_session_id: str,
        target_session_id: str,
        through_turn_id: int,
        *,
        decision_statuses: Collection[str],
    ) -> int: ...

    def set_session_main_llm_provider_key(
        self,
        session_id: str,
        provider_key: str | None,
    ) -> Session | None: ...

    def set_session_lifecycle(
        self,
        session_id: str,
        lifecycle: str,
    ) -> Session | None: ...


class SessionDerivationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class SessionDerivationStage(StrEnum):
    QUEUED = "queued"
    SNAPSHOTTING = "snapshotting"
    COPYING = "copying"
    REBUILDING_STATUS = "rebuilding_status"
    EXTRACTING_STORY_MEMORY = "extracting_story_memory"
    SUMMARIZING = "summarizing"
    EVALUATING_CONTEXT = "evaluating_context"
    FINALIZING = "finalizing"
    READY = "ready"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

    @property
    def is_running_stage(self) -> bool:
        return self not in {
            self.QUEUED,
            self.READY,
            self.FAILED,
            self.INTERRUPTED,
        }


class SessionDerivationErrorCode(StrEnum):
    SOURCE_BUSY = "DERIVATION_SOURCE_BUSY"
    SOURCE_NOT_READY = "DERIVATION_SOURCE_NOT_READY"
    TARGET_BUSY = "DERIVATION_TARGET_BUSY"
    TARGET_PROVISIONING = "DERIVATION_TARGET_PROVISIONING"
    TURN_INVALID = "DERIVATION_TURN_INVALID"
    TURN_NOT_FOUND = "DERIVATION_TURN_NOT_FOUND"
    TURN_INCOMPLETE = "DERIVATION_TURN_INCOMPLETE"
    INVALID_STATE = "DERIVATION_INVALID_STATE"
    CLAIM_CONFLICT = "DERIVATION_CLAIM_CONFLICT"
    TARGET_ALREADY_CREATED = "DERIVATION_TARGET_ALREADY_CREATED"
    TARGET_MISSING = "DERIVATION_TARGET_MISSING"
    TARGET_NOT_PROVISIONING = "DERIVATION_TARGET_NOT_PROVISIONING"
    TARGET_CLEANUP_REQUIRED = "DERIVATION_TARGET_CLEANUP_REQUIRED"
    TARGET_OWNERSHIP_MISMATCH = "DERIVATION_TARGET_OWNERSHIP_MISMATCH"
    TARGET_ALREADY_READY = "DERIVATION_TARGET_ALREADY_READY"
    WORKER_RESTARTED = "DERIVATION_WORKER_RESTARTED"
    WORKER_UNAVAILABLE = "DERIVATION_WORKER_UNAVAILABLE"
    PREPARATION_FAILED = "DERIVATION_PREPARATION_FAILED"


class SessionDerivationError(ValueError):
    """Stable domain failure mapped by the Agent service boundary."""

    def __init__(self, code: SessionDerivationErrorCode | str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


class SessionDerivationSourceBusyError(SessionDerivationError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            SessionDerivationErrorCode.SOURCE_BUSY,
            f"Session has an active derivation: {session_id}",
        )


class SessionDerivationTargetBusyError(SessionDerivationError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            SessionDerivationErrorCode.TARGET_BUSY,
            f"Session is the target of an active derivation: {session_id}",
        )


class SessionDerivationProvisioningError(SessionDerivationError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            SessionDerivationErrorCode.TARGET_PROVISIONING,
            f"Session is still provisioning: {session_id}",
        )


@dataclass(frozen=True)
class SessionDerivationSeedResult:
    job: SessionDerivationJob
    session: Session
    copied_message_count: int


class SessionDerivationService:
    """Own the derivation job lifecycle and target inheritance policy."""

    def __init__(self, data: SessionDerivationDataPort) -> None:
        self._data = data

    def create_job(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        requested_title: str = "",
    ) -> SessionDerivationJob:
        session_id = str(source_session_id)
        turn_id = _positive_turn_id(branch_turn_id)
        with self._data.transaction():
            source = self._data.get_session(session_id)
            if (
                source is None
                or source.lifecycle != SESSION_LIFECYCLE_READY
            ):
                raise SessionDerivationError(
                    SessionDerivationErrorCode.SOURCE_NOT_READY,
                    f"Ready source session not found: {session_id}",
                )
            messages = self._data.list_messages_through_turn(session_id, turn_id)
            _require_complete_turn(session_id, turn_id, messages)
            try:
                return self._data.create_derivation_job(
                    session_id,
                    turn_id,
                    requested_title=str(requested_title).strip(),
                )
            except SessionDataConflictError as exc:
                raise SessionDerivationSourceBusyError(session_id) from exc

    def get_job(self, job_id: str) -> SessionDerivationJob | None:
        return self._data.get_derivation_job(str(job_id))

    def list_jobs(
        self,
        *statuses: SessionDerivationStatus,
    ) -> list[SessionDerivationJob]:
        return self._data.list_derivation_jobs(*(status.value for status in statuses))

    def has_active_job(self, source_session_id: str) -> bool:
        return self._data.has_active_derivation_for_source(str(source_session_id))

    def start_job(self, job_id: str) -> SessionDerivationJob:
        updated = self._data.update_derivation_job_if_status(
            str(job_id),
            SessionDerivationStatus.QUEUED.value,
            SessionDerivationJobUpdate(
                status=SessionDerivationStatus.RUNNING.value,
                stage=SessionDerivationStage.SNAPSHOTTING.value,
                mark_started=True,
            ),
        )
        if updated is not None:
            return updated
        job = self._require_job(job_id)
        if job.status != SessionDerivationStatus.QUEUED.value:
            raise SessionDerivationError(
                SessionDerivationErrorCode.INVALID_STATE,
                f"Derivation job is not queued: {job.id}/{job.status}",
            )
        raise SessionDerivationError(
            SessionDerivationErrorCode.CLAIM_CONFLICT,
            f"Derivation job could not be claimed: {job.id}",
        )

    def set_stage(
        self,
        job_id: str,
        stage: SessionDerivationStage,
    ) -> SessionDerivationJob:
        if not stage.is_running_stage:
            raise ValueError(f"Stage is not a running stage: {stage.value}")
        job = self._require_running_job(job_id)
        updated = self._data.update_derivation_job(
            job.id,
            SessionDerivationJobUpdate(stage=stage.value),
        )
        if updated is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        return updated

    def materialize_target(self, job_id: str) -> SessionDerivationSeedResult:
        with self._data.transaction():
            job = self._require_running_job(job_id)
            if job.target_session_id is not None:
                raise SessionDerivationError(
                    SessionDerivationErrorCode.TARGET_ALREADY_CREATED,
                    f"Derivation target already exists: {job.target_session_id}",
                )
            source = self._data.get_session(job.source_session_id)
            if (
                source is None
                or source.lifecycle != SESSION_LIFECYCLE_READY
            ):
                raise SessionDerivationError(
                    SessionDerivationErrorCode.SOURCE_NOT_READY,
                    f"Ready source session not found: {job.source_session_id}",
                )
            messages = self._data.list_messages_through_turn(
                source.id,
                job.branch_turn_id,
            )
            _require_complete_turn(source.id, job.branch_turn_id, messages)
            target = SessionCatalogService(self._data).create_session(
                source.workspace_id,
                source.story_id,
                title=job.requested_title or _derived_title(source.title),
                description="",
                player_character_id=source.player_character_id,
                player_character_snapshot_json=source.player_character_snapshot_json,
                story_opening_id=source.story_opening_id,
                lifecycle=SESSION_LIFECYCLE_PROVISIONING,
            )
            if target is None:
                raise RuntimeError(
                    f"Source Story disappeared during derivation: {source.story_id}"
                )
            if source.main_llm_provider_key is not None:
                target = (
                    self._data.set_session_main_llm_provider_key(
                        target.id,
                        source.main_llm_provider_key,
                    )
                    or target
                )
            source_overrides = (
                self._data.list_session_rp_module_overrides(source.id) or []
            )
            self._data.copy_rp_module_overrides(target.id, source_overrides)
            copied_message_count = self._data.copy_messages(target.id, messages)

            copy_policy = PLOT_DERIVATION_COPY_POLICY
            if copy_policy.copy_overrides:
                self._data.copy_plot_overrides(source.id, target.id)
            self._data.copy_plot_decisions(
                source.id,
                target.id,
                job.branch_turn_id,
                decision_statuses=copy_policy.decision_statuses,
            )
            updated_job = self._data.update_derivation_job(
                job.id,
                SessionDerivationJobUpdate(
                    target_session_id=target.id,
                    stage=SessionDerivationStage.REBUILDING_STATUS.value,
                ),
            )
            if updated_job is None:
                raise RuntimeError(f"Derivation job disappeared: {job.id}")

        seeded = self._data.get_session(target.id)
        if seeded is None:
            raise RuntimeError(f"Seeded session disappeared: {target.id}")
        return SessionDerivationSeedResult(
            job=updated_job,
            session=seeded,
            copied_message_count=copied_message_count,
        )

    def set_context_usage(
        self,
        job_id: str,
        *,
        used_tokens: int,
        context_limit: int,
        threshold_exceeded: bool,
    ) -> SessionDerivationJob:
        job = self._require_running_job(job_id)
        if used_tokens < 0 or context_limit <= 0:
            raise ValueError(
                "Context usage must have used_tokens >= 0 and context_limit > 0"
            )
        updated = self._data.update_derivation_job(
            job.id,
            SessionDerivationJobUpdate(
                context_used_tokens=int(used_tokens),
                context_limit=int(context_limit),
                context_threshold_exceeded=bool(threshold_exceeded),
                write_context_usage=True,
            ),
        )
        if updated is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        return updated

    def complete_job(self, job_id: str) -> SessionDerivationJob:
        with self._data.transaction():
            job = self._require_running_job(job_id)
            if job.target_session_id is None:
                raise SessionDerivationError(
                    SessionDerivationErrorCode.TARGET_MISSING,
                    f"Derivation target has not been created: {job.id}",
                )
            target = self._data.get_session(job.target_session_id)
            if (
                target is None
                or target.lifecycle
                != SESSION_LIFECYCLE_PROVISIONING
            ):
                raise SessionDerivationError(
                    SessionDerivationErrorCode.TARGET_NOT_PROVISIONING,
                    "Provisioning target session not found: "
                    f"{job.target_session_id}",
                )
            ready = self._data.set_session_lifecycle(
                target.id,
                SESSION_LIFECYCLE_READY,
            )
            if ready is None:
                raise RuntimeError(f"Derivation target disappeared: {target.id}")
            updated = self._data.update_derivation_job(
                job.id,
                SessionDerivationJobUpdate(
                    status=SessionDerivationStatus.READY.value,
                    stage=SessionDerivationStage.READY.value,
                    error_code="",
                    error_message="",
                    mark_finished=True,
                ),
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
    ) -> SessionDerivationJob:
        with self._data.transaction():
            job = self._require_job(job_id)
            if job.status not in {
                SessionDerivationStatus.QUEUED.value,
                SessionDerivationStatus.RUNNING.value,
            }:
                raise SessionDerivationError(
                    SessionDerivationErrorCode.INVALID_STATE,
                    f"Derivation job is already final: {job.id}/{job.status}",
                )
            self._require_target_absent(job)
            updated = self._data.update_derivation_job(
                job.id,
                SessionDerivationJobUpdate(
                    status=SessionDerivationStatus.FAILED.value,
                    stage=SessionDerivationStage.FAILED.value,
                    error_code=str(error_code),
                    error_message=str(error_message),
                    mark_finished=True,
                ),
            )
            if updated is None:
                raise RuntimeError(f"Derivation job disappeared: {job.id}")
            return updated

    def interrupt_job(self, job_id: str) -> SessionDerivationJob:
        with self._data.transaction():
            job = self._require_running_job(job_id)
            self._require_target_absent(job)
            updated = self._data.update_derivation_job(
                job.id,
                SessionDerivationJobUpdate(
                    status=SessionDerivationStatus.INTERRUPTED.value,
                    stage=SessionDerivationStage.INTERRUPTED.value,
                    error_code=SessionDerivationErrorCode.WORKER_RESTARTED.value,
                    error_message=(
                        "Derivation worker restarted while the job was running"
                    ),
                    mark_finished=True,
                ),
            )
            if updated is None:
                raise RuntimeError(f"Derivation job disappeared: {job.id}")
            return updated

    def _require_target_absent(
        self,
        job: SessionDerivationJob,
    ) -> None:
        target_id = job.target_session_id
        if (
            target_id is not None
            and self._data.get_session(target_id) is not None
        ):
            raise SessionDerivationError(
                SessionDerivationErrorCode.TARGET_CLEANUP_REQUIRED,
                "Provisioning target must be quarantined before finalizing job: "
                f"{target_id}",
            )

    def _require_job(self, job_id: str) -> SessionDerivationJob:
        job = self._data.get_derivation_job(str(job_id))
        if job is None:
            raise FileNotFoundError(f"Derivation job not found: {job_id}")
        return job

    def _require_running_job(
        self,
        job_id: str,
    ) -> SessionDerivationJob:
        job = self._require_job(job_id)
        if job.status != SessionDerivationStatus.RUNNING.value:
            raise SessionDerivationError(
                SessionDerivationErrorCode.INVALID_STATE,
                f"Derivation job is not running: {job.id}/{job.status}",
            )
        return job


def _positive_turn_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SessionDerivationError(
            SessionDerivationErrorCode.TURN_INVALID,
            "branch_turn_id must be a positive integer",
        )
    return value


def _require_complete_turn(
    session_id: str,
    turn_id: int,
    messages: list[SessionMessage],
) -> None:
    turn = [message for message in messages if message.turn_id == turn_id]
    if not turn:
        raise SessionDerivationError(
            SessionDerivationErrorCode.TURN_NOT_FOUND,
            f"Turn not found in current main history: {session_id}/{turn_id}",
        )
    sequences = [message.seq_in_turn for message in turn]
    if any(
        current <= previous
        for previous, current in zip(sequences, sequences[1:])
    ) or turn[-1].role != MESSAGE_ROLE_ASSISTANT:
        raise SessionDerivationError(
            SessionDerivationErrorCode.TURN_INCOMPLETE,
            f"Turn is not a complete committed turn: {session_id}/{turn_id}",
        )


def _derived_title(source_title: str) -> str:
    title = str(source_title).strip()
    return f"{title} - 分支" if title else "分支会话"


__all__ = [
    "SessionDerivationError",
    "SessionDerivationErrorCode",
    "SessionDerivationProvisioningError",
    "SessionDerivationSeedResult",
    "SessionDerivationService",
    "SessionDerivationSourceBusyError",
    "SessionDerivationStage",
    "SessionDerivationStatus",
    "SessionDerivationTargetBusyError",
]
