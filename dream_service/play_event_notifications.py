"""Play-event adapter for Dream terminal notifications."""

from __future__ import annotations

from dream_service.notifications import DreamTerminalNotification
from play_events import (
    DreamProposalTerminalPayload,
    PlayEvent,
    PlayEventPublisher,
    PlayEventType,
    TerminalStatus,
)


class DreamPlayEventSink:
    def __init__(self, publisher: PlayEventPublisher) -> None:
        self._publisher = publisher

    async def publish(self, notification: DreamTerminalNotification) -> None:
        await self._publisher.publish(
            PlayEvent.create(
                event_type=PlayEventType.DREAM_PROPOSAL_TERMINAL,
                session_id=notification.session_id,
                payload=DreamProposalTerminalPayload(
                    proposal_id=notification.proposal_id,
                    depth=notification.depth,
                    scope=notification.scope,
                    status=TerminalStatus(notification.status),
                    error_code=notification.error_code,
                    error_message=notification.error_message,
                    finished_at=notification.finished_at,
                    updated_at=notification.updated_at,
                ),
            )
        )
