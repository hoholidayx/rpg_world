"""Typed terminal-notification seam for Dream generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DreamTerminalNotification:
    proposal_id: str
    session_id: str
    depth: str
    scope: str
    status: str
    error_code: str
    error_message: str
    finished_at: str
    updated_at: str


class DreamTerminalNotificationSink(Protocol):
    async def publish(self, notification: DreamTerminalNotification) -> None: ...


class NullDreamTerminalNotificationSink:
    async def publish(self, notification: DreamTerminalNotification) -> None:
        del notification
