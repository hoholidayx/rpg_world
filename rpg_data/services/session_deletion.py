"""Permanent deletion of one catalog session and its runtime directory."""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from peewee import Database

from rpg_data import models
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.session_derivation_repo import SessionDerivationRepository
from rpg_data.services.catalog import CatalogService
from rpg_data.services.session_derivation import (
    SessionDerivationDataError,
    SessionDerivationProvisioningError,
    SessionDerivationSourceBusyError,
    SessionDerivationTargetBusyError,
)

__all__ = ["SessionDeletionService"]

logger = logging.getLogger("rpg_data.session_deletion")


class SessionDeletionService:
    """Delete a session row, all FK children, and session runtime files."""

    def __init__(
        self,
        database: Database,
        *,
        catalog: CatalogService | None = None,
    ) -> None:
        self._database = database
        self._catalog = catalog or CatalogService(database)
        self._sessions = SessionRepository(database)
        self._derivations = SessionDerivationRepository(database)

    def delete(self, session_id: str) -> models.SessionDeleteResult | None:
        """Permanently delete one session after quarantining its runtime path."""

        normalized_session_id = str(session_id)
        session = self.validate_regular_deletion(normalized_session_id)
        if session is None:
            return None
        return self._delete_validated_session(session)

    def validate_regular_deletion(self, session_id: str) -> models.Session | None:
        """Validate the public deletion path without mutating runtime state."""

        normalized_session_id = str(session_id)
        session = self._sessions.get(normalized_session_id)
        if session is None:
            return None
        if self._derivations.has_active_for_source(normalized_session_id):
            raise SessionDerivationSourceBusyError(normalized_session_id)
        if self._derivations.has_active_for_target(normalized_session_id):
            raise SessionDerivationTargetBusyError(normalized_session_id)
        if session.lifecycle != models.SESSION_LIFECYCLE_READY:
            raise SessionDerivationProvisioningError(normalized_session_id)
        return session

    def delete_provisioning_target(
        self,
        job_id: str,
        target_session_id: str,
    ) -> models.SessionDeleteResult:
        """Privileged worker-only deletion for one job-owned target.

        The explicit target ID is checked against the persisted job before the
        filesystem or SQL is touched. The job row intentionally survives so a
        failed/interrupted terminal state retains its target ID for diagnosis.
        """

        normalized_job_id = str(job_id)
        normalized_target_id = str(target_session_id)
        job = self._derivations.get(normalized_job_id)
        if job is None:
            raise FileNotFoundError(f"Derivation job not found: {normalized_job_id}")
        if job.target_session_id != normalized_target_id:
            raise SessionDerivationDataError(
                "DERIVATION_TARGET_OWNERSHIP_MISMATCH",
                "Provisioning target does not belong to derivation job: "
                f"{normalized_job_id}/{normalized_target_id}",
            )
        if job.status != models.SESSION_DERIVATION_JOB_STATUS_RUNNING:
            raise SessionDerivationDataError(
                "DERIVATION_INVALID_STATE",
                f"Derivation job is not running: {job.id}/{job.status}",
            )
        target = self._sessions.get(normalized_target_id)
        if target is None:
            return models.SessionDeleteResult(
                session_id=normalized_target_id,
                runtime_cleanup=models.SESSION_RUNTIME_CLEANUP_ABSENT,
            )
        if target.lifecycle != models.SESSION_LIFECYCLE_PROVISIONING:
            raise SessionDerivationDataError(
                "DERIVATION_TARGET_ALREADY_READY",
                f"Refusing to clean up a ready session: {target.id}",
            )
        return self._delete_validated_session(target, derivation_job_id=job.id)

    def _delete_validated_session(
        self,
        session: models.Session,
        *,
        derivation_job_id: str | None = None,
    ) -> models.SessionDeleteResult:
        normalized_session_id = str(session.id)

        runtime_dir = self._catalog.resolve_session_runtime_dir(normalized_session_id)
        quarantine_dir = runtime_dir.with_name(
            f".{runtime_dir.name}.delete-{uuid.uuid4().hex}"
        )
        runtime_moved = False

        try:
            if runtime_dir.exists():
                runtime_dir.rename(quarantine_dir)
                runtime_moved = True
            with self._database.atomic():
                deleted = (
                    self._sessions.delete_ready_without_active_derivation(
                        normalized_session_id
                    )
                    if derivation_job_id is None
                    else self._sessions.delete_provisioning_for_derivation(
                        normalized_session_id,
                        derivation_job_id,
                    )
                )
                if not deleted:
                    self._raise_conditional_delete_conflict(
                        normalized_session_id,
                        derivation_job_id=derivation_job_id,
                    )
        except BaseException:
            self._restore_runtime_directory(
                runtime_dir=runtime_dir,
                quarantine_dir=quarantine_dir,
                runtime_moved=runtime_moved,
            )
            raise

        runtime_cleanup = models.SESSION_RUNTIME_CLEANUP_ABSENT
        if runtime_moved:
            try:
                shutil.rmtree(quarantine_dir)
                runtime_cleanup = models.SESSION_RUNTIME_CLEANUP_DELETED
            except Exception:
                runtime_cleanup = models.SESSION_RUNTIME_CLEANUP_PENDING
                logger.exception(
                    "session catalog deleted but quarantined runtime cleanup is pending session_id=%s path=%s",
                    normalized_session_id,
                    quarantine_dir,
                )

        logger.info(
            "deleted catalog session session_id=%s runtime_cleanup=%s",
            normalized_session_id,
            runtime_cleanup,
        )
        return models.SessionDeleteResult(
            session_id=normalized_session_id,
            runtime_cleanup=runtime_cleanup,
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
                raise RuntimeError(f"Session disappeared during deletion: {session_id}")
            raise RuntimeError(
                f"Ready session conditional deletion failed: {session_id}"
            )

        job = self._derivations.get(derivation_job_id)
        if job is None:
            raise FileNotFoundError(f"Derivation job not found: {derivation_job_id}")
        if job.target_session_id != session_id:
            raise SessionDerivationDataError(
                "DERIVATION_TARGET_OWNERSHIP_MISMATCH",
                "Provisioning target does not belong to derivation job: "
                f"{derivation_job_id}/{session_id}",
            )
        if job.status != models.SESSION_DERIVATION_JOB_STATUS_RUNNING:
            raise SessionDerivationDataError(
                "DERIVATION_INVALID_STATE",
                f"Derivation job is not running: {job.id}/{job.status}",
            )
        target = self._sessions.get(session_id)
        if target is None:
            raise RuntimeError(
                f"Provisioning target disappeared during deletion: {session_id}"
            )
        if target.lifecycle != models.SESSION_LIFECYCLE_PROVISIONING:
            raise SessionDerivationDataError(
                "DERIVATION_TARGET_ALREADY_READY",
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
