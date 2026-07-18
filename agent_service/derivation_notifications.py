"""Typed completion notification seam for session derivation jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SessionDerivationNotification:
    """Stable payload consumed by an injected terminal-notification adapter."""

    job_id: str
    source_session_id: str
    target_session_id: str | None
    branch_turn_id: int
    status: str
    error_code: str = ""
    error_message: str = ""
    context_threshold_exceeded: bool = False
    finished_at: str = ""
    updated_at: str = ""


class SessionDerivationNotificationSink(Protocol):
    """Transport-neutral boundary for terminal notification delivery."""

    async def publish(self, notification: SessionDerivationNotification) -> None: ...


class NullSessionDerivationNotificationSink:
    """No-op implementation used when delivery is disabled or under test."""

    async def publish(self, notification: SessionDerivationNotification) -> None:
        del notification
