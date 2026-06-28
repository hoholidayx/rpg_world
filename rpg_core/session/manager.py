"""SessionManager — session lifecycle and rpg_data-backed conversation history."""

from __future__ import annotations

import re

from loguru import logger

from rpg_core.context.rpg_context import Message, Role

_TAG = "[SessionManager]"

_DEFAULT_SESSION_ID = "default"

# Public constant for use by API and other layers.
DEFAULT_SESSION_ID = _DEFAULT_SESSION_ID
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_SESSION_ID_MAX_LENGTH = 64


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
        self._story_memory_last_turn_id = 0

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
        self.__history = [
            Message.from_dict(row.to_message_dict())
            for row in gateway.messages.list(self._session_id)
        ]
        self._story_memory_last_turn_id = gateway.story_memory.get_last_turn_id(self._session_id)
        self._rebuild_turn_state()
        logger.debug(_TAG + " loaded {} message(s) for session '{}'", len(self.__history), self._session_id)

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
        if not messages:
            return False
        if any(msg.turn_id <= 0 or msg.seq_in_turn <= 0 for msg in messages):
            return False

        last_turn_id = 0
        for msg in messages:
            if msg.turn_id < last_turn_id:
                return False
            last_turn_id = msg.turn_id
        return True

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

    def append(
        self,
        role: Role | str,
        content: str,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
    ) -> None:
        """Append a message to in-memory history and, when enabled, rpg_data."""
        role_value = Role(role).value
        if turn_id is None:
            turn_id = self._active_turn_id or self.begin_turn()
        if seq_in_turn is None:
            seq_in_turn = self._turn_seq_by_turn.get(turn_id, 1)
        self._turn_seq_by_turn[turn_id] = seq_in_turn + 1

        text = str(content or "")
        uid = 0
        if self._history_enabled:
            gateway = self._require_data_session()
            with gateway.database.atomic():
                row = gateway.messages.append(
                    self._session_id,
                    role_value,
                    text,
                    turn_id=turn_id,
                    seq_in_turn=seq_in_turn,
                )
                gateway.backup.messages.append(
                    self._session_id,
                    role_value,
                    text,
                    turn_id=turn_id,
                    seq_in_turn=seq_in_turn,
                )
            uid = row.id

        self.__history.append(
            Message(
                role_value,
                text,
                uid=uid,
                turn_id=turn_id,
                seq_in_turn=seq_in_turn,
            )
        )

    def clear(self) -> None:
        """Clear in-memory history and the mutable rpg_data message table."""
        self.replace_history([], persist=self._history_enabled)
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
                self._require_data_session().messages.clear(self._session_id)
            self.__history = []
            self._rebuild_turn_state()
            return before

        remaining = self.__history[keep_from_index:]
        if self._history_enabled:
            boundary_uid = self.__history[keep_from_index].uid
            if boundary_uid > 0:
                self._require_data_session().messages.truncate_before_id(self._session_id, boundary_uid)
            else:
                self.replace_history(remaining, persist=True)
                return before - len(self.__history)

        self.__history = remaining
        self._rebuild_turn_state()
        removed = before - len(self.__history)
        logger.debug(_TAG + " truncated: removed {} msgs, {} remaining", removed, len(self.__history))
        return removed

    # ── Session switch ─────────────────────────────────────────────────

    def switch_to(self, session_id: str) -> None:
        """Switch to a different rpg_data session and reload history."""
        self.validate_session_id(session_id)
        self._session_id = session_id
        self.replace_history([], persist=False)
        self._story_memory_last_turn_id = 0
        if self._history_enabled:
            self.load()
        logger.debug(_TAG + " switched to session '{}'", session_id)

    # ── Metadata ───────────────────────────────────────────────────────

    @property
    def meta(self) -> dict[str, object]:
        if not self._history_enabled:
            return {"story_memory_last_turn_id": self._story_memory_last_turn_id}

        gateway = self._require_data_session()
        session = gateway.catalog.get_session(self._session_id)
        if session is None:
            return {}
        return {
            **session,
            "story_memory_last_turn_id": gateway.story_memory.get_last_turn_id(self._session_id),
        }

    # ── Story memory progress tracking ──────────────────────────────────

    @property
    def story_memory_last_turn_id(self) -> int:
        """Last processed conversation ``turn_id`` for story memory extraction."""
        if not self._history_enabled:
            return self._story_memory_last_turn_id
        self._story_memory_last_turn_id = self._require_data_session().story_memory.get_last_turn_id(self._session_id)
        return self._story_memory_last_turn_id

    def set_story_memory_last_turn_id(self, turn_id: int) -> None:
        """Persist the last processed story-memory ``turn_id``."""
        normalized = max(0, int(turn_id))
        if self._history_enabled:
            self._require_data_session().story_memory.set_last_turn_id(self._session_id, normalized)
        self._story_memory_last_turn_id = normalized

    def story_turn_groups_since_last_extraction(self) -> list[list[Message]]:
        """Return logical turn groups with ``turn_id`` greater than the story cursor."""
        cursor = self.story_memory_last_turn_id
        return [
            group
            for group in self.iter_turn_groups(self.__history)
            if self.latest_turn_id(group) > cursor
        ]

    def story_messages_since_last_extraction(self) -> list[Message]:
        """Return messages with turn ids not yet processed for story memory."""
        groups = self.story_turn_groups_since_last_extraction()
        return [msg for group in groups for msg in group]

    def mark_story_messages_processed(self, messages: list[Message]) -> None:
        """Advance the story-memory cursor to the newest processed ``turn_id``."""
        turn_id = self.latest_turn_id(messages)
        if turn_id > self.story_memory_last_turn_id:
            self.set_story_memory_last_turn_id(turn_id)

    def count_new_turns_since_story(self) -> int:
        """Count new explicit conversation turn ids since the last story extraction."""
        cursor = self.story_memory_last_turn_id
        return len({msg.turn_id for msg in self.__history if msg.turn_id > cursor})

    # ── History-enabled flag ───────────────────────────────────────────

    @property
    def history_enabled(self) -> bool:
        return self._history_enabled

    def set_history_enabled(self, enabled: bool) -> None:
        self._history_enabled = enabled

    def replace_history(self, history: list[Message], *, persist: bool | None = None) -> None:
        """Replace in-memory history and optionally rewrite the mutable SQL table."""
        self.__history = list(history)
        if persist is None:
            persist = self._history_enabled

        if persist and self._history_enabled:
            rows = self._require_data_session().messages.replace(
                self._session_id,
                (msg.to_dict() for msg in self.__history),
            )
            self.__history = [Message.from_dict(row.to_message_dict()) for row in rows]

        self._rebuild_turn_state()

    def _rebuild_turn_state(self) -> None:
        """Reconstruct turn sequence counters from the current in-memory history."""
        seq_by_turn: dict[int, int] = {}
        for msg in self.__history:
            if msg.turn_id <= 0:
                continue
            seq_by_turn[msg.turn_id] = max(seq_by_turn.get(msg.turn_id, 0), msg.seq_in_turn)
        self._turn_seq_by_turn = {turn_id: seq + 1 for turn_id, seq in seq_by_turn.items()}
        self._active_turn_id = None

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
