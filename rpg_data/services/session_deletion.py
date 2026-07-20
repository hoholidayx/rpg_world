"""Conditional CRUD primitives for permanent Session deletion."""

from __future__ import annotations

from peewee import Database

from rpg_data.repositories.session_repo import SessionRepository

__all__ = ["SessionDeletionDataService"]


class SessionDeletionDataService:
    """Delete Session rows under caller-selected persisted predicates."""

    def __init__(self, database: Database) -> None:
        self._sessions = SessionRepository(database)

    def delete(self, session_id: str) -> bool:
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
