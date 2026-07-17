"""SessionManager — session lifecycle and rpg_data-backed conversation history."""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

from rpg_core.context.rpg_context import Message, Role
from rpg_core.session.turn_metadata import (
    InvalidTurnMetadataError,
    has_trustworthy_turn_metadata,
    validate_turn_metadata,
)

_TAG = "[SessionManager]"

_DEFAULT_SESSION_ID = "default"

# Public constant for use by API and other layers.
DEFAULT_SESSION_ID = _DEFAULT_SESSION_ID
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_SESSION_ID_MAX_LENGTH = 64


@dataclass(frozen=True)
class ContextHistorySnapshot:
    """Main-Agent history projection derived from ``summary_processed``."""

    messages: tuple[Message, ...]
    filtered_message_count: int


class SessionManager:
    """Owns in-memory conversation history for one rpg_data session."""

    # ── Session ID validation (static) ─────────────────────────────────

    @staticmethod
    def is_valid_session_id(session_id: str) -> bool:
        """Return whether *session_id* matches the repository naming rule."""
        return len(session_id) <= _SESSION_ID_MAX_LENGTH and bool(_SESSION_ID_PATTERN.fullmatch(session_id))

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        """Validate *session_id* and return it unchanged on success."""
        if len(session_id) > _SESSION_ID_MAX_LENGTH:
            raise ValueError(f"session_id must be at most {_SESSION_ID_MAX_LENGTH} characters long")
        if not SessionManager.is_valid_session_id(session_id):
            raise ValueError("session_id must match ^[A-Za-z0-9_]+$")
        return session_id

    def __init__(
        self,
        session_id: str = None,  # type: ignore[assignment]
        workspace: str = "",
        history_enabled: bool = True,
    ) -> None:
        self._session_id = session_id if session_id is not None else _DEFAULT_SESSION_ID
        self._workspace = workspace
        self._history_enabled = history_enabled
        self.__history: list[Message] = []
        self._active_turn_id: int | None = None
        self._turn_seq_by_turn: dict[int, int] = {}
        self._story_memory_processed_message_keys: set[int] = set()
        self._summary_processed_message_keys: set[int] = set()

    # ── Public API — history ───────────────────────────────────────────

    @property
    def history(self) -> list[Message]:
        """Read-only snapshot of in-memory history."""
        return list(self.__history)

    @property
    def _history(self) -> list[Message]:
        """Compatibility snapshot for legacy internal access.

        Returns a copy so callers cannot mutate internal state by accident.
        """
        return list(self.__history)

    def load(self) -> None:
        """Load current session messages from rpg_data into memory."""
        self.__history = []
        if not self._history_enabled:
            self._rebuild_turn_state()
            logger.debug(_TAG + " history disabled; using empty in-memory history for '{}'", self._session_id)
            return

        gateway = self._require_data_session()
        rows = gateway.messages.list(self._session_id)
        try:
            validate_turn_metadata(rows, label="history")
        except InvalidTurnMetadataError as exc:
            logger.opt(exception=exc).error(
                _TAG + " invalid persisted turn metadata while loading history: session_id={}, rows={}, error={}",
                self._session_id,
                len(rows),
                exc,
            )
            raise

        self.__history = [
            Message.from_dict(row.to_message_dict())
            for row in rows
        ]
        self._rebuild_turn_state()
        logger.debug(_TAG + " loaded {} message(s) for session '{}'", len(self.__history), self._session_id)

    def context_history(self) -> ContextHistorySnapshot:
        """Return the history visible to the main Agent context.

        Persisted sessions read the current SQLite flags on every call so a
        completed compaction takes effect without reloading the cached Agent.
        Frontend/history callers continue to use :attr:`history` or the data
        service's unfiltered list methods.
        """
        if self._history_enabled:
            projection = self._require_data_session().messages.list_for_agent_context(
                self._session_id
            )
            messages = tuple(
                Message.from_dict(row.to_message_dict())
                for row in projection.messages
            )
            logger.debug(
                _TAG + " context history projected: session_id={}, kept={}, filtered={}",
                self._session_id,
                len(messages),
                projection.filtered_message_count,
            )
            return ContextHistorySnapshot(
                messages=messages,
                filtered_message_count=projection.filtered_message_count,
            )

        messages = tuple(
            message
            for message in self.__history
            if self._in_memory_message_key(message)
            not in self._summary_processed_message_keys
        )
        return ContextHistorySnapshot(
            messages=messages,
            filtered_message_count=len(self.__history) - len(messages),
        )

    def begin_turn(self) -> int:
        """Allocate and activate the next turn id."""
        latest = self.latest_turn_id(self.__history)
        if self._history_enabled:
            latest = max(latest, self._require_data_session().messages.latest_turn_id(self._session_id))
        if self._active_turn_id is not None:
            latest = max(latest, self._active_turn_id)

        turn_id = latest + 1
        self._active_turn_id = turn_id
        self._turn_seq_by_turn[turn_id] = 1
        return turn_id

    def end_turn(self, turn_id: int | None = None) -> None:
        """Clear the active turn marker if it matches *turn_id*."""
        if turn_id is None or self._active_turn_id == turn_id:
            self._active_turn_id = None

    # ── turn helpers ────────────────────────────────────────────────

    @staticmethod
    def has_explicit_turn_ids(messages: list[Message]) -> bool:
        """Return whether any message carries a positive ``turn_id``."""
        return any(msg.turn_id > 0 for msg in messages)

    @staticmethod
    def has_trustworthy_turn_ids(messages: list[Message]) -> bool:
        """Return whether explicit turn ids can be used safely."""
        return has_trustworthy_turn_metadata(messages)

    @staticmethod
    def validate_turn_metadata(messages: list[Message], *, label: str = "history") -> None:
        """Strictly validate explicit turn metadata for external operations."""
        validate_turn_metadata(messages, label=label)

    def validate_loaded_turn_metadata(self, *, label: str = "history") -> None:
        """Strictly validate the currently loaded in-memory history."""
        self.validate_turn_metadata(self.__history, label=label)

    @classmethod
    def iter_turn_groups(cls, messages: list[Message]) -> list[list[Message]]:
        """Group messages into logical turns.

        Priority is explicit ``turn_id`` first. If no trustworthy explicit ids
        exist, fall back to ``user`` anchors. If no user anchor is present,
        fall back to 2-message windows, with a single trailing message kept as
        its own turn.
        """
        if not messages:
            return []

        first_explicit = next(
            (i for i, msg in enumerate(messages) if msg.turn_id > 0 and msg.seq_in_turn > 0),
            len(messages),
        )
        if first_explicit < len(messages):
            suffix = messages[first_explicit:]
            if cls.has_trustworthy_turn_ids(suffix):
                return cls._iter_legacy_groups(messages[:first_explicit]) + cls._iter_explicit_turn_groups(suffix)

        return cls._iter_legacy_groups(messages)

    @classmethod
    def count_turns(cls, messages: list[Message]) -> int:
        return len(cls.iter_turn_groups(messages))

    @classmethod
    def slice_recent_turns(cls, messages: list[Message], keep_turns: int) -> list[Message]:
        if keep_turns <= 0:
            return []

        groups = cls.iter_turn_groups(messages)
        if len(groups) <= keep_turns:
            return list(messages)

        return [msg for group in groups[-keep_turns:] for msg in group]

    @classmethod
    def split_into_turn_batches(
        cls,
        messages: list[Message],
        batch_turn_size: int,
    ) -> list[tuple[int, list[Message], int]]:
        if batch_turn_size <= 0:
            raise ValueError("batch_turn_size must be positive")

        groups = cls.iter_turn_groups(messages)
        if not groups:
            return []

        batches: list[tuple[int, list[Message], int]] = []
        batch_id = 0
        start = 0
        while start < len(groups):
            end = min(start + batch_turn_size, len(groups))
            batch_groups = groups[start:end]
            batch_messages = [msg for group in batch_groups for msg in group]
            batches.append((batch_id, batch_messages, end - start))
            batch_id += 1
            start = end
        return batches

    @staticmethod
    def latest_turn_id(messages: list[Message]) -> int:
        turn_ids = [msg.turn_id for msg in messages if msg.turn_id > 0]
        return max(turn_ids, default=0)

    def _validate_append_turn_metadata(self, message: Message) -> None:
        """Validate one append against the loaded turn sequence state."""
        if message.turn_id <= 0 or message.seq_in_turn <= 0:
            raise InvalidTurnMetadataError(
                "invalid turn metadata for append: turn_id and seq_in_turn must be positive integers"
            )

        latest = self.latest_turn_id(self.__history)
        if message.turn_id < latest:
            raise InvalidTurnMetadataError(
                "invalid turn metadata for append: turn_id must be nondecreasing"
            )

        next_seq = self._turn_seq_by_turn.get(message.turn_id)
        if next_seq is not None and message.seq_in_turn < next_seq:
            raise InvalidTurnMetadataError(
                "invalid turn metadata for append: seq_in_turn must increase inside the same turn"
            )

    def append(
        self,
        role: Role | str,
        content: str,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        *,
        mode: str = "ic",
    ) -> None:
        """Append a message to in-memory history and, when enabled, rpg_data."""
        role_value = Role(role).value
        if turn_id is None:
            turn_id = self._active_turn_id or self.begin_turn()
        if seq_in_turn is None:
            seq_in_turn = self._turn_seq_by_turn.get(turn_id, 1)

        text = str(content or "")
        pending = Message(role_value, text, mode=mode, turn_id=turn_id, seq_in_turn=seq_in_turn)
        self._validate_append_turn_metadata(pending)
        turn_id = pending.turn_id
        seq_in_turn = pending.seq_in_turn

        uid = 0
        if self._history_enabled:
            gateway = self._require_data_session()
            with gateway.database.atomic():
                row = gateway.messages.append(
                    self._session_id,
                    role_value,
                    text,
                    mode=pending.mode,
                    turn_id=turn_id,
                    seq_in_turn=seq_in_turn,
                )
                gateway.backup.messages.append(
                    self._session_id,
                    role_value,
                    text,
                    mode=pending.mode,
                    turn_id=turn_id,
                    seq_in_turn=seq_in_turn,
                )
            uid = row.id

        self._turn_seq_by_turn[turn_id] = seq_in_turn + 1
        self.__history.append(
            Message(
                role_value,
                text,
                mode=pending.mode,
                uid=uid,
                turn_id=turn_id,
                seq_in_turn=seq_in_turn,
            )
        )

    def clear(self) -> None:
        """Clear in-memory history and the mutable rpg_data message table."""
        if self._history_enabled:
            gateway = self._require_data_session()
            with gateway.database.atomic():
                gateway.messages.clear(self._session_id)
                gateway.narrative_outcomes.clear(self._session_id)
        self.replace_history([], persist=False)
        logger.debug(_TAG + " cleared history for session '{}'", self._session_id)

    def truncate(self, keep_from_index: int) -> int:
        """Remove all messages before *keep_from_index* from memory and main SQL table.

        The cold backup table is append-only and is not truncated.
        """
        before = len(self.__history)
        if keep_from_index <= 0:
            return 0

        if keep_from_index >= before:
            if self._history_enabled:
                gateway = self._require_data_session()
                with gateway.database.atomic():
                    gateway.messages.clear(self._session_id)
                    gateway.narrative_outcomes.clear(self._session_id)
            self.__history = []
            self._rebuild_turn_state()
            return before

        remaining = self.__history[keep_from_index:]
        if self._history_enabled:
            removed_turn_ids = {
                message.turn_id
                for message in self.__history[:keep_from_index]
                if message.turn_id > 0
            }
            boundary_uid = self.__history[keep_from_index].uid
            if boundary_uid > 0:
                gateway = self._require_data_session()
                with gateway.database.atomic():
                    gateway.messages.truncate_before_id(self._session_id, boundary_uid)
                    for turn_id in removed_turn_ids:
                        gateway.narrative_outcomes.delete_for_turn(
                            self._session_id,
                            turn_id,
                        )
            else:
                self.replace_history(remaining, persist=True)
                return before - len(self.__history)

        self.__history = remaining
        self._rebuild_turn_state()
        removed = before - len(self.__history)
        logger.debug(_TAG + " truncated: removed {} msgs, {} remaining", removed, len(self.__history))
        return removed

    def get_message(self, message_id: int) -> Message | None:
        """Return one message from this session by its persisted message id."""
        target_id = int(message_id)
        for message in self.__history:
            if message.uid == target_id:
                return message

        if not self._history_enabled:
            return None

        row = self._require_data_session().messages.get_for_session(self._session_id, target_id)
        if row is None:
            return None
        return Message.from_dict(row.to_message_dict())

    def turn_messages(self, turn_id: int) -> list[Message]:
        """Return loaded messages for one explicit turn id."""
        target_turn = int(turn_id)
        return [message for message in self.__history if message.turn_id == target_turn]

    def first_user_message_for_turn(self, turn_id: int) -> Message | None:
        """Return the first user message in a turn, if present."""
        messages = sorted(self.turn_messages(turn_id), key=lambda item: item.seq_in_turn or 0)
        return next((message for message in messages if message.is_user()), None)

    def truncate_from_turn(self, turn_id: int) -> int:
        """Remove *turn_id* and all following turns from mutable history.

        The backup message table remains append-only.
        """
        boundary_turn = int(turn_id)
        if boundary_turn <= 0:
            raise ValueError("turn_id must be positive")

        before = len(self.__history)
        if self._history_enabled:
            gateway = self._require_data_session()
            with gateway.database.atomic():
                removed = gateway.messages.truncate_from_turn(
                    self._session_id,
                    boundary_turn,
                )
                gateway.narrative_outcomes.delete_from_turn(
                    self._session_id,
                    boundary_turn,
                )
            self.load()
            return removed

        self.__history = [message for message in self.__history if message.turn_id < boundary_turn]
        self._intersect_in_memory_processing_keys()
        self._rebuild_turn_state()
        return before - len(self.__history)

    def update_message_content(self, message_id: int, content: str) -> Message:
        """Update a persisted message body and reload in-memory history."""
        target_id = int(message_id)
        if not self._history_enabled:
            for index, message in enumerate(self.__history):
                if message.uid == target_id:
                    self._discard_in_memory_processing_key(message)
                    updated = Message(
                        message.role,
                        str(content),
                        mode=message.mode,
                        uid=message.uid,
                        turn_id=message.turn_id,
                        seq_in_turn=message.seq_in_turn,
                        tool_call_id=message.tool_call_id,
                        tool_calls=message.tool_calls,
                    )
                    self.__history[index] = updated
                    self._rebuild_turn_state()
                    return updated
            raise FileNotFoundError(f"session message not found: {message_id}")

        gateway = self._require_data_session()
        with gateway.database.atomic():
            current = gateway.messages.get_for_session(self._session_id, target_id)
            if current is None:
                raise FileNotFoundError(f"session message not found: {message_id}")
            updated_row = gateway.messages.update(target_id, content=str(content))
            if updated_row is None:
                raise FileNotFoundError(f"session message not found: {message_id}")
            if current.role == "user":
                gateway.narrative_outcomes.delete_for_turn(
                    self._session_id,
                    current.turn_id,
                )
        self.load()
        return Message.from_dict(updated_row.to_message_dict())

    def delete_message(self, message_id: int) -> Message:
        """Delete one message from mutable history and reload memory."""
        target_id = int(message_id)
        if not self._history_enabled:
            for index, message in enumerate(self.__history):
                if message.uid == target_id:
                    deleted = self.__history.pop(index)
                    self._discard_in_memory_processing_key(deleted)
                    self._rebuild_turn_state()
                    return deleted
            raise FileNotFoundError(f"session message not found: {message_id}")

        gateway = self._require_data_session()
        with gateway.database.atomic():
            current = gateway.messages.get_for_session(self._session_id, target_id)
            if current is None:
                raise FileNotFoundError(f"session message not found: {message_id}")
            if not gateway.messages.delete_for_session(self._session_id, target_id):
                raise FileNotFoundError(f"session message not found: {message_id}")
            gateway.narrative_outcomes.delete_for_turn(
                self._session_id,
                current.turn_id,
            )
        self.load()
        return Message.from_dict(current.to_message_dict())

    # ── Session switch ─────────────────────────────────────────────────

    def switch_to(self, session_id: str) -> None:
        """Switch to a different rpg_data session and reload history."""
        self.validate_session_id(session_id)
        self._session_id = session_id
        self.replace_history([], persist=False)
        self._story_memory_processed_message_keys.clear()
        self._summary_processed_message_keys.clear()
        if self._history_enabled:
            self.load()
        logger.debug(_TAG + " switched to session '{}'", session_id)

    # ── Metadata ───────────────────────────────────────────────────────

    @property
    def meta(self) -> dict[str, object]:
        if not self._history_enabled:
            return {}

        gateway = self._require_data_session()
        session = gateway.catalog.get_session(self._session_id)
        if session is None:
            return {}
        return {
            "id": str(session.id),
            "workspace_id": str(session.workspace_id),
            "story_id": int(session.story_id),
            "title": str(session.title or session.id),
            "description": str(session.description or ""),
            "created_at": str(session.created_at),
            "updated_at": str(session.updated_at),
        }

    # ── Summary and story-memory progress tracking ─────────────────────

    def summary_turn_groups_for_compression(self, keep_recent_turns: int) -> list[list[Message]]:
        """Return unprocessed message groups eligible for summary compression.

        Processing progress is message-level. Turn grouping is only used for
        the recent keep window and batch sizing.
        """
        if self._history_enabled:
            groups = self._require_data_session().messages.list_summary_candidate_turn_groups(
                self._session_id,
                keep_recent_turns=keep_recent_turns,
            )
            return [
                [Message.from_dict(row.to_message_dict()) for row in group]
                for group in groups
            ]

        conversation = [
            message
            for message in self.__history
            if not message.is_system()
        ]

        if not any(
            self._in_memory_message_key(message) not in self._summary_processed_message_keys
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
                if self._in_memory_message_key(message) not in self._summary_processed_message_keys
            ]
            for group in eligible_groups
            if any(
                self._in_memory_message_key(message) not in self._summary_processed_message_keys
                for message in group
            )
        ]

    def summary_unprocessed_turn_groups(self) -> list[list[Message]]:
        """Return all unprocessed summary groups without mode/keep policy."""
        if self._history_enabled:
            groups = self._require_data_session().messages.list_summary_unprocessed_turn_groups(
                self._session_id
            )
            return [
                [Message.from_dict(row.to_message_dict()) for row in group]
                for group in groups
            ]
        return self._conversation_turn_groups([
            message
            for message in self.__history
            if not message.is_system()
            and self._in_memory_message_key(message)
            not in self._summary_processed_message_keys
        ], purpose="summary")

    def count_summary_turns_for_compression(self, keep_recent_turns: int) -> int:
        return len(self.summary_turn_groups_for_compression(keep_recent_turns))

    def mark_summary_messages_processed(
        self,
        messages: list[Message],
        *,
        batch_id: int | None,
    ) -> None:
        """Mark messages included in a successfully written summary batch."""
        if not messages:
            return
        if self._history_enabled:
            self._require_data_session().messages.mark_summary_processed(
                self._session_id,
                self._message_ids(messages),
                batch_id=batch_id,
            )
            return
        self._summary_processed_message_keys.update(
            self._in_memory_message_key(msg) for msg in messages
        )

    def mark_summary_batches_processed(
        self,
        batches: list[tuple[list[Message], int]],
    ) -> None:
        """Atomically advance every successfully materialized summary batch."""
        if not batches:
            return
        if self._history_enabled:
            self._require_data_session().messages.mark_summary_batches_processed(
                self._session_id,
                [
                    (self._message_ids(messages), batch_id)
                    for messages, batch_id in batches
                ],
            )
            return
        for messages, _ in batches:
            self._summary_processed_message_keys.update(
                self._in_memory_message_key(message) for message in messages
            )

    def story_turn_groups_since_last_extraction(self) -> list[list[Message]]:
        """Return logical turn groups not yet processed for story memory."""
        if self._history_enabled:
            groups = self._require_data_session().messages.list_story_memory_unprocessed_turn_groups(
                self._session_id
            )
            return [
                [Message.from_dict(row.to_message_dict()) for row in group]
                for group in groups
            ]
        return [
            group
            for group in self._conversation_turn_groups([
                message
                for message in self.__history
                if not message.is_system()
                and self._in_memory_message_key(message) not in self._story_memory_processed_message_keys
            ], purpose="story_memory")
        ]

    def story_messages_since_last_extraction(self) -> list[Message]:
        """Return messages not yet processed for story memory."""
        groups = self.story_turn_groups_since_last_extraction()
        return [msg for group in groups for msg in group]

    def mark_story_messages_processed(self, messages: list[Message]) -> None:
        """Mark messages examined by story-memory extraction."""
        if not messages:
            return
        if self._history_enabled:
            self._require_data_session().messages.mark_story_memory_processed(
                self._session_id,
                self._message_ids(messages),
            )
            return
        self._story_memory_processed_message_keys.update(
            self._in_memory_message_key(msg) for msg in messages
        )

    def count_new_turns_since_story(self) -> int:
        """Count conversation turns not yet processed for story memory."""
        if self._history_enabled:
            return self._require_data_session().messages.count_story_memory_unprocessed_turns(
                self._session_id
            )
        return len(self.story_turn_groups_since_last_extraction())

    # ── History-enabled flag ───────────────────────────────────────────

    @property
    def history_enabled(self) -> bool:
        return self._history_enabled

    @property
    def session_id(self) -> str:
        return self._session_id

    def set_history_enabled(self, enabled: bool) -> None:
        self._history_enabled = enabled

    def replace_history(self, history: list[Message], *, persist: bool | None = None) -> None:
        """Replace in-memory history and optionally rewrite the mutable SQL table."""
        self.__history = list(history)
        if persist is None:
            persist = self._history_enabled

        if persist and self._history_enabled:
            self.validate_loaded_turn_metadata(label="history")
            gateway = self._require_data_session()
            with gateway.database.atomic():
                rows = gateway.messages.replace(
                    self._session_id,
                    (msg.to_persistence_dict() for msg in self.__history),
                )
                gateway.narrative_outcomes.retain_turns(
                    self._session_id,
                    (message.turn_id for message in self.__history),
                )
            self.__history = [Message.from_dict(row.to_message_dict()) for row in rows]

        self._rebuild_turn_state()
        self._intersect_in_memory_processing_keys()

    def _rebuild_turn_state(self) -> None:
        """Reconstruct turn sequence counters from the current in-memory history."""
        seq_by_turn: dict[int, int] = {}
        for msg in self.__history:
            if msg.turn_id <= 0:
                continue
            seq_by_turn[msg.turn_id] = max(seq_by_turn.get(msg.turn_id, 0), msg.seq_in_turn)
        self._turn_seq_by_turn = {turn_id: seq + 1 for turn_id, seq in seq_by_turn.items()}
        self._active_turn_id = None

    @staticmethod
    def _message_ids(messages: list[Message]) -> list[int]:
        return sorted({msg.uid for msg in messages if msg.uid > 0})

    def _conversation_turn_groups(
        self,
        messages: list[Message],
        *,
        purpose: str,
    ) -> list[list[Message]]:
        conversation_messages = [msg for msg in messages if not msg.is_system()]
        if self._uses_fallback_grouping(conversation_messages):
            invalid_count = sum(
                1
                for msg in conversation_messages
                if msg.turn_id <= 0 or msg.seq_in_turn <= 0
            )
            logger.warning(
                _TAG + " fallback round grouping for {}: session_id={}, rows={}, invalid_turn_metadata={}; message processed keys remain authoritative",
                purpose,
                self._session_id,
                len(conversation_messages),
                invalid_count,
            )
        return self.iter_turn_groups(conversation_messages)

    @classmethod
    def _uses_fallback_grouping(cls, messages: list[Message]) -> bool:
        if not messages:
            return False
        first_explicit = next(
            (i for i, msg in enumerate(messages) if msg.turn_id > 0 and msg.seq_in_turn > 0),
            len(messages),
        )
        if first_explicit >= len(messages):
            return True
        return first_explicit > 0 or not cls.has_trustworthy_turn_ids(messages[first_explicit:])

    @staticmethod
    def _in_memory_message_key(message: Message) -> int:
        return id(message)

    def _discard_in_memory_processing_key(self, message: Message) -> None:
        key = self._in_memory_message_key(message)
        self._story_memory_processed_message_keys.discard(key)
        self._summary_processed_message_keys.discard(key)

    def _intersect_in_memory_processing_keys(self) -> None:
        current_keys = {self._in_memory_message_key(message) for message in self.__history}
        self._story_memory_processed_message_keys.intersection_update(current_keys)
        self._summary_processed_message_keys.intersection_update(current_keys)

    def _require_data_session(self):
        from rpg_data.services import get_data_service_gateway

        gateway = get_data_service_gateway()
        if gateway.catalog.get_session(self._session_id) is None:
            raise FileNotFoundError(f"Session not found in rpg_data: {self._session_id}")
        return gateway

    @staticmethod
    def _iter_legacy_groups(messages: list[Message]) -> list[list[Message]]:
        if any(msg.is_user() for msg in messages):
            return SessionManager._iter_user_anchor_groups(messages)
        return SessionManager._iter_pairs(messages)

    @staticmethod
    def _iter_user_anchor_groups(messages: list[Message]) -> list[list[Message]]:
        user_indices = [i for i, msg in enumerate(messages) if msg.is_user()]
        if not user_indices:
            return SessionManager._iter_pairs(messages)

        groups: list[list[Message]] = []
        for idx, user_idx in enumerate(user_indices):
            start = 0 if idx == 0 else user_idx
            end = user_indices[idx + 1] if idx + 1 < len(user_indices) else len(messages)
            groups.append(messages[start:end])
        return groups

    @staticmethod
    def _iter_pairs(messages: list[Message]) -> list[list[Message]]:
        if not messages:
            return []
        groups: list[list[Message]] = []
        idx = 0
        while idx < len(messages):
            groups.append(messages[idx:idx + 2])
            idx += 2
        return groups

    @staticmethod
    def _iter_explicit_turn_groups(messages: list[Message]) -> list[list[Message]]:
        if not messages:
            return []

        groups: list[list[Message]] = []
        current_turn_id = messages[0].turn_id
        current_group: list[Message] = []
        for msg in messages:
            if msg.turn_id <= 0 or msg.seq_in_turn <= 0:
                if current_group:
                    groups.append(current_group)
                    current_group = []
                groups.append([msg])
                continue
            if msg.turn_id != current_turn_id and current_group:
                groups.append(current_group)
                current_group = []
            current_turn_id = msg.turn_id
            current_group.append(msg)
        if current_group:
            groups.append(current_group)
        return groups
