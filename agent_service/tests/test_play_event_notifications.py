from __future__ import annotations

import pytest

from agent_service.derivation_notifications import SessionDerivationNotification
from agent_service.play_event_notifications import SessionDerivationPlayEventSink
from play_events import PlayEventType, SessionDerivationTerminalPayload, TerminalStatus


class _Publisher:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event) -> None:  # noqa: ANN001
        self.events.append(event)


@pytest.mark.asyncio
async def test_derivation_sink_maps_terminal_notification() -> None:
    publisher = _Publisher()
    sink = SessionDerivationPlayEventSink(publisher)  # type: ignore[arg-type]

    await sink.publish(
        SessionDerivationNotification(
            job_id="job-1",
            source_session_id="source-1",
            target_session_id="target-1",
            branch_turn_id=7,
            status="ready",
            context_threshold_exceeded=True,
            finished_at="2026-07-18T08:00:00Z",
            updated_at="2026-07-18T08:00:01Z",
        )
    )

    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert event.event_type is PlayEventType.SESSION_DERIVATION_TERMINAL
    assert event.session_id == "source-1"
    assert isinstance(event.payload, SessionDerivationTerminalPayload)
    assert event.payload.status is TerminalStatus.READY
    assert event.payload.target_session_id == "target-1"
    assert event.payload.turn_id == 7
    assert event.payload.context_threshold_exceeded is True
