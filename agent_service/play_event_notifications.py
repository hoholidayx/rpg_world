"""Play-event adapter for session derivation domain notifications."""

from __future__ import annotations

from agent_service.derivation_notifications import SessionDerivationNotification
from play_events import (
    PlayEvent,
    PlayEventPublisher,
    PlayEventType,
    SessionDerivationTerminalPayload,
    TerminalStatus,
)


class SessionDerivationPlayEventSink:
    """Map Derivation notifications onto the shared Play wire contract."""

    def __init__(self, publisher: PlayEventPublisher) -> None:
        self._publisher = publisher

    async def publish(self, notification: SessionDerivationNotification) -> None:
        status = TerminalStatus(notification.status)
        await self._publisher.publish(
            PlayEvent.create(
                event_type=PlayEventType.SESSION_DERIVATION_TERMINAL,
                session_id=notification.source_session_id,
                payload=SessionDerivationTerminalPayload(
                    job_id=notification.job_id,
                    source_session_id=notification.source_session_id,
                    target_session_id=notification.target_session_id,
                    turn_id=notification.branch_turn_id,
                    status=status,
                    error_code=notification.error_code,
                    error_message=notification.error_message,
                    context_threshold_exceeded=(
                        notification.context_threshold_exceeded
                    ),
                    finished_at=notification.finished_at,
                    updated_at=notification.updated_at,
                ),
            )
        )
