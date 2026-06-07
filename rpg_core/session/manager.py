"""SessionManager — owns conversation history and session metadata for one session.

Responsibilities:
  - In-memory ``_history`` list
  - Persistence to ``history.jsonl`` and ``history_cold.jsonl``
  - ``session.json`` metadata file read/write (lazy-created)
  - Single-turn checkpoint/rollback
  - History truncation (for compact)

The ``_history_enabled`` flag (from agent) controls all disk I/O.
In-memory ``_history`` is always updated regardless of the flag.
"""

from __future__ import annotations

import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from rpg_world.rpg_core.settings import settings
from rpg_world.rpg_core.context.rpg_context import Message, Role

_TAG = "[SessionManager]"

# Module-level constants — avoid magic strings scattered throughout
_DEFAULT_SESSION_ID = "default"
_META_TMP_SUFFIX = ".json.tmp"
_META_CREATED_AT = "created_at"
_META_UPDATED_AT = "updated_at"
_META_MESSAGE_COUNT = "message_count"
_META_COMPACTED_ROUNDS = "compacted_rounds"
_META_LAST_STORY_RP_HIS_ID = "last_story_rp_his_id"


class SessionManager:
    """Owns conversation history and session metadata for one session."""

    def __init__(
        self,
        session_id: str = None,  # type: ignore[assignment]
        history_enabled: bool = True,
    ) -> None:
        self._session_id = session_id if session_id is not None else _DEFAULT_SESSION_ID
        self._history_enabled = history_enabled
        self._history: list[Message] = []
        self._meta: dict[str, Any] = {}

    # ── Public API — history ───────────────────────────────────────────

    @property
    def history(self) -> list[Message]:
        """Read-only snapshot of in-memory history."""
        return list(self._history)

    @property
    def message_count(self) -> int:
        return len(self._history)

    def load(self) -> None:
        """Load history from ``history.jsonl`` into ``_history``.

        Called once during agent initialization.  Also loads (or creates)
        the ``session.json`` metadata.
        """
        self._load_meta()
        path = self._history_path()
        if not path.exists():
            logger.debug(_TAG + " no history file for session '{}'", self._session_id)
            return
        self._history = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._history.append(Message.from_dict(json.loads(line)))
                except (json.JSONDecodeError, Exception):
                    continue
        logger.debug(
            _TAG + " loaded {} message(s) from {}",
            len(self._history), path,
        )

    def append(self, role: Role | str, content: str) -> None:
        """Append a message to in-memory history.

        Each message gets an ``rp_his_id`` field — current Unix timestamp
        (seconds) used as a unique index for tracking.

        Writes to ``history.jsonl`` and ``history_cold.jsonl`` only when
        ``_history_enabled`` is ``True``.
        """
        his_id = int(_time.time())
        msg = Message(role, content, his_id)
        self._history.append(msg)
        if not self._history_enabled:
            return
        record = json.dumps(msg.to_dict(), ensure_ascii=False)
        # Primary
        path = self._history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(record + "\n")
        # Cold backup (append-only, never truncated)
        cold_path = self._cold_history_path()
        cold_path.parent.mkdir(parents=True, exist_ok=True)
        with cold_path.open("a", encoding="utf-8") as f:
            f.write(record + "\n")
        # Update metadata
        self._update_meta(message_count=len(self._history))

    def clear(self) -> None:
        """Clear in-memory history and truncate ``history.jsonl``."""
        self._history = []
        if self._history_enabled:
            path = self._history_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        self._update_meta(message_count=0)
        logger.debug(_TAG + " cleared history for session '{}'", self._session_id)

    def truncate(self, keep_from_index: int) -> int:
        """Remove all messages before *keep_from_index* from memory and disk.

        Returns the number of messages removed.  Does **not** generate a
        summary — that is the caller's (agent's) responsibility.
        """
        before = len(self._history)
        del self._history[:keep_from_index]
        removed = before - len(self._history)

        if self._history_enabled:
            path = self._history_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                for msg in self._history:
                    f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")

        logger.debug(
            _TAG + " truncated: removed {} msgs, {} remaining",
            removed, len(self._history),
        )
        self._update_meta(message_count=len(self._history))
        return removed

    # ── Checkpoint / rollback (for single_turn) ────────────────────────

    def checkpoint(self) -> int:
        """Return current history length as a rollback checkpoint."""
        return len(self._history)

    def rollback(self, checkpoint: int) -> None:
        """Remove all messages appended since *checkpoint*.

        Note: this does NOT revert the JSONL files on disk.  The
        ``single_turn()`` pattern with ``record_history=False`` does not
        write to disk, so the in-memory rollback is sufficient.
        """
        del self._history[checkpoint:]

    # ── Session switch ─────────────────────────────────────────────────

    def switch_to(self, session_id: str) -> None:
        """Switch to a different session: reload path, metadata, and history."""
        self._session_id = session_id
        self._meta = {}
        self._history = []
        self._load_meta()
        if self._history_enabled:
            self.load()
        logger.debug(_TAG + " switched to session '{}'", session_id)

    # ── Metadata ───────────────────────────────────────────────────────

    @property
    def meta(self) -> dict[str, Any]:
        return dict(self._meta)

    @property
    def compacted_rounds(self) -> int:
        return self._meta.get(_META_COMPACTED_ROUNDS, 0)

    def increment_compacted_rounds(self, count: int = 1) -> None:
        """Bump the compacted_rounds counter and persist metadata."""
        current = self._meta.get(_META_COMPACTED_ROUNDS, 0) + count
        self._update_meta(**{_META_COMPACTED_ROUNDS: current})

    # ── Story memory progress tracking ──────────────────────────────────

    @property
    def last_story_rp_his_id(self) -> int:
        """rp_his_id of the last user message processed by story extraction."""
        return self._meta.get(_META_LAST_STORY_RP_HIS_ID, 0)

    def set_last_story_rp_his_id(self, idx: int) -> None:
        """Persist the last extracted message rp_his_id."""
        self._update_meta(**{_META_LAST_STORY_RP_HIS_ID: idx})

    def count_new_user_rounds_since_story(self) -> int:
        """Count user messages with rp_his_id > last_story_rp_his_id."""
        last = self.last_story_rp_his_id
        return sum(
            1 for m in self._history
            if m.is_user() and m.rp_his_id > last
        )

    # ── History-enabled flag ───────────────────────────────────────────

    @property
    def history_enabled(self) -> bool:
        return self._history_enabled

    def set_history_enabled(self, enabled: bool) -> None:
        self._history_enabled = enabled

    # ── Internals — paths ──────────────────────────────────────────────

    def _history_path(self) -> Path:
        return settings.get_history_path(self._session_id)

    def _cold_history_path(self) -> Path:
        return settings.get_cold_history_path(self._session_id)

    def _meta_path(self) -> Path:
        return settings.get_session_meta_path(self._session_id)

    # ── Internals — metadata persistence ───────────────────────────────

    def _load_meta(self) -> None:
        """Load ``session.json`` into ``_meta``.  If missing, create with defaults."""
        path = self._meta_path()
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    self._meta = json.load(f)
                return
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    _TAG + " failed to load session.json: {}, recreating", exc,
                )
        self._meta = self._default_meta()
        self._write_meta()

    def _default_meta(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            _META_CREATED_AT: now,
            _META_UPDATED_AT: now,
            _META_MESSAGE_COUNT: 0,
            _META_COMPACTED_ROUNDS: 0,
            _META_LAST_STORY_RP_HIS_ID: 0,
        }

    def _update_meta(self, **kwargs: Any) -> None:
        """Update metadata fields and persist to disk atomically."""
        self._meta.update(kwargs)
        self._meta[_META_UPDATED_AT] = datetime.now(timezone.utc).isoformat()
        self._write_meta()

    def _write_meta(self) -> None:
        """Write ``_meta`` to ``session.json`` atomically (tmp + rename)."""
        if not self._history_enabled:
            return
        path = self._meta_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(_META_TMP_SUFFIX)
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp.replace(path)
        logger.debug(
            _TAG + " wrote session.json: msg_count={}, compacted={}",
            self._meta.get(_META_MESSAGE_COUNT, 0),
            self._meta.get(_META_COMPACTED_ROUNDS, 0),
        )
