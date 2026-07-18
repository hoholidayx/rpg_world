from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from play_api.event_hub import PlayEventHub, PlayEventRuntime
from play_api.routers import events as events_router
from play_events import (
    DreamProposalTerminalPayload,
    PlayEvent,
    PlayEventPublisher,
    PlayEventType,
    SessionDerivationTerminalPayload,
    TerminalStatus,
)


def _dream_event(*, proposal_id: str = "proposal-1") -> PlayEvent:
    return PlayEvent.create(
        event_type=PlayEventType.DREAM_PROPOSAL_TERMINAL,
        session_id="s_forest001",
        payload=DreamProposalTerminalPayload(
            proposal_id=proposal_id,
            depth="deep",
            scope="full",
            status=TerminalStatus.READY,
            error_code="",
            error_message="",
            finished_at="2026-07-18 08:00:00",
            updated_at="2026-07-18 08:00:00",
        ),
    )


def _derivation_event() -> PlayEvent:
    return PlayEvent.create(
        event_type=PlayEventType.SESSION_DERIVATION_TERMINAL,
        session_id="s_forest001",
        payload=SessionDerivationTerminalPayload(
            job_id="job-1",
            source_session_id="s_forest001",
            target_session_id="s_branch001",
            turn_id=4,
            status=TerminalStatus.FAILED,
            error_code="DERIVATION_FAILED",
            error_message="failed",
            context_threshold_exceeded=False,
            finished_at="2026-07-18T08:00:00Z",
            updated_at="2026-07-18T08:00:00Z",
        ),
    )


@pytest.mark.asyncio
async def test_hub_broadcasts_and_drops_oldest_for_slow_subscriber() -> None:
    hub = PlayEventHub(subscriber_queue_capacity=1)
    first_queue = await hub.subscribe()
    second_queue = await hub.subscribe()
    first = _dream_event(proposal_id="proposal-1")
    second = _dream_event(proposal_id="proposal-2")

    assert await hub.publish(first) == 2
    assert await hub.publish(second) == 2
    assert await first_queue.get() == second
    assert await second_queue.get() == second

    await hub.unsubscribe(first_queue)
    await hub.unsubscribe(second_queue)
    assert await hub.publish(_derivation_event()) == 0
    await hub.close()


@pytest.mark.asyncio
async def test_sse_stream_emits_retry_event_and_cleans_up() -> None:
    hub = PlayEventHub(subscriber_queue_capacity=4)
    runtime = PlayEventRuntime(
        hub=hub,
        token="token",
        heartbeat_seconds=0.01,
        retry_ms=3000,
    )

    class Request:
        app = SimpleNamespace(state=SimpleNamespace(play_events=runtime))

        async def is_disconnected(self) -> bool:
            return False

    response = await events_router.stream_events(Request())  # type: ignore[arg-type]
    iterator = response.body_iterator.__aiter__()
    assert await anext(iterator) == "retry: 3000\n\n"

    event = _dream_event()
    assert await hub.publish(event) == 1
    frame = await anext(iterator)
    assert frame.startswith(f"id: {event.event_id}\n")
    assert json.loads(frame.split("data: ", 1)[1]) == event.to_wire()
    assert await anext(iterator) == ": heartbeat\n\n"

    await iterator.aclose()  # type: ignore[attr-defined]
    assert await hub.publish(_derivation_event()) == 0
    await hub.close()


def test_internal_event_ingress_requires_token_and_validates_contract() -> None:
    app = FastAPI()
    app.state.play_events = PlayEventRuntime(
        hub=PlayEventHub(),
        token="secret",
        heartbeat_seconds=15,
        retry_ms=3000,
    )
    app.include_router(events_router.router, prefix="/play-api/v1")
    event = _dream_event()

    with TestClient(app) as client:
        missing = client.post(
            "/play-api/v1/internal/events",
            json=event.to_wire(),
        )
        assert missing.status_code == 401

        wrong = client.post(
            "/play-api/v1/internal/events",
            headers={"Authorization": "Bearer wrong"},
            json=event.to_wire(),
        )
        assert wrong.status_code == 401

        accepted = client.post(
            "/play-api/v1/internal/events",
            headers={"Authorization": "Bearer secret"},
            json=event.to_wire(),
        )
        assert accepted.status_code == 202
        assert accepted.json() == {
            "accepted": True,
            "eventId": event.event_id,
            "subscribers": 0,
        }

        invalid = event.to_wire()
        invalid["schemaVersion"] = "unknown"
        rejected = client.post(
            "/play-api/v1/internal/events",
            headers={"Authorization": "Bearer secret"},
            json=invalid,
        )
        assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_publisher_sends_bearer_contract_and_closes() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"accepted": True})

    publisher = PlayEventPublisher(
        endpoint_url="http://play.test/play-api/v1/internal/events",
        token="secret",
        transport=httpx.MockTransport(handle),
    )
    event = _derivation_event()
    await publisher.publish(event)
    await publisher.close()
    await publisher.close()

    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert json.loads(requests[0].content) == event.to_wire()
