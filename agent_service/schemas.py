"""Agent service request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rpg_core.session.manager import DEFAULT_SESSION_ID, SessionManager


class _BaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRequestBase(_BaseSchema):
    workspace: str
    session_id: str = DEFAULT_SESSION_ID

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        return SessionManager.validate_session_id(value)


class AgentMessageRequest(AgentRequestBase):
    message: str


class AgentCommandRequest(AgentRequestBase):
    command: str


class AgentSessionEnsureRequest(_BaseSchema):
    workspace_id: str
    story_id: int
    session_id: str | None = None
    title: str = ""

    @field_validator("session_id")
    @classmethod
    def _validate_optional_session_id(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return SessionManager.validate_session_id(str(value))


class AgentSessionCreateRequest(_BaseSchema):
    workspace_id: str
    story_id: int
    title: str = ""


class AgentHealthResponse(_BaseSchema):
    status: str = "ok"


class AgentHistoryResponse(_BaseSchema):
    history: list[dict] = Field(default_factory=list)


class AgentCommandsResponse(_BaseSchema):
    commands: list[dict] = Field(default_factory=list)
