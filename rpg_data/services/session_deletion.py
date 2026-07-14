"""Permanent deletion of one catalog session and its runtime directory."""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from peewee import Database

from rpg_data import models
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.services.catalog import CatalogService

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

    def delete(self, session_id: str) -> models.SessionDeleteResult | None:
        """Permanently delete one session after quarantining its runtime path."""

        normalized_session_id = str(session_id)
        if self._sessions.get(normalized_session_id) is None:
            return None

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
                if not self._sessions.delete(normalized_session_id):
                    raise RuntimeError(
                        f"Session disappeared during deletion: {normalized_session_id}"
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
