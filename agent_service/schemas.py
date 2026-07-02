"""Agent service request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rpg_core.session.manager import DEFAULT_SESSION_ID, SessionManager


class _BaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRequestBase(_BaseSchema):
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


class AgentContextPreviewTotals(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    layer_count: int = Field(alias="layerCount")
    active_layers: int = Field(alias="activeLayers")
    token_count: int = Field(alias="tokenCount")
    message_count: int = Field(alias="messageCount")


class AgentContextPreviewLayer(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    index: int
    type: str
    role: str
    status: str
    char_count: int = Field(alias="charCount")
    token_count: int = Field(alias="tokenCount")
    description: str
    content: str


class AgentContextPreviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    format_version: str = Field(alias="formatVersion")
    session_id: str = Field(alias="sessionId")
    hot_history_rounds: int | None = Field(alias="hotHistoryRounds")
    totals: AgentContextPreviewTotals
    layers: list[AgentContextPreviewLayer] = Field(default_factory=list)
    messages: list[dict[str, object]] = Field(default_factory=list)
