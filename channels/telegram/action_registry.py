"""In-memory callback action registry for Telegram inline keyboards."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType

from loguru import logger

_CALLBACK_PREFIX = "tg:a:"
_LEGACY_CALLBACK_PREFIX = "tg_sess:"
_DEFAULT_TTL_SECONDS = 600.0
_TOKEN_PREVIEW_LENGTH = 6

ActionValue = str | int | bool | None


class CallbackConsumePolicy(StrEnum):
    """Controls whether claiming an action consumes its token."""

    ON_CLAIM = "on_claim"
    REUSABLE = "reusable"


class CallbackResolutionStatus(StrEnum):
    """Internal result of resolving callback data."""

    RESOLVED = "resolved"
    INVALID = "invalid"
    LEGACY = "legacy"
    EXPIRED = "expired"
    CHAT_MISMATCH = "chat_mismatch"
    SESSION_MISMATCH = "session_mismatch"


@dataclass(frozen=True)
class TelegramCallbackAction:
    """Server-owned state represented by a short Telegram callback token."""

    token: str
    kind: str
    chat_id: str
    session_id: str | None
    payload: Mapping[str, ActionValue] = field(default_factory=dict)
    created_at: float = 0.0
    expires_at: float = 0.0
    consume_policy: CallbackConsumePolicy = CallbackConsumePolicy.ON_CLAIM


@dataclass(frozen=True)
class TelegramCallbackResolution:
    """A validated action lookup without consuming the action."""

    status: CallbackResolutionStatus
    token: str = ""
    action: TelegramCallbackAction | None = None

    @property
    def resolved(self) -> bool:
        return self.status == CallbackResolutionStatus.RESOLVED and self.action is not None


class TelegramActionRegistry:
    """Process-local callback registry with ownership and expiry checks."""

    callback_prefix = _CALLBACK_PREFIX
    legacy_callback_prefix = _LEGACY_CALLBACK_PREFIX

    def __init__(
        self,
        *,
        default_ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._default_ttl_seconds = float(default_ttl_seconds)
        self._clock = clock
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(9))
        self._actions: dict[str, TelegramCallbackAction] = {}

    def create(
        self,
        *,
        kind: str,
        chat_id: str,
        session_id: str | None,
        payload: Mapping[str, ActionValue] | None = None,
        consume_policy: CallbackConsumePolicy = CallbackConsumePolicy.ON_CLAIM,
        ttl_seconds: float | None = None,
    ) -> TelegramCallbackAction:
        """Create an action ready for registration."""
        now = self._clock()
        ttl = self._default_ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        token = self._new_token()
        return TelegramCallbackAction(
            token=token,
            kind=str(kind),
            chat_id=str(chat_id),
            session_id=str(session_id) if session_id is not None else None,
            payload=MappingProxyType(dict(payload or {})),
            created_at=now,
            expires_at=now + ttl,
            consume_policy=consume_policy,
        )

    def register(self, action: TelegramCallbackAction) -> str:
        """Register an action and return its compact callback data."""
        now = self._clock()
        self._cleanup_expired(now)
        if not action.token:
            raise ValueError("callback action token must not be empty")
        if action.token in self._actions:
            raise ValueError("callback action token already registered")
        stored = replace(action, payload=MappingProxyType(dict(action.payload)))
        callback_data = f"{_CALLBACK_PREFIX}{stored.token}"
        if len(callback_data.encode("utf-8")) > 64:
            raise ValueError("callback data exceeds Telegram 64-byte limit")
        self._actions[stored.token] = stored
        return callback_data

    def add(
        self,
        *,
        kind: str,
        chat_id: str,
        session_id: str | None,
        payload: Mapping[str, ActionValue] | None = None,
        consume_policy: CallbackConsumePolicy = CallbackConsumePolicy.ON_CLAIM,
        ttl_seconds: float | None = None,
    ) -> str:
        """Create and register an action in one call."""
        return self.register(
            self.create(
                kind=kind,
                chat_id=chat_id,
                session_id=session_id,
                payload=payload,
                consume_policy=consume_policy,
                ttl_seconds=ttl_seconds,
            )
        )

    def resolve(
        self,
        callback_data: str,
        *,
        chat_id: str,
        current_session_id: str | None,
    ) -> TelegramCallbackResolution:
        """Validate callback ownership and expiry without consuming it."""
        raw = str(callback_data or "")
        if raw.startswith(_LEGACY_CALLBACK_PREFIX):
            return TelegramCallbackResolution(CallbackResolutionStatus.LEGACY)
        if not raw.startswith(_CALLBACK_PREFIX):
            return TelegramCallbackResolution(CallbackResolutionStatus.INVALID)

        token = raw.removeprefix(_CALLBACK_PREFIX)
        now = self._clock()
        action = self._actions.get(token)
        if action is not None and now >= action.expires_at:
            self._actions.pop(token, None)
            self._cleanup_expired(now)
            self._log_rejection(CallbackResolutionStatus.EXPIRED, token)
            return TelegramCallbackResolution(CallbackResolutionStatus.EXPIRED, token=token)

        self._cleanup_expired(now)
        action = self._actions.get(token)
        if action is None:
            self._log_rejection(CallbackResolutionStatus.INVALID, token)
            return TelegramCallbackResolution(CallbackResolutionStatus.INVALID, token=token)
        if action.chat_id != str(chat_id):
            self._log_rejection(CallbackResolutionStatus.CHAT_MISMATCH, token)
            return TelegramCallbackResolution(CallbackResolutionStatus.CHAT_MISMATCH, token=token)
        if action.session_id is not None and action.session_id != current_session_id:
            self._log_rejection(CallbackResolutionStatus.SESSION_MISMATCH, token)
            return TelegramCallbackResolution(CallbackResolutionStatus.SESSION_MISMATCH, token=token)
        return TelegramCallbackResolution(
            CallbackResolutionStatus.RESOLVED,
            token=token,
            action=action,
        )

    def claim(self, token: str) -> TelegramCallbackAction | None:
        """Atomically claim a resolved token according to its consume policy."""
        action = self._actions.get(token)
        if action is None:
            return None
        if self._clock() >= action.expires_at:
            self._actions.pop(token, None)
            return None
        if action.consume_policy == CallbackConsumePolicy.ON_CLAIM:
            return self._actions.pop(token, None)
        return action

    def invalidate(self, token: str) -> bool:
        return self._actions.pop(str(token), None) is not None

    def invalidate_chat(self, chat_id: str) -> int:
        return self._invalidate_matching(lambda action: action.chat_id == str(chat_id))

    def invalidate_session(self, session_id: str) -> int:
        return self._invalidate_matching(lambda action: action.session_id == str(session_id))

    def clear(self) -> None:
        self._actions.clear()

    def __len__(self) -> int:
        return len(self._actions)

    def _new_token(self) -> str:
        for _ in range(100):
            token = str(self._token_factory())
            if token and token not in self._actions:
                return token
        raise RuntimeError("failed to allocate unique callback token")

    def _cleanup_expired(self, now: float) -> None:
        expired = [token for token, action in self._actions.items() if now >= action.expires_at]
        for token in expired:
            self._actions.pop(token, None)

    def _invalidate_matching(self, predicate: Callable[[TelegramCallbackAction], bool]) -> int:
        tokens = [token for token, action in self._actions.items() if predicate(action)]
        for token in tokens:
            self._actions.pop(token, None)
        return len(tokens)

    @staticmethod
    def _log_rejection(status: CallbackResolutionStatus, token: str) -> None:
        logger.debug(
            "telegram callback rejected: status={} token_prefix={}",
            status.value,
            token[:_TOKEN_PREVIEW_LENGTH],
        )


__all__ = [
    "ActionValue",
    "CallbackConsumePolicy",
    "CallbackResolutionStatus",
    "TelegramActionRegistry",
    "TelegramCallbackAction",
    "TelegramCallbackResolution",
]
