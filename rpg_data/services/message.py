"""Session message service for mutable main history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import SessionMessageRecord
from rpg_data.services._message_store import BaseSessionMessageStore, MessageInput

__all__ = ["MessageService"]


class MessageService:
    """Expose CRUD for the current mutable session message history."""

    def __init__(self, database: Database) -> None:
        self._store = BaseSessionMessageStore(database, SessionMessageRecord)

    def append(
        self,
        session_id: str,
        role: str,
        content: str = "",
        *,
        turn_id: int = 0,
        seq_in_turn: int = 0,
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

    def update(
        self,
        message_id: int,
        *,
        role: str | None = None,
        content: str | None = None,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        tool_call_id: str | None = None,
        tool_calls_json: str | None = None,
        metadata_json: str | None = None,
    ) -> models.SessionMessage | None:
        return self._store.update(
            message_id,
            role=role,
            content=content,
            turn_id=turn_id,
            seq_in_turn=seq_in_turn,
            tool_call_id=tool_call_id,
            tool_calls_json=tool_calls_json,
            metadata_json=metadata_json,
        )

    def delete(self, message_id: int) -> bool:
        return self._store.delete(message_id)

    def clear(self, session_id: str) -> int:
        return self._store.clear(session_id)

    def count(self, session_id: str) -> int:
        return self._store.count(session_id)

    def replace(
        self,
        session_id: str,
        messages: Iterable[MessageInput],
    ) -> list[models.SessionMessage]:
        return self._store.replace(session_id, messages)

    def truncate_before_id(self, session_id: str, boundary_id: int) -> int:
        return self._store.truncate_before_id(session_id, boundary_id)

    def truncate_before_index(self, session_id: str, keep_from_index: int) -> int:
        return self._store.truncate_before_index(session_id, keep_from_index)
