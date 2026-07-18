"""Summary and story-memory processing progress for one session."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.context.models import Message
from rpg_core.session.grouping import iter_turn_groups, uses_fallback_grouping
from rpg_core.session.models import SessionRuntimeState

if TYPE_CHECKING:
    from rpg_data.services import DataServiceGateway


_TAG = "[SessionManager]"


class SessionProgress:
    """Own message-level summary and story-memory processing state."""

    def __init__(
        self,
        state: SessionRuntimeState,
        *,
        session_id: Callable[[], str],
        history_enabled: Callable[[], bool],
        require_gateway: Callable[[], DataServiceGateway],
    ) -> None:
        self._state = state
        self._session_id = session_id
        self._history_enabled = history_enabled
        self._require_gateway = require_gateway

    def summary_turn_groups_for_compression(
        self,
        keep_recent_turns: int,
    ) -> list[list[Message]]:
        """Return unprocessed message groups eligible for summary compression."""
        if self._history_enabled():
            groups = self._require_gateway().messages.list_summary_candidate_turn_groups(
                self._session_id(),
                keep_recent_turns=keep_recent_turns,
            )
            return [
                [Message.from_dict(row.to_message_dict()) for row in group]
                for group in groups
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
            groups = self._require_gateway().messages.list_summary_unprocessed_turn_groups(
                self._session_id()
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
            self._require_gateway().messages.mark_summary_processed(
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
            self._require_gateway().messages.mark_summary_batches_processed(
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
            groups = self._require_gateway().messages.list_story_memory_unprocessed_turn_groups(
                self._session_id()
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
            self._require_gateway().messages.mark_story_memory_processed(
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
            return self._require_gateway().messages.count_story_memory_unprocessed_turns(
                self._session_id()
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
