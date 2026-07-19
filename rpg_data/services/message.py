"""Session message service for mutable main history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from peewee import Database

from commons.errors import InvalidTurnMetadataError
from rpg_data import models
from rpg_data.repositories.records import SessionMessageRecord
from rpg_data.services._message_store import BaseSessionMessageStore, MessageInput

__all__ = ["AgentContextMessageProjection", "MessageService"]


@dataclass(frozen=True)
class AgentContextMessageProjection:
    """Messages eligible for the main Agent context.

    ``summary_processed`` is the sole projection rule.  The complete mutable
    history remains available through :meth:`MessageService.list`.
    """

    messages: tuple[models.SessionMessage, ...]
    filtered_message_count: int


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

    def list_for_agent_context(self, session_id: str) -> AgentContextMessageProjection:
        """Return current messages after applying ``summary_processed`` only."""
        rows = self.list(session_id)
        messages = tuple(row for row in rows if not row.summary_processed)
        return AgentContextMessageProjection(
            messages=messages,
            filtered_message_count=len(rows) - len(messages),
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
        updated = self._store.update(
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
        if updated is None:
            return None
        if _processing_affecting_update(
            role=role,
            content=content,
            mode=mode,
            turn_id=turn_id,
            seq_in_turn=seq_in_turn,
            tool_call_id=tool_call_id,
            tool_calls_json=tool_calls_json,
            metadata_json=metadata_json,
        ):
            self.reset_processing_for_messages(updated.session_id, [updated.id])
            updated = self._store.get(message_id)
        return updated

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
        current_by_id = {row.id: row for row in self.list(session_id)}
        enriched = [
            _preserve_processing_fields(message, current_by_id)
            for message in messages
        ]
        return self._store.replace(session_id, enriched)

    def truncate_before_id(self, session_id: str, boundary_id: int) -> int:
        return self._store.truncate_before_id(session_id, boundary_id)

    def truncate_before_index(self, session_id: str, keep_from_index: int) -> int:
        return self._store.truncate_before_index(session_id, keep_from_index)

    def truncate_from_turn(self, session_id: str, turn_id: int) -> int:
        return self._store.truncate_from_turn(session_id, turn_id)

    def list_summary_candidate_turn_groups(
        self,
        session_id: str,
        *,
        keep_recent_turns: int,
    ) -> list[list[models.SessionMessage]]:
        """Return unprocessed message groups eligible for summary compression."""
        rows = [
            row
            for row in self.list(session_id)
            if row.role != models.MESSAGE_ROLE_SYSTEM
        ]
        if not any(not row.summary_processed for row in rows):
            return []

        groups = _conversation_turn_groups(rows, session_id=session_id, purpose="summary")
        keep = max(0, int(keep_recent_turns))
        eligible_groups = groups if keep <= 0 else groups[:-keep]
        return [
            [row for row in group if not row.summary_processed]
            for group in eligible_groups
            if any(not row.summary_processed for row in group)
        ]

    def list_summary_unprocessed_turn_groups(
        self,
        session_id: str,
    ) -> list[list[models.SessionMessage]]:
        """Return all unprocessed turn groups without applying business policy."""
        rows = [
            row
            for row in self.list(session_id)
            if row.role != models.MESSAGE_ROLE_SYSTEM and not row.summary_processed
        ]
        return _conversation_turn_groups(rows, session_id=session_id, purpose="summary")

    def count_summary_candidate_turns(
        self,
        session_id: str,
        *,
        keep_recent_turns: int,
    ) -> int:
        return len(
            self.list_summary_candidate_turn_groups(
                session_id,
                keep_recent_turns=keep_recent_turns,
            )
        )

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

    def list_story_memory_unprocessed_turn_groups(
        self,
        session_id: str,
    ) -> list[list[models.SessionMessage]]:
        """Return unprocessed message groups for story-memory extraction."""
        rows = [
            row
            for row in self.list(session_id)
            if row.role != models.MESSAGE_ROLE_SYSTEM and not row.story_memory_processed
        ]
        return _conversation_turn_groups(rows, session_id=session_id, purpose="story_memory")

    def count_story_memory_unprocessed_turns(self, session_id: str) -> int:
        return len(self.list_story_memory_unprocessed_turn_groups(session_id))

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


def _processing_affecting_update(
    *,
    role: str | None,
    content: str | None,
    mode: str | None,
    turn_id: int | None,
    seq_in_turn: int | None,
    tool_call_id: str | None,
    tool_calls_json: str | None,
    metadata_json: str | None,
) -> bool:
    return any(
        value is not None
        for value in (
            role,
            content,
            mode,
            turn_id,
            seq_in_turn,
            tool_call_id,
            tool_calls_json,
            metadata_json,
        )
    )


def _preserve_processing_fields(
    message: MessageInput,
    current_by_id: dict[int, models.SessionMessage],
) -> MessageInput:
    message_id = _message_input_id(message)
    current = current_by_id.get(message_id) if message_id > 0 else None
    if current is None:
        return message

    if isinstance(message, models.SessionMessage):
        return message

    payload = dict(message)
    payload.setdefault("summary_processed", current.summary_processed)
    payload.setdefault("summary_batch_id", current.summary_batch_id)
    payload.setdefault("summary_processed_at", current.summary_processed_at)
    payload.setdefault("story_memory_processed", current.story_memory_processed)
    payload.setdefault("story_memory_processed_at", current.story_memory_processed_at)
    return payload


def _message_input_id(message: MessageInput) -> int:
    if isinstance(message, models.SessionMessage):
        return int(message.id)
    raw = message.get("id", message.get("uid", 0))
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _conversation_turn_groups(
    rows: list[models.SessionMessage],
    *,
    session_id: str,
    purpose: str,
) -> list[list[models.SessionMessage]]:
    conversation_rows = [row for row in rows if row.role != models.MESSAGE_ROLE_SYSTEM]
    if not conversation_rows:
        return []

    if not _has_trustworthy_turn_metadata(conversation_rows):
        raise InvalidTurnMetadataError(f"invalid turn metadata for {purpose}: session_id={session_id}")
    return _explicit_turn_groups(conversation_rows)


def _has_trustworthy_turn_metadata(rows: list[models.SessionMessage]) -> bool:
    if not rows:
        return False
    last_turn_id = 0
    last_seq_in_turn = 0
    for row in rows:
        turn_id = int(row.turn_id)
        seq_in_turn = int(row.seq_in_turn)
        if turn_id <= 0 or seq_in_turn <= 0:
            return False
        if turn_id < last_turn_id:
            return False
        if turn_id == last_turn_id and seq_in_turn <= last_seq_in_turn:
            return False
        last_turn_id = turn_id
        last_seq_in_turn = seq_in_turn
    return True


def _explicit_turn_groups(rows: list[models.SessionMessage]) -> list[list[models.SessionMessage]]:
    if not rows:
        return []
    groups: list[list[models.SessionMessage]] = []
    current_turn_id = int(rows[0].turn_id)
    current_group: list[models.SessionMessage] = []
    for row in rows:
        if int(row.turn_id) != current_turn_id:
            groups.append(current_group)
            current_group = []
            current_turn_id = int(row.turn_id)
        current_group.append(row)
    if current_group:
        groups.append(current_group)
    return groups
