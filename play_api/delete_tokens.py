"""Short-lived deletion confirmation tokens for Play API destructive actions."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

DELETE_CONFIRMATION_HEADER = "X-Delete-Confirm-Token"
DELETE_CONFIRMATION_TTL_SECONDS = 300


@dataclass(frozen=True)
class DeleteConfirmationToken:
    token: str
    expires_in_seconds: int


@dataclass(frozen=True)
class _TokenRecord:
    purpose: str
    expires_at: float


_TOKENS: dict[str, _TokenRecord] = {}


def issue_delete_confirmation_token(purpose: str) -> DeleteConfirmationToken:
    """Create a one-time token bound to a destructive action purpose."""

    _cleanup_expired()
    token = secrets.token_urlsafe(24)
    _TOKENS[token] = _TokenRecord(
        purpose=purpose,
        expires_at=time.monotonic() + DELETE_CONFIRMATION_TTL_SECONDS,
    )
    return DeleteConfirmationToken(
        token=token,
        expires_in_seconds=DELETE_CONFIRMATION_TTL_SECONDS,
    )


def consume_delete_confirmation_token(token: str | None, purpose: str) -> bool:
    """Return whether *token* is valid for *purpose* and consume it on success."""

    _cleanup_expired()
    value = str(token or "").strip()
    if not value:
        return False
    record = _TOKENS.get(value)
    if record is None:
        return False
    if record.purpose != purpose or record.expires_at < time.monotonic():
        _TOKENS.pop(value, None)
        return False
    _TOKENS.pop(value, None)
    return True


def reset_delete_confirmation_tokens() -> None:
    """Clear in-memory tokens, primarily for tests."""

    _TOKENS.clear()


def _cleanup_expired() -> None:
    now = time.monotonic()
    expired = [token for token, record in _TOKENS.items() if record.expires_at < now]
    for token in expired:
        _TOKENS.pop(token, None)
