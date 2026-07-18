"""Public façade for session lifecycle and conversation history."""

from __future__ import annotations

import re

from loguru import logger

from rpg_core.context.models import Message, Role
from rpg_core.session.grouping import (
    count_turns as count_grouped_turns,
    has_explicit_turn_ids as contains_explicit_turn_ids,
    has_trustworthy_turn_ids as contains_trustworthy_turn_ids,
    iter_turn_groups as group_messages_by_turn,
    latest_turn_id as find_latest_turn_id,
    slice_recent_turns as select_recent_turns,
    split_into_turn_batches as build_turn_batches,
)
from rpg_core.session.history import SessionHistory
from rpg_core.session.models import ContextHistorySnapshot, SessionRuntimeState
from rpg_core.session.progress import SessionProgress
from rpg_core.session.turn_metadata import (
    InvalidTurnMetadataError,
    validate_turn_metadata as validate_message_turn_metadata,
)

_TAG = "[SessionManager]"

_DEFAULT_SESSION_ID = "default"

# Public constant for use by API and other layers.
DEFAULT_SESSION_ID = _DEFAULT_SESSION_ID
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_SESSION_ID_MAX_LENGTH = 64


class SessionManager:
    """Stable session façade over history, grouping, and progress services."""

    @staticmethod
    def is_valid_session_id(session_id: str) -> bool:
        """Return whether *session_id* matches the repository naming rule."""
        return len(session_id) <= _SESSION_ID_MAX_LENGTH and bool(
            _SESSION_ID_PATTERN.fullmatch(session_id)
        )

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        """Validate *session_id* and return it unchanged on success."""
        if len(session_id) > _SESSION_ID_MAX_LENGTH:
            raise ValueError(
                f"session_id must be at most {_SESSION_ID_MAX_LENGTH} characters long"
            )
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
        state = SessionRuntimeState()
        self._progress = SessionProgress(
            state,
            session_id=lambda: self._session_id,
            history_enabled=lambda: self._history_enabled,
            require_gateway=lambda: self._require_data_session(),
        )
        self._history_service = SessionHistory(
            state,
            self._progress,
            session_id=lambda: self._session_id,
            history_enabled=lambda: self._history_enabled,
            require_gateway=lambda: self._require_data_session(),
        )

    # ── Public API — history ───────────────────────────────────────────

    @property
    def history(self) -> list[Message]:
        """Read-only snapshot of in-memory history."""
        return self._history_service.messages

    @property
    def _history(self) -> list[Message]:
        """Compatibility snapshot for legacy internal access."""
        return self._history_service.messages

    def load(self) -> None:
        self._history_service.load()

    def context_history(self) -> ContextHistorySnapshot:
        """Return the history visible to the main Agent context."""
        return self._history_service.context_history()

    def begin_turn(self) -> int:
        return self._history_service.begin_turn()

    def end_turn(self, turn_id: int | None = None) -> None:
        self._history_service.end_turn(turn_id)

    # ── Turn helpers ───────────────────────────────────────────────────

    @staticmethod
    def has_explicit_turn_ids(messages: list[Message]) -> bool:
        return contains_explicit_turn_ids(messages)

    @staticmethod
    def has_trustworthy_turn_ids(messages: list[Message]) -> bool:
        return contains_trustworthy_turn_ids(messages)

    @staticmethod
    def validate_turn_metadata(
        messages: list[Message],
        *,
        label: str = "history",
    ) -> None:
        validate_message_turn_metadata(messages, label=label)

    def validate_loaded_turn_metadata(self, *, label: str = "history") -> None:
        self._history_service.validate_loaded_turn_metadata(label=label)

    @classmethod
    def iter_turn_groups(cls, messages: list[Message]) -> list[list[Message]]:
        return group_messages_by_turn(messages)

    @classmethod
    def count_turns(cls, messages: list[Message]) -> int:
        return count_grouped_turns(messages)

    @classmethod
    def slice_recent_turns(
        cls,
        messages: list[Message],
        keep_turns: int,
    ) -> list[Message]:
        return select_recent_turns(messages, keep_turns)

    @classmethod
    def split_into_turn_batches(
        cls,
        messages: list[Message],
        batch_turn_size: int,
    ) -> list[tuple[int, list[Message], int]]:
        return build_turn_batches(messages, batch_turn_size)

    @staticmethod
    def latest_turn_id(messages: list[Message]) -> int:
        return find_latest_turn_id(messages)

    # ── History mutations ──────────────────────────────────────────────

    def append(
        self,
        role: Role | str,
        content: str,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        *,
        mode: str = "ic",
    ) -> None:
        self._history_service.append(
            role,
            content,
            turn_id,
            seq_in_turn,
            mode=mode,
        )

    def clear(self) -> None:
        self._history_service.clear()

    def truncate(self, keep_from_index: int) -> int:
        return self._history_service.truncate(keep_from_index)

    def get_message(self, message_id: int) -> Message | None:
        return self._history_service.get_message(message_id)

    def turn_messages(self, turn_id: int) -> list[Message]:
        return self._history_service.turn_messages(turn_id)

    def first_user_message_for_turn(self, turn_id: int) -> Message | None:
        return self._history_service.first_user_message_for_turn(turn_id)

    def truncate_from_turn(self, turn_id: int) -> int:
        return self._history_service.truncate_from_turn(turn_id)

    def update_message_content(self, message_id: int, content: str) -> Message:
        return self._history_service.update_message_content(message_id, content)

    def delete_message(self, message_id: int) -> Message:
        return self._history_service.delete_message(message_id)

    @property
    def meta(self) -> dict[str, object]:
        if not self._history_enabled:
            return {}

        session = self._require_data_session().catalog.get_session(self._session_id)
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

    def summary_turn_groups_for_compression(
        self,
        keep_recent_turns: int,
    ) -> list[list[Message]]:
        return self._progress.summary_turn_groups_for_compression(keep_recent_turns)

    def summary_unprocessed_turn_groups(self) -> list[list[Message]]:
        return self._progress.summary_unprocessed_turn_groups()

    def count_summary_turns_for_compression(self, keep_recent_turns: int) -> int:
        return len(self.summary_turn_groups_for_compression(keep_recent_turns))

    def mark_summary_messages_processed(
        self,
        messages: list[Message],
        *,
        batch_id: int | None,
    ) -> None:
        self._progress.mark_summary_messages_processed(messages, batch_id=batch_id)

    def mark_summary_batches_processed(
        self,
        batches: list[tuple[list[Message], int]],
    ) -> None:
        self._progress.mark_summary_batches_processed(batches)

    def story_turn_groups_since_last_extraction(self) -> list[list[Message]]:
        return self._progress.story_turn_groups_since_last_extraction()

    def story_messages_since_last_extraction(self) -> list[Message]:
        return self._progress.story_messages_since_last_extraction()

    def mark_story_messages_processed(self, messages: list[Message]) -> None:
        self._progress.mark_story_messages_processed(messages)

    def count_new_turns_since_story(self) -> int:
        return self._progress.count_new_turns_since_story()

    # ── Configuration and replacement ─────────────────────────────────

    @property
    def history_enabled(self) -> bool:
        return self._history_enabled

    @property
    def session_id(self) -> str:
        return self._session_id

    def set_history_enabled(self, enabled: bool) -> None:
        self._history_enabled = enabled

    def replace_history(
        self,
        history: list[Message],
        *,
        persist: bool | None = None,
    ) -> None:
        self._history_service.replace(history, persist=persist)

    def _require_data_session(self):
        from rpg_data.services import get_data_service_gateway

        gateway = get_data_service_gateway()
        if gateway.catalog.get_session(self._session_id) is None:
            raise FileNotFoundError(
                f"Session not found in rpg_data: {self._session_id}"
            )
        return gateway
