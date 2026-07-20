"""Permanent Session deletion policy and runtime-directory compensation."""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from rpg_core.session.derivation import (
    SessionDerivationError,
    SessionDerivationErrorCode,
    SessionDerivationProvisioningError,
    SessionDerivationSourceBusyError,
    SessionDerivationStatus,
    SessionDerivationTargetBusyError,
)
from rpg_data import models as data_models

if TYPE_CHECKING:
    from rpg_data.services.gateway import DataServiceGateway

logger = logging.getLogger("rpg_core.session.deletion")


class SessionRuntimeCleanupStatus(StrEnum):
    DELETED = "deleted"
    ABSENT = "absent"
    PENDING = "pending"


@dataclass(frozen=True)
class SessionDeleteResult:
    session_id: str
    runtime_cleanup: SessionRuntimeCleanupStatus


class SessionDeletionService:
    """Authorize deletion and compensate runtime-directory/SQL failures."""

    def __init__(self, gateway: "DataServiceGateway") -> None:
        self._gateway = gateway
        self._data = gateway.session_deletion

    def validate_regular_deletion(
        self,
        session_id: str,
    ) -> data_models.Session | None:
        normalized_session_id = str(session_id)
        session = self._gateway.catalog.get_session(normalized_session_id)
        if session is None:
            return None
        derivations = self._gateway.session_derivations
        if derivations.has_active_for_source(normalized_session_id):
            raise SessionDerivationSourceBusyError(normalized_session_id)
        if derivations.has_active_for_target(normalized_session_id):
            raise SessionDerivationTargetBusyError(normalized_session_id)
        if session.lifecycle != data_models.SESSION_LIFECYCLE_READY:
            raise SessionDerivationProvisioningError(normalized_session_id)
        return session

    def delete(self, session_id: str) -> SessionDeleteResult | None:
        session = self.validate_regular_deletion(str(session_id))
        if session is None:
            return None
        return self._delete_validated_session(session)

    def delete_provisioning_target(
        self,
        job_id: str,
        target_session_id: str,
    ) -> SessionDeleteResult:
        normalized_job_id = str(job_id)
        normalized_target_id = str(target_session_id)
        job = self._gateway.session_derivations.get_job(normalized_job_id)
        if job is None:
            raise FileNotFoundError(f"Derivation job not found: {normalized_job_id}")
        if job.target_session_id != normalized_target_id:
            raise SessionDerivationError(
                SessionDerivationErrorCode.TARGET_OWNERSHIP_MISMATCH,
                "Provisioning target does not belong to derivation job: "
                f"{normalized_job_id}/{normalized_target_id}",
            )
        if job.status != SessionDerivationStatus.RUNNING.value:
            raise SessionDerivationError(
                SessionDerivationErrorCode.INVALID_STATE,
                f"Derivation job is not running: {job.id}/{job.status}",
            )
        target = self._gateway.catalog.get_session(normalized_target_id)
        if target is None:
            return SessionDeleteResult(
                session_id=normalized_target_id,
                runtime_cleanup=SessionRuntimeCleanupStatus.ABSENT,
            )
        if target.lifecycle != data_models.SESSION_LIFECYCLE_PROVISIONING:
            raise SessionDerivationError(
                SessionDerivationErrorCode.TARGET_ALREADY_READY,
                f"Refusing to clean up a ready session: {target.id}",
            )
        return self._delete_validated_session(
            target,
            derivation_job_id=job.id,
        )

    def _delete_validated_session(
        self,
        session: data_models.Session,
        *,
        derivation_job_id: str | None = None,
    ) -> SessionDeleteResult:
        session_id = str(session.id)
        runtime_dir = self._gateway.catalog.resolve_session_runtime_dir(session_id)
        quarantine_dir = runtime_dir.with_name(
            f".{runtime_dir.name}.delete-{uuid.uuid4().hex}"
        )
        runtime_moved = False

        try:
            if runtime_dir.exists():
                runtime_dir.rename(quarantine_dir)
                runtime_moved = True
            with self._gateway.transaction():
                deleted = (
                    self._data.delete_ready_without_active_derivation(session_id)
                    if derivation_job_id is None
                    else self._data.delete_provisioning_for_derivation(
                        session_id,
                        derivation_job_id,
                    )
                )
                if not deleted:
                    self._raise_conditional_delete_conflict(
                        session_id,
                        derivation_job_id=derivation_job_id,
                    )
        except BaseException:
            self._restore_runtime_directory(
                runtime_dir=runtime_dir,
                quarantine_dir=quarantine_dir,
                runtime_moved=runtime_moved,
            )
            raise

        cleanup = SessionRuntimeCleanupStatus.ABSENT
        if runtime_moved:
            try:
                shutil.rmtree(quarantine_dir)
                cleanup = SessionRuntimeCleanupStatus.DELETED
            except Exception:
                cleanup = SessionRuntimeCleanupStatus.PENDING
                logger.exception(
                    "Session row deleted but runtime cleanup is pending "
                    "session_id=%s path=%s",
                    session_id,
                    quarantine_dir,
                )
        return SessionDeleteResult(
            session_id=session_id,
            runtime_cleanup=cleanup,
        )

    def _raise_conditional_delete_conflict(
        self,
        session_id: str,
        *,
        derivation_job_id: str | None,
    ) -> None:
        if derivation_job_id is None:
            current = self.validate_regular_deletion(session_id)
            if current is None:
                raise RuntimeError(
                    f"Session disappeared during deletion: {session_id}"
                )
            raise RuntimeError(
                f"Ready session conditional deletion failed: {session_id}"
            )

        job = self._gateway.session_derivations.get_job(derivation_job_id)
        if job is None:
            raise FileNotFoundError(
                f"Derivation job not found: {derivation_job_id}"
            )
        if job.target_session_id != session_id:
            raise SessionDerivationError(
                SessionDerivationErrorCode.TARGET_OWNERSHIP_MISMATCH,
                "Provisioning target does not belong to derivation job: "
                f"{derivation_job_id}/{session_id}",
            )
        if job.status != SessionDerivationStatus.RUNNING.value:
            raise SessionDerivationError(
                SessionDerivationErrorCode.INVALID_STATE,
                f"Derivation job is not running: {job.id}/{job.status}",
            )
        target = self._gateway.catalog.get_session(session_id)
        if target is None:
            raise RuntimeError(
                f"Provisioning target disappeared during deletion: {session_id}"
            )
        if target.lifecycle != data_models.SESSION_LIFECYCLE_PROVISIONING:
            raise SessionDerivationError(
                SessionDerivationErrorCode.TARGET_ALREADY_READY,
                f"Refusing to clean up a ready session: {target.id}",
            )
        raise RuntimeError(
            f"Provisioning target conditional deletion failed: {session_id}"
        )

    @staticmethod
    def _restore_runtime_directory(
        *,
        runtime_dir: Path,
        quarantine_dir: Path,
        runtime_moved: bool,
    ) -> None:
        if not runtime_moved or not quarantine_dir.exists():
            return
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
        quarantine_dir.rename(runtime_dir)


__all__ = [
    "SessionDeleteResult",
    "SessionDeletionService",
    "SessionRuntimeCleanupStatus",
]
