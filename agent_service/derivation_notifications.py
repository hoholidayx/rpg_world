"""Typed completion notification seam for session derivation jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SessionDerivationNotification:
    """Stable payload that a future user-notification adapter can consume."""

    job_id: str
    source_session_id: str
    target_session_id: str | None
    branch_turn_id: int
    status: str
    error_code: str = ""
    error_message: str = ""
    context_threshold_exceeded: bool = False


class SessionDerivationNotificationSink(Protocol):
    """Boundary for future WebUI/global notification delivery."""

    async def publish(self, notification: SessionDerivationNotification) -> None: ...


class NullSessionDerivationNotificationSink:
    """Default backend-only implementation used until a UI channel exists."""

    async def publish(self, notification: SessionDerivationNotification) -> None:
        del notification
