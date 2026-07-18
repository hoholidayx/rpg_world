"""Internal Play event ingress and browser-facing global SSE stream."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from play_api.event_hub import PlayEventHubClosedError, PlayEventRuntime
from play_events import (
    PLAY_EVENT_SCHEMA_VERSION,
    DreamProposalTerminalPayload,
    PlayEvent,
    PlayEventType,
    SessionDerivationTerminalPayload,
    TerminalStatus,
)

router = APIRouter(tags=["events"])
logger = logging.getLogger("play_api.events")


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DreamProposalTerminalPayloadRequest(_WireModel):
    proposal_id: str = Field(alias="proposalId", min_length=1)
    depth: Literal["shallow", "deep"]
    scope: Literal["incremental", "full"]
    status: TerminalStatus
    error_code: str = Field(alias="errorCode")
    error_message: str = Field(alias="errorMessage")
    finished_at: str = Field(alias="finishedAt", min_length=1)
    updated_at: str = Field(alias="updatedAt", min_length=1)

    @field_validator("finished_at", "updated_at")
    @classmethod
    def _valid_timestamps(cls, value: str) -> str:
        return _validated_timestamp(value)


class SessionDerivationTerminalPayloadRequest(_WireModel):
    job_id: str = Field(alias="jobId", min_length=1)
    source_session_id: str = Field(alias="sourceSessionId", min_length=1)
    target_session_id: str | None = Field(alias="targetSessionId")
    turn_id: int = Field(alias="turnId", gt=0)
    status: TerminalStatus
    error_code: str = Field(alias="errorCode")
    error_message: str = Field(alias="errorMessage")
    context_threshold_exceeded: bool = Field(alias="contextThresholdExceeded")
    finished_at: str = Field(alias="finishedAt", min_length=1)
    updated_at: str = Field(alias="updatedAt", min_length=1)

    @field_validator("target_session_id")
    @classmethod
    def _valid_target_session_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("targetSessionId must not be empty")
        return value

    @field_validator("finished_at", "updated_at")
    @classmethod
    def _valid_timestamps(cls, value: str) -> str:
        return _validated_timestamp(value)


class PlayEventRequest(_WireModel):
    schema_version: str = Field(alias="schemaVersion")
    event_id: str = Field(alias="eventId")
    event_type: PlayEventType = Field(alias="eventType")
    published_at: str = Field(alias="publishedAt", min_length=1)
    session_id: str = Field(alias="sessionId", min_length=1)
    payload: (
        DreamProposalTerminalPayloadRequest
        | SessionDerivationTerminalPayloadRequest
    )

    @field_validator("schema_version")
    @classmethod
    def _valid_schema_version(cls, value: str) -> str:
        if value != PLAY_EVENT_SCHEMA_VERSION:
            raise ValueError("unsupported Play event schemaVersion")
        return value

    @field_validator("event_id")
    @classmethod
    def _valid_event_id(cls, value: str) -> str:
        UUID(value)
        return value

    @field_validator("published_at")
    @classmethod
    def _valid_published_at(cls, value: str) -> str:
        return _validated_timestamp(value)

    @model_validator(mode="after")
    def _payload_matches_event_type(self) -> "PlayEventRequest":
        expected = {
            PlayEventType.DREAM_PROPOSAL_TERMINAL: (
                DreamProposalTerminalPayloadRequest
            ),
            PlayEventType.SESSION_DERIVATION_TERMINAL: (
                SessionDerivationTerminalPayloadRequest
            ),
        }[self.event_type]
        if not isinstance(self.payload, expected):
            raise ValueError("payload does not match eventType")
        if (
            isinstance(self.payload, SessionDerivationTerminalPayloadRequest)
            and self.payload.source_session_id != self.session_id
        ):
            raise ValueError("sessionId must match payload.sourceSessionId")
        return self

    def to_contract(self) -> PlayEvent:
        if isinstance(self.payload, DreamProposalTerminalPayloadRequest):
            payload = DreamProposalTerminalPayload(
                proposal_id=self.payload.proposal_id,
                depth=self.payload.depth,
                scope=self.payload.scope,
                status=self.payload.status,
                error_code=self.payload.error_code,
                error_message=self.payload.error_message,
                finished_at=self.payload.finished_at,
                updated_at=self.payload.updated_at,
            )
        else:
            payload = SessionDerivationTerminalPayload(
                job_id=self.payload.job_id,
                source_session_id=self.payload.source_session_id,
                target_session_id=self.payload.target_session_id,
                turn_id=self.payload.turn_id,
                status=self.payload.status,
                error_code=self.payload.error_code,
                error_message=self.payload.error_message,
                context_threshold_exceeded=(
                    self.payload.context_threshold_exceeded
                ),
                finished_at=self.payload.finished_at,
                updated_at=self.payload.updated_at,
            )
        return PlayEvent(
            schema_version=self.schema_version,
            event_id=self.event_id,
            event_type=self.event_type,
            published_at=self.published_at,
            session_id=self.session_id,
            payload=payload,
        )


class PlayEventAcceptedResponse(_WireModel):
    accepted: bool = True
    event_id: str = Field(alias="eventId")
    subscribers: int


def _validated_timestamp(value: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    return value


def _runtime(request: Request) -> PlayEventRuntime:
    # Starlette intentionally exposes lifespan-owned resources through its
    # dynamic app.state boundary; the concrete type check keeps routes typed.
    runtime = getattr(request.app.state, "play_events", None)
    if not isinstance(runtime, PlayEventRuntime):
        raise HTTPException(status_code=503, detail="Play event stream is unavailable")
    return runtime


@router.post(
    "/internal/events",
    response_model=PlayEventAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def publish_event(
    request: Request,
    event: PlayEventRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> PlayEventAcceptedResponse:
    runtime = _runtime(request)
    expected = f"Bearer {runtime.token}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid Play event token")
    try:
        contract = event.to_contract()
        subscribers = await runtime.hub.publish(contract)
    except PlayEventHubClosedError as exc:
        raise HTTPException(
            status_code=503,
            detail="Play event stream is unavailable",
        ) from exc
    log = logger.warning if subscribers == 0 else logger.info
    log(
        "accepted Play event into hub event_id=%s event_type=%s "
        "session_id=%s status=%s subscribers=%s",
        contract.event_id,
        contract.event_type.value,
        contract.session_id,
        contract.payload.status.value,
        subscribers,
    )
    return PlayEventAcceptedResponse(
        eventId=event.event_id,
        subscribers=subscribers,
    )


@router.get("/events/stream")
async def stream_events(request: Request) -> StreamingResponse:
    runtime = _runtime(request)
    stream_id = uuid4().hex[:12]
    try:
        queue = await runtime.hub.subscribe()
    except PlayEventHubClosedError as exc:
        raise HTTPException(
            status_code=503,
            detail="Play event stream is unavailable",
        ) from exc
    logger.info("opened Play event stream stream_id=%s", stream_id)

    async def generate() -> AsyncIterator[str]:
        try:
            yield f"retry: {runtime.retry_ms}\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=runtime.heartbeat_seconds,
                    )
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if event is None:
                    return
                logger.debug(
                    "yielding Play event to stream stream_id=%s event_id=%s "
                    "event_type=%s session_id=%s",
                    stream_id,
                    event.event_id,
                    event.event_type.value,
                    event.session_id,
                )
                data = json.dumps(
                    event.to_wire(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"id: {event.event_id}\ndata: {data}\n\n"
        finally:
            await runtime.hub.unsubscribe(queue)
            logger.info("closed Play event stream stream_id=%s", stream_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
