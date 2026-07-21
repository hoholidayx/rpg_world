"""Summary and story-memory processing progress for one session."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from typing import Protocol

from loguru import logger

from rpg_core.context.models import Message
from rpg_core.session.grouping import iter_turn_groups, uses_fallback_grouping
from rpg_core.session.models import SessionRuntimeState
from rpg_core.session.turn_metadata import validate_turn_metadata
from rpg_data.model.session import MESSAGE_ROLE_SYSTEM, SessionMessage


_TAG = "[SessionManager]"


class SessionProgressDataPort(Protocol):
    def list_messages_filtered(
        self,
        session_id: str,
        *,
        excluded_roles: Collection[str] = (),
        summary_processed: bool | None = None,
        story_memory_processed: bool | None = None,
    ) -> list[SessionMessage]: ...

    def count_message_turns_filtered(
        self,
        session_id: str,
        *,
        excluded_roles: Collection[str] = (),
        summary_processed: bool | None = None,
        story_memory_processed: bool | None = None,
    ) -> int: ...

    def mark_summary_messages_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
        *,
        batch_id: int | None,
    ) -> int: ...

    def mark_summary_message_batches_processed(
        self,
        session_id: str,
        batches: Iterable[tuple[Iterable[int], int]],
    ) -> int: ...

    def mark_story_memory_messages_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int: ...


class SessionProgress:
    """Own message-level summary and story-memory processing state."""

    def __init__(
        self,
        state: SessionRuntimeState,
        *,
        session_id: Callable[[], str],
        history_enabled: Callable[[], bool],
        require_data: Callable[[], SessionProgressDataPort],
    ) -> None:
        self._state = state
        self._session_id = session_id
        self._history_enabled = history_enabled
        self._require_data = require_data

    def summary_turn_groups_for_compression(
        self,
        keep_recent_turns: int,
    ) -> list[list[Message]]:
        """Return unprocessed message groups eligible for summary compression."""
        if self._history_enabled():
            rows = self._require_data().list_messages_filtered(
                self._session_id(),
                excluded_roles=(MESSAGE_ROLE_SYSTEM,),
            )
            if not any(not row.summary_processed for row in rows):
                return []
            groups = _persisted_turn_groups(
                rows,
                session_id=self._session_id(),
                purpose="summary",
            )
            keep = max(0, int(keep_recent_turns))
            eligible = groups if keep <= 0 else groups[:-keep]
            return [
                [
                    Message.from_dict(row.to_message_dict())
                    for row in group
                    if not row.summary_processed
                ]
                for group in eligible
                if any(not row.summary_processed for row in group)
            ]

        conversation = [
            message
            for message in self._state.messages
            if not message.is_system()
        ]

        if not any(
            self._in_memory_message_key(message)
            not in self._state.summary_processed_message_keys
            for message in conversation
        ):
            return []

        groups = self._conversation_turn_groups(conversation, purpose="summary")
        keep = max(0, int(keep_recent_turns))
        eligible_groups = groups if keep <= 0 else groups[:-keep]
        return [
            [
                message
                for message in group
                if self._in_memory_message_key(message)
                not in self._state.summary_processed_message_keys
            ]
            for group in eligible_groups
            if any(
                self._in_memory_message_key(message)
                not in self._state.summary_processed_message_keys
                for message in group
            )
        ]

    def summary_unprocessed_turn_groups(self) -> list[list[Message]]:
        """Return all unprocessed summary groups without mode/keep policy."""
        if self._history_enabled():
            groups = _persisted_turn_groups(
                self._require_data().list_messages_filtered(
                    self._session_id(),
                    excluded_roles=(MESSAGE_ROLE_SYSTEM,),
                    summary_processed=False,
                ),
                session_id=self._session_id(),
                purpose="summary",
            )
            return [
                [Message.from_dict(row.to_message_dict()) for row in group]
                for group in groups
            ]
        return self._conversation_turn_groups(
            [
                message
                for message in self._state.messages
                if not message.is_system()
                and self._in_memory_message_key(message)
                not in self._state.summary_processed_message_keys
            ],
            purpose="summary",
        )

    def mark_summary_messages_processed(
        self,
        messages: list[Message],
        *,
        batch_id: int | None,
    ) -> None:
        """Mark messages included in a successfully written summary batch."""
        if not messages:
            return
        if self._history_enabled():
            self._require_data().mark_summary_messages_processed(
                self._session_id(),
                self._message_ids(messages),
                batch_id=batch_id,
            )
            return
        self._state.summary_processed_message_keys.update(
            self._in_memory_message_key(message) for message in messages
        )

    def mark_summary_batches_processed(
        self,
        batches: list[tuple[list[Message], int]],
    ) -> None:
        """Atomically advance every successfully materialized summary batch."""
        if not batches:
            return
        if self._history_enabled():
            self._require_data().mark_summary_message_batches_processed(
                self._session_id(),
                [
                    (self._message_ids(messages), batch_id)
                    for messages, batch_id in batches
                ],
            )
            return
        for messages, _ in batches:
            self._state.summary_processed_message_keys.update(
                self._in_memory_message_key(message) for message in messages
            )

    def story_turn_groups_since_last_extraction(self) -> list[list[Message]]:
        """Return logical turn groups not yet processed for story memory."""
        if self._history_enabled():
            groups = _persisted_turn_groups(
                self._require_data().list_messages_filtered(
                    self._session_id(),
                    excluded_roles=(MESSAGE_ROLE_SYSTEM,),
                    story_memory_processed=False,
                ),
                session_id=self._session_id(),
                purpose="story_memory",
            )
            return [
                [Message.from_dict(row.to_message_dict()) for row in group]
                for group in groups
            ]
        return [
            group
            for group in self._conversation_turn_groups(
                [
                    message
                    for message in self._state.messages
                    if not message.is_system()
                    and self._in_memory_message_key(message)
                    not in self._state.story_memory_processed_message_keys
                ],
                purpose="story_memory",
            )
        ]

    def story_messages_since_last_extraction(self) -> list[Message]:
        groups = self.story_turn_groups_since_last_extraction()
        return [message for group in groups for message in group]

    def mark_story_messages_processed(self, messages: list[Message]) -> None:
        """Mark messages examined by story-memory extraction."""
        if not messages:
            return
        if self._history_enabled():
            self._require_data().mark_story_memory_messages_processed(
                self._session_id(),
                self._message_ids(messages),
            )
            return
        self._state.story_memory_processed_message_keys.update(
            self._in_memory_message_key(message) for message in messages
        )

    def count_new_turns_since_story(self) -> int:
        """Count conversation turns not yet processed for story memory."""
        if self._history_enabled():
            return self._require_data().count_message_turns_filtered(
                self._session_id(),
                excluded_roles=(MESSAGE_ROLE_SYSTEM,),
                story_memory_processed=False,
            )
        return len(self.story_turn_groups_since_last_extraction())

    def is_summary_processed(self, message: Message) -> bool:
        return (
            self._in_memory_message_key(message)
            in self._state.summary_processed_message_keys
        )

    def discard_in_memory_processing_key(self, message: Message) -> None:
        key = self._in_memory_message_key(message)
        self._state.story_memory_processed_message_keys.discard(key)
        self._state.summary_processed_message_keys.discard(key)

    def intersect_in_memory_processing_keys(self) -> None:
        current_keys = {
            self._in_memory_message_key(message)
            for message in self._state.messages
        }
        self._state.story_memory_processed_message_keys.intersection_update(current_keys)
        self._state.summary_processed_message_keys.intersection_update(current_keys)

    def _conversation_turn_groups(
        self,
        messages: list[Message],
        *,
        purpose: str,
    ) -> list[list[Message]]:
        conversation_messages = [message for message in messages if not message.is_system()]
        if uses_fallback_grouping(conversation_messages):
            invalid_count = sum(
                1
                for message in conversation_messages
                if message.turn_id <= 0 or message.seq_in_turn <= 0
            )
            logger.warning(
                _TAG + " fallback round grouping for {}: session_id={}, rows={}, invalid_turn_metadata={}; message processed keys remain authoritative",
                purpose,
                self._session_id(),
                len(conversation_messages),
                invalid_count,
            )
        return iter_turn_groups(conversation_messages)

    @staticmethod
    def _message_ids(messages: list[Message]) -> list[int]:
        return sorted({message.uid for message in messages if message.uid > 0})

    @staticmethod
    def _in_memory_message_key(message: Message) -> int:
        return id(message)


def _persisted_turn_groups(
    rows: list[SessionMessage],
    *,
    session_id: str,
    purpose: str,
) -> list[list[SessionMessage]]:
    if not rows:
        return []
    validate_turn_metadata(rows, label=f"{purpose}: session_id={session_id}")
    groups: list[list[SessionMessage]] = []
    current_turn_id = rows[0].turn_id
    current: list[SessionMessage] = []
    for row in rows:
        if row.turn_id != current_turn_id:
            groups.append(current)
            current = []
            current_turn_id = row.turn_id
        current.append(row)
    if current:
        groups.append(current)
    return groups


__all__ = [
    "SessionProgress",
    "SessionProgressDataPort",
]
