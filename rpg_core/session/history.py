"""Conversation history lifecycle and persistence for one session."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import ContextManager, Protocol

from loguru import logger

from rpg_core.context.models import Message, Role
from rpg_core.session.grouping import latest_turn_id
from rpg_core.session.models import ContextHistorySnapshot, SessionRuntimeState
from rpg_core.session.progress import SessionProgress
from rpg_core.session.turn_metadata import InvalidTurnMetadataError, validate_turn_metadata
from rpg_data.model.session import Session, SessionMessage


_TAG = "[SessionManager]"


class SessionHistoryDataPort(Protocol):
    def transaction(self) -> ContextManager[None]: ...

    def get_session(self, session_id: str) -> Session | None: ...

    def list_messages(self, session_id: str) -> list[SessionMessage]: ...

    def latest_message_turn_id(self, session_id: str) -> int: ...

    def get_message_for_session(
        self,
        session_id: str,
        message_id: int,
    ) -> SessionMessage | None: ...

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        mode: str,
        turn_id: int,
        seq_in_turn: int,
        metadata_json: str,
    ) -> SessionMessage: ...

    def append_backup_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        mode: str,
        turn_id: int,
        seq_in_turn: int,
        metadata_json: str,
    ) -> SessionMessage: ...

    def update_message_content(
        self,
        message_id: int,
        content: str,
    ) -> SessionMessage | None: ...

    def delete_message_for_session(self, session_id: str, message_id: int) -> bool: ...

    def clear_messages(self, session_id: str) -> int: ...

    def replace_messages(
        self,
        session_id: str,
        messages: Iterable[SessionMessage | Mapping[str, object]],
    ) -> list[SessionMessage]: ...

    def truncate_messages_before_id(self, session_id: str, boundary_id: int) -> int: ...

    def truncate_messages_from_turn(self, session_id: str, turn_id: int) -> int: ...

    def reset_message_processing(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int: ...

    def clear_narrative_outcomes(self, session_id: str) -> int: ...

    def delete_narrative_outcomes_for_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int: ...

    def delete_narrative_outcomes_from_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int: ...

    def retain_narrative_outcome_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> int: ...

    def clear_plot_decisions(self, session_id: str) -> int: ...

    def delete_plot_decisions_for_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int: ...

    def delete_plot_decisions_from_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> int: ...

    def retain_plot_decision_turns(
        self,
        session_id: str,
        turn_ids: Iterable[int],
    ) -> int: ...


class SessionHistory:
    """Own ordered messages, turn allocation, and mutable history writes."""

    def __init__(
        self,
        state: SessionRuntimeState,
        progress: SessionProgress,
        *,
        session_id: Callable[[], str],
        history_enabled: Callable[[], bool],
        require_data: Callable[[], SessionHistoryDataPort],
    ) -> None:
        self._state = state
        self._progress = progress
        self._session_id = session_id
        self._history_enabled = history_enabled
        self._require_data = require_data

    @property
    def messages(self) -> list[Message]:
        """Return a read-only snapshot of in-memory history."""
        return list(self._state.messages)

    def load(self) -> None:
        """Load current session messages from rpg_data into memory."""
        self._state.messages = []
        if not self._history_enabled():
            self._rebuild_turn_state()
            logger.debug(
                _TAG + " history disabled; using empty in-memory history for '{}'",
                self._session_id(),
            )
            return

        rows = self._require_data().list_messages(self._session_id())
        try:
            validate_turn_metadata(rows, label="history")
        except InvalidTurnMetadataError as exc:
            logger.opt(exception=exc).error(
                _TAG + " invalid persisted turn metadata while loading history: session_id={}, rows={}, error={}",
                self._session_id(),
                len(rows),
                exc,
            )
            raise

        self._state.messages = [
            Message.from_dict(row.to_message_dict())
            for row in rows
        ]
        self._rebuild_turn_state()
        logger.debug(
            _TAG + " loaded {} message(s) for session '{}'",
            len(self._state.messages),
            self._session_id(),
        )

    def context_history(self) -> ContextHistorySnapshot:
        """Return the history visible to the main Agent context."""
        if self._history_enabled():
            rows = self._require_data().list_messages(self._session_id())
            projected = tuple(row for row in rows if not row.summary_processed)
            messages = tuple(
                Message.from_dict(row.to_message_dict())
                for row in projected
            )
            logger.debug(
                _TAG + " context history projected: session_id={}, kept={}, filtered={}",
                self._session_id(),
                len(messages),
                len(rows) - len(projected),
            )
            return ContextHistorySnapshot(
                messages=messages,
                filtered_message_count=len(rows) - len(projected),
            )

        messages = tuple(
            message
            for message in self._state.messages
            if not self._progress.is_summary_processed(message)
        )
        return ContextHistorySnapshot(
            messages=messages,
            filtered_message_count=len(self._state.messages) - len(messages),
        )

    def begin_turn(self) -> int:
        """Allocate and activate the next turn id."""
        latest = latest_turn_id(self._state.messages)
        if self._history_enabled():
            latest = max(
                latest,
                self._require_data().latest_message_turn_id(self._session_id()),
            )
        if self._state.active_turn_id is not None:
            latest = max(latest, self._state.active_turn_id)

        turn_id = latest + 1
        self._state.active_turn_id = turn_id
        self._state.turn_seq_by_turn[turn_id] = 1
        return turn_id

    def end_turn(self, turn_id: int | None = None) -> None:
        """Clear the active turn marker if it matches *turn_id*."""
        if turn_id is None or self._state.active_turn_id == turn_id:
            self._state.active_turn_id = None

    def validate_loaded_turn_metadata(self, *, label: str = "history") -> None:
        """Strictly validate the currently loaded in-memory history."""
        validate_turn_metadata(self._state.messages, label=label)

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
            turn_id = self._state.active_turn_id or self.begin_turn()
        if seq_in_turn is None:
            seq_in_turn = self._state.turn_seq_by_turn.get(turn_id, 1)

        text = str(content or "")
        pending = Message(
            role_value,
            text,
            mode=mode,
            turn_id=turn_id,
            seq_in_turn=seq_in_turn,
        )
        self._validate_append_turn_metadata(pending)
        turn_id = pending.turn_id
        seq_in_turn = pending.seq_in_turn

        uid = 0
        if self._history_enabled():
            data = self._require_data()
            with data.transaction():
                row = data.append_message(
                    self._session_id(),
                    role_value,
                    text,
                    mode=pending.mode,
                    turn_id=turn_id,
                    seq_in_turn=seq_in_turn,
                    metadata_json="{}",
                )
                data.append_backup_message(
                    self._session_id(),
                    role_value,
                    text,
                    mode=pending.mode,
                    turn_id=turn_id,
                    seq_in_turn=seq_in_turn,
                    metadata_json="{}",
                )
            uid = row.id

        self._state.turn_seq_by_turn[turn_id] = seq_in_turn + 1
        self._state.messages.append(
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
        if self._history_enabled():
            data = self._require_data()
            with data.transaction():
                data.clear_messages(self._session_id())
                data.clear_narrative_outcomes(self._session_id())
                data.clear_plot_decisions(self._session_id())
        self.replace([], persist=False)
        logger.debug(_TAG + " cleared history for session '{}'", self._session_id())

    def truncate(self, keep_from_index: int) -> int:
        """Remove messages before *keep_from_index* from memory and main SQL."""
        before = len(self._state.messages)
        if keep_from_index <= 0:
            return 0

        if keep_from_index >= before:
            if self._history_enabled():
                data = self._require_data()
                with data.transaction():
                    data.clear_messages(self._session_id())
                    data.clear_narrative_outcomes(self._session_id())
                    data.clear_plot_decisions(self._session_id())
            self._state.messages = []
            self._rebuild_turn_state()
            return before

        remaining = self._state.messages[keep_from_index:]
        if self._history_enabled():
            removed_turn_ids = {
                message.turn_id
                for message in self._state.messages[:keep_from_index]
                if message.turn_id > 0
            }
            boundary_uid = self._state.messages[keep_from_index].uid
            if boundary_uid > 0:
                data = self._require_data()
                with data.transaction():
                    data.truncate_messages_before_id(self._session_id(), boundary_uid)
                    for turn_id in removed_turn_ids:
                        data.delete_narrative_outcomes_for_turn(
                            self._session_id(),
                            turn_id,
                        )
                        data.delete_plot_decisions_for_turn(
                            self._session_id(),
                            turn_id,
                        )
            else:
                self.replace(remaining, persist=True)
                return before - len(self._state.messages)

        self._state.messages = remaining
        self._rebuild_turn_state()
        removed = before - len(self._state.messages)
        logger.debug(
            _TAG + " truncated: removed {} msgs, {} remaining",
            removed,
            len(self._state.messages),
        )
        return removed

    def get_message(self, message_id: int) -> Message | None:
        """Return one message from this session by its persisted message id."""
        target_id = int(message_id)
        for message in self._state.messages:
            if message.uid == target_id:
                return message

        if not self._history_enabled():
            return None

        row = self._require_data().get_message_for_session(
            self._session_id(),
            target_id,
        )
        if row is None:
            return None
        return Message.from_dict(row.to_message_dict())

    def turn_messages(self, turn_id: int) -> list[Message]:
        """Return loaded messages for one explicit turn id."""
        target_turn = int(turn_id)
        return [
            message
            for message in self._state.messages
            if message.turn_id == target_turn
        ]

    def first_user_message_for_turn(self, turn_id: int) -> Message | None:
        """Return the first user message in a turn, if present."""
        messages = sorted(
            self.turn_messages(turn_id),
            key=lambda item: item.seq_in_turn or 0,
        )
        return next((message for message in messages if message.is_user()), None)

    def truncate_from_turn(self, turn_id: int) -> int:
        """Remove *turn_id* and all following turns from mutable history."""
        boundary_turn = int(turn_id)
        if boundary_turn <= 0:
            raise ValueError("turn_id must be positive")

        before = len(self._state.messages)
        if self._history_enabled():
            data = self._require_data()
            with data.transaction():
                removed = data.truncate_messages_from_turn(
                    self._session_id(),
                    boundary_turn,
                )
                data.delete_narrative_outcomes_from_turn(
                    self._session_id(),
                    boundary_turn,
                )
                data.delete_plot_decisions_from_turn(
                    self._session_id(),
                    boundary_turn,
                )
            self.load()
            return removed

        self._state.messages = [
            message
            for message in self._state.messages
            if message.turn_id < boundary_turn
        ]
        self._progress.intersect_in_memory_processing_keys()
        self._rebuild_turn_state()
        return before - len(self._state.messages)

    def update_message_content(self, message_id: int, content: str) -> Message:
        """Update a persisted message body and reload in-memory history."""
        target_id = int(message_id)
        if not self._history_enabled():
            for index, message in enumerate(self._state.messages):
                if message.uid == target_id:
                    self._progress.discard_in_memory_processing_key(message)
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
                    self._state.messages[index] = updated
                    self._rebuild_turn_state()
                    return updated
            raise FileNotFoundError(f"session message not found: {message_id}")

        data = self._require_data()
        with data.transaction():
            current = data.get_message_for_session(self._session_id(), target_id)
            if current is None:
                raise FileNotFoundError(f"session message not found: {message_id}")
            updated_row = data.update_message_content(target_id, str(content))
            if updated_row is None:
                raise FileNotFoundError(f"session message not found: {message_id}")
            data.reset_message_processing(self._session_id(), (target_id,))
            if current.role == "user":
                data.delete_narrative_outcomes_for_turn(
                    self._session_id(),
                    current.turn_id,
                )
            data.delete_plot_decisions_for_turn(
                self._session_id(),
                current.turn_id,
            )
        self.load()
        return Message.from_dict(updated_row.to_message_dict())

    def delete_message(self, message_id: int) -> Message:
        """Delete one message from mutable history and reload memory."""
        target_id = int(message_id)
        if not self._history_enabled():
            for index, message in enumerate(self._state.messages):
                if message.uid == target_id:
                    deleted = self._state.messages.pop(index)
                    self._progress.discard_in_memory_processing_key(deleted)
                    self._rebuild_turn_state()
                    return deleted
            raise FileNotFoundError(f"session message not found: {message_id}")

        data = self._require_data()
        with data.transaction():
            current = data.get_message_for_session(self._session_id(), target_id)
            if current is None:
                raise FileNotFoundError(f"session message not found: {message_id}")
            if not data.delete_message_for_session(self._session_id(), target_id):
                raise FileNotFoundError(f"session message not found: {message_id}")
            data.delete_narrative_outcomes_for_turn(
                self._session_id(),
                current.turn_id,
            )
            data.delete_plot_decisions_for_turn(
                self._session_id(),
                current.turn_id,
            )
        self.load()
        return Message.from_dict(current.to_message_dict())

    def replace(self, history: list[Message], *, persist: bool | None = None) -> None:
        """Replace in-memory history and optionally rewrite the mutable SQL table."""
        self._state.messages = list(history)
        if persist is None:
            persist = self._history_enabled()

        if persist and self._history_enabled():
            self.validate_loaded_turn_metadata(label="history")
            data = self._require_data()
            with data.transaction():
                current_by_id = {
                    row.id: row for row in data.list_messages(self._session_id())
                }
                payloads = tuple(
                    _message_replace_payload(message, current_by_id)
                    for message in self._state.messages
                )
                rows = data.replace_messages(
                    self._session_id(),
                    payloads,
                )
                data.retain_narrative_outcome_turns(
                    self._session_id(),
                    (message.turn_id for message in self._state.messages),
                )
                data.retain_plot_decision_turns(
                    self._session_id(),
                    (message.turn_id for message in self._state.messages),
                )
            self._state.messages = [
                Message.from_dict(row.to_message_dict())
                for row in rows
            ]

        self._rebuild_turn_state()
        self._progress.intersect_in_memory_processing_keys()

    def _validate_append_turn_metadata(self, message: Message) -> None:
        if message.turn_id <= 0 or message.seq_in_turn <= 0:
            raise InvalidTurnMetadataError(
                "invalid turn metadata for append: turn_id and seq_in_turn must be positive integers"
            )

        latest = latest_turn_id(self._state.messages)
        if message.turn_id < latest:
            raise InvalidTurnMetadataError(
                "invalid turn metadata for append: turn_id must be nondecreasing"
            )

        next_seq = self._state.turn_seq_by_turn.get(message.turn_id)
        if next_seq is not None and message.seq_in_turn < next_seq:
            raise InvalidTurnMetadataError(
                "invalid turn metadata for append: seq_in_turn must increase inside the same turn"
            )

    def _rebuild_turn_state(self) -> None:
        seq_by_turn: dict[int, int] = {}
        for message in self._state.messages:
            if message.turn_id <= 0:
                continue
            seq_by_turn[message.turn_id] = max(
                seq_by_turn.get(message.turn_id, 0),
                message.seq_in_turn,
            )
        self._state.turn_seq_by_turn = {
            turn_id: sequence + 1
            for turn_id, sequence in seq_by_turn.items()
        }
        self._state.active_turn_id = None


def _message_replace_payload(
    message: Message,
    current_by_id: Mapping[int, SessionMessage],
) -> Mapping[str, object]:
    payload = message.to_persistence_dict()
    current = current_by_id.get(message.uid)
    if current is None:
        return payload
    payload.update(
        summary_processed=current.summary_processed,
        summary_batch_id=current.summary_batch_id,
        summary_processed_at=current.summary_processed_at,
        story_memory_processed=current.story_memory_processed,
        story_memory_processed_at=current.story_memory_processed_at,
    )
    return payload


__all__ = ["SessionHistory", "SessionHistoryDataPort"]
