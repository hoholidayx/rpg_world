"""Append-only backup services for session cold data."""

from __future__ import annotations

from collections.abc import Mapping

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import SessionBackupMessageRecord
from rpg_data.services._message_store import BaseSessionMessageStore

__all__ = ["BackupMessageComponent", "BackupService"]


class BackupMessageComponent:
    """Append-only backup access for session messages."""

    def __init__(self, database: Database) -> None:
        self._store = BaseSessionMessageStore(database, SessionBackupMessageRecord)

    def append(
        self,
        session_id: str,
        role: str,
        content: str = "",
        *,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        tool_call_id: str = "",
        tool_calls_json: str = "",
        metadata_json: str = "{}",
    ) -> models.SessionMessage:
        return self._store.append(
            session_id,
            role,
            content,
            turn_id=turn_id,
            seq_in_turn=seq_in_turn,
            tool_call_id=tool_call_id,
            tool_calls_json=tool_calls_json,
            metadata_json=metadata_json,
        )

    def append_mapping(
        self,
        session_id: str,
        values: models.SessionMessage | Mapping[str, object],
    ) -> models.SessionMessage:
        return self._store.append_mapping(session_id, values)

    def list(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[models.SessionMessage]:
        return self._store.list(session_id, limit=limit, offset=offset)

    def get(self, message_id: int) -> models.SessionMessage | None:
        return self._store.get(message_id)

    def count(self, session_id: str) -> int:
        return self._store.count(session_id)


class BackupService:
    """Compose append-only backup components by record family."""

    def __init__(self, database: Database) -> None:
        self.messages = BackupMessageComponent(database)
