"""Framework-neutral contracts for terminal events consumed by Play WebUI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import TypeAlias
from uuid import uuid4

from commons.types import JsonObject

PLAY_EVENT_SCHEMA_VERSION = "play_event_v1"


class PlayEventType(StrEnum):
    DREAM_PROPOSAL_TERMINAL = "dream.proposal.terminal"
    SESSION_DERIVATION_TERMINAL = "session.derivation.terminal"


class TerminalStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class DreamProposalTerminalPayload:
    proposal_id: str
    depth: str
    scope: str
    status: TerminalStatus
    error_code: str
    error_message: str
    finished_at: str
    updated_at: str

    def to_wire(self) -> JsonObject:
        return {
            "proposalId": self.proposal_id,
            "depth": self.depth,
            "scope": self.scope,
            "status": self.status.value,
            "errorCode": self.error_code,
            "errorMessage": self.error_message,
            "finishedAt": self.finished_at,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True)
class SessionDerivationTerminalPayload:
    job_id: str
    source_session_id: str
    target_session_id: str | None
    turn_id: int
    status: TerminalStatus
    error_code: str
    error_message: str
    context_threshold_exceeded: bool
    finished_at: str
    updated_at: str

    def to_wire(self) -> JsonObject:
        return {
            "jobId": self.job_id,
            "sourceSessionId": self.source_session_id,
            "targetSessionId": self.target_session_id,
            "turnId": self.turn_id,
            "status": self.status.value,
            "errorCode": self.error_code,
            "errorMessage": self.error_message,
            "contextThresholdExceeded": self.context_threshold_exceeded,
            "finishedAt": self.finished_at,
            "updatedAt": self.updated_at,
        }


TerminalPayload: TypeAlias = (
    DreamProposalTerminalPayload | SessionDerivationTerminalPayload
)


@dataclass(frozen=True)
class PlayEvent:
    event_id: str
    event_type: PlayEventType
    published_at: str
    session_id: str
    payload: TerminalPayload
    schema_version: str = PLAY_EVENT_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        event_type: PlayEventType,
        session_id: str,
        payload: TerminalPayload,
    ) -> "PlayEvent":
        expected_payload = {
            PlayEventType.DREAM_PROPOSAL_TERMINAL: DreamProposalTerminalPayload,
            PlayEventType.SESSION_DERIVATION_TERMINAL: SessionDerivationTerminalPayload,
        }[event_type]
        if not isinstance(payload, expected_payload):
            raise TypeError(
                f"payload for {event_type.value} must be {expected_payload.__name__}"
            )
        return cls(
            event_id=str(uuid4()),
            event_type=event_type,
            published_at=_utc_now(),
            session_id=_required_text(session_id, "session_id"),
            payload=payload,
        )

    def to_wire(self) -> JsonObject:
        return {
            "schemaVersion": self.schema_version,
            "eventId": self.event_id,
            "eventType": self.event_type.value,
            "publishedAt": self.published_at,
            "sessionId": self.session_id,
            "payload": self.payload.to_wire(),
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_text(value: str, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized

