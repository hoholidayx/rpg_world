from __future__ import annotations

import pytest

from dream_service.notifications import DreamTerminalNotification
from dream_service.play_event_notifications import DreamPlayEventSink
from play_events import DreamProposalTerminalPayload, PlayEventType, TerminalStatus


class _Publisher:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event) -> None:  # noqa: ANN001
        self.events.append(event)


@pytest.mark.asyncio
async def test_dream_sink_maps_terminal_notification() -> None:
    publisher = _Publisher()
    sink = DreamPlayEventSink(publisher)  # type: ignore[arg-type]

    await sink.publish(
        DreamTerminalNotification(
            proposal_id="proposal-1",
            session_id="s_forest001",
            depth="deep",
            scope="full",
            status="interrupted",
            error_code="DREAM_GENERATION_INTERRUPTED",
            error_message="",
            finished_at="2026-07-18T08:00:00Z",
            updated_at="2026-07-18T08:00:01Z",
        )
    )

    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert event.event_type is PlayEventType.DREAM_PROPOSAL_TERMINAL
    assert event.session_id == "s_forest001"
    assert isinstance(event.payload, DreamProposalTerminalPayload)
    assert event.payload.status is TerminalStatus.INTERRUPTED
    assert event.payload.proposal_id == "proposal-1"
