"""Session message service for mutable main history."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping

from peewee import Database

from commons.errors import InvalidTurnMetadataError
from rpg_data.model import session as models
from rpg_data.repositories.records import SessionMessageRecord
from rpg_data.services._message_store import BaseSessionMessageStore, MessageInput

__all__ = ["MessageDataService"]


class MessageDataService:
    """Expose CRUD for the current mutable session message history."""

    def __init__(self, database: Database) -> None:
        self._store = BaseSessionMessageStore(database, SessionMessageRecord)

    def append(
        self,
        session_id: str,
        role: str,
        content: str = "",
        *,
        mode: str = models.TURN_MODE_IC,
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
            mode=mode,
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

    def list_filtered(
        self,
        session_id: str,
        *,
        excluded_roles: Collection[str] = (),
        summary_processed: bool | None = None,
        story_memory_processed: bool | None = None,
    ) -> list[models.SessionMessage]:
        return self._store.list_filtered(
            session_id,
            excluded_roles=excluded_roles,
            summary_processed=summary_processed,
            story_memory_processed=story_memory_processed,
        )

    def count_distinct_turns(
        self,
        session_id: str,
        *,
        excluded_roles: Collection[str] = (),
        summary_processed: bool | None = None,
        story_memory_processed: bool | None = None,
    ) -> int:
        return self._store.count_distinct_turns(
            session_id,
            excluded_roles=excluded_roles,
            summary_processed=summary_processed,
            story_memory_processed=story_memory_processed,
        )

    def list_turn_window(
        self,
        session_id: str,
        *,
        limit: int,
        before_turn_id: int | None = None,
        after_turn_id: int | None = None,
    ) -> list[models.SessionMessage]:
        return self._store.list_turn_window(
            session_id,
            limit=limit,
            before_turn_id=before_turn_id,
            after_turn_id=after_turn_id,
        )

    def list_turn(self, session_id: str, turn_id: int) -> list[models.SessionMessage]:
        return self._store.list_turn(session_id, turn_id)

    def has_turn_before(self, session_id: str, turn_id: int) -> bool:
        return self._store.has_turn_before(session_id, turn_id)

    def has_turn_after(self, session_id: str, turn_id: int) -> bool:
        return self._store.has_turn_after(session_id, turn_id)

    def get(self, message_id: int) -> models.SessionMessage | None:
        return self._store.get(message_id)

    def get_for_session(self, session_id: str, message_id: int) -> models.SessionMessage | None:
        return self._store.get_for_session(session_id, message_id)

    def update(
        self,
        message_id: int,
        *,
        role: str | None = None,
        content: str | None = None,
        mode: str | None = None,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        tool_call_id: str | None = None,
        tool_calls_json: str | None = None,
        metadata_json: str | None = None,
    ) -> models.SessionMessage | None:
        if turn_id is not None or seq_in_turn is not None:
            raise InvalidTurnMetadataError("turn_id and seq_in_turn are immutable; use a dedicated repair flow")
        return self._store.update(
            message_id,
            role=role,
            content=content,
            mode=mode,
            turn_id=turn_id,
            seq_in_turn=seq_in_turn,
            tool_call_id=tool_call_id,
            tool_calls_json=tool_calls_json,
            metadata_json=metadata_json,
        )

    def delete(self, message_id: int) -> bool:
        return self._store.delete(message_id)

    def delete_for_session(self, session_id: str, message_id: int) -> bool:
        return self._store.delete_for_session(session_id, message_id)

    def clear(self, session_id: str) -> int:
        return self._store.clear(session_id)

    def count(self, session_id: str) -> int:
        return self._store.count(session_id)

    def latest_turn_id(self, session_id: str) -> int:
        return self._store.latest_turn_id(session_id)

    def list_summary_turn_ranges(self, session_id: str) -> dict[int, tuple[int, int]]:
        """Return min/max turn IDs for each processed summary batch."""

        return self._store.list_summary_turn_ranges(session_id)

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

    def truncate_from_turn(self, session_id: str, turn_id: int) -> int:
        return self._store.truncate_from_turn(session_id, turn_id)

    def mark_summary_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
        *,
        batch_id: int | None,
    ) -> int:
        return self._store.mark_summary_processed(
            session_id,
            message_ids,
            batch_id=batch_id,
        )

    def mark_summary_batches_processed(
        self,
        session_id: str,
        batches: Iterable[tuple[Iterable[int], int]],
    ) -> int:
        return self._store.mark_summary_batches_processed(session_id, batches)

    def mark_story_memory_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int:
        return self._store.mark_story_memory_processed(session_id, message_ids)

    def reset_processing_for_messages(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int:
        return self._store.reset_processing_for_messages(session_id, message_ids)
