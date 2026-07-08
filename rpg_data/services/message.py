"""Session message service for mutable main history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from loguru import logger
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
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        tool_call_id: str | None = None,
        tool_calls_json: str | None = None,
        metadata_json: str | None = None,
    ) -> models.SessionMessage | None:
        updated = self._store.update(
            message_id,
            role=role,
            content=content,
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
        """Return unprocessed message groups eligible for summary compression.

        Message-level ``summary_processed`` is the correctness cursor.  Turn
        grouping is only used to apply ``keep_recent_turns`` and batch windows:
        explicit metadata is used when trustworthy, otherwise user/pair fallback
        grouping is used and a warning is emitted.
        """
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
        batch_id: int,
    ) -> int:
        return self._store.mark_summary_processed(
            session_id,
            message_ids,
            batch_id=batch_id,
        )

    def list_story_memory_unprocessed_turn_groups(
        self,
        session_id: str,
    ) -> list[list[models.SessionMessage]]:
        """Return unprocessed message groups for story-memory extraction.

        Story memory has no keep window.  The processed flag remains the
        correctness cursor; grouping is only the extraction window shape.
        """
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

    first_explicit = next(
        (
            index
            for index, row in enumerate(conversation_rows)
            if row.turn_id > 0 and row.seq_in_turn > 0
        ),
        len(conversation_rows),
    )
    if first_explicit < len(conversation_rows):
        prefix = conversation_rows[:first_explicit]
        suffix = conversation_rows[first_explicit:]
        if _has_trustworthy_turn_metadata(suffix):
            if prefix:
                _warn_fallback_grouping(session_id, purpose, prefix, reason="missing explicit turn metadata prefix")
            return _legacy_groups(prefix) + _explicit_turn_groups(suffix)

    _warn_fallback_grouping(session_id, purpose, conversation_rows, reason="untrustworthy turn metadata")
    return _legacy_groups(conversation_rows)


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


def _legacy_groups(rows: list[models.SessionMessage]) -> list[list[models.SessionMessage]]:
    if not rows:
        return []
    if any(row.role == models.MESSAGE_ROLE_USER for row in rows):
        return _user_anchor_groups(rows)
    return _pair_groups(rows)


def _user_anchor_groups(rows: list[models.SessionMessage]) -> list[list[models.SessionMessage]]:
    user_indices = [
        index
        for index, row in enumerate(rows)
        if row.role == models.MESSAGE_ROLE_USER
    ]
    groups: list[list[models.SessionMessage]] = []
    for index, user_index in enumerate(user_indices):
        start = 0 if index == 0 else user_index
        end = user_indices[index + 1] if index + 1 < len(user_indices) else len(rows)
        groups.append(rows[start:end])
    return groups


def _pair_groups(rows: list[models.SessionMessage]) -> list[list[models.SessionMessage]]:
    return [rows[index:index + 2] for index in range(0, len(rows), 2)]


def _warn_fallback_grouping(
    session_id: str,
    purpose: str,
    rows: list[models.SessionMessage],
    *,
    reason: str,
) -> None:
    if not rows:
        return
    invalid_count = sum(1 for row in rows if row.turn_id <= 0 or row.seq_in_turn <= 0)
    logger.warning(
        "[MessageService] fallback round grouping for {}: session_id={}, reason={}, rows={}, invalid_turn_metadata={}; message processed flags remain authoritative",
        purpose,
        session_id,
        reason,
        len(rows),
        invalid_count,
    )
