"""Agent service request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rpg_core.session.manager import DEFAULT_SESSION_ID, SessionManager


class _BaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRequestBase(_BaseSchema):
    workspace: str
    session_id: str = DEFAULT_SESSION_ID
    api_key: str | None = None

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return SessionManager.validate_session_id(value)


class AgentMessageRequest(AgentRequestBase):
    message: str


class AgentCommandRequest(AgentRequestBase):
    command: str


class AgentSessionCreateRequest(_BaseSchema):
    workspace: str
    session_id: str

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return SessionManager.validate_session_id(value)


class AgentSessionCloneRequest(_BaseSchema):
    workspace: str
    target_session_id: str

    @field_validator("target_session_id")
    @classmethod
    def _validate_target_session_id(cls, value: str) -> str:
        return SessionManager.validate_session_id(value)


class AgentHealthResponse(_BaseSchema):
    status: str = "ok"


class AgentHistoryResponse(_BaseSchema):
    history: list[dict] = Field(default_factory=list)


class AgentCommandsResponse(_BaseSchema):
    commands: list[dict] = Field(default_factory=list)
