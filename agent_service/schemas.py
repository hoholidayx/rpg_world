"""Agent service request/response schemas."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from commons.types import JsonObject, JsonValue
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


class AgentSessionMutationRequest(AgentRequestBase):
    pass


class AgentMessageUpdateRequest(AgentRequestBase):
    content: str


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
    history: list[JsonObject] = Field(default_factory=list)


class AgentCommandInfo(_BaseSchema):
    command: str
    description: str
    detail: str


class AgentCommandsResponse(_BaseSchema):
    commands: list[AgentCommandInfo] = Field(default_factory=list)


class AgentSessionsResponse(_BaseSchema):
    sessions: list[str] = Field(default_factory=list)


class AgentSessionPayload(_BaseSchema):
    workspace: str
    story_id: int
    session_id: str
    title: str


class AgentSessionCreateResponse(AgentSessionPayload):
    status: Literal["created"] = "created"


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
    messages: list[JsonObject] = Field(default_factory=list)


class AgentHealthPayload(TypedDict):
    status: str


class AgentHistoryPayload(TypedDict):
    history: list[JsonObject]


class AgentCommandPayload(TypedDict):
    command: str
    description: str
    detail: str


class AgentCommandsPayload(TypedDict):
    commands: list[AgentCommandPayload]


class AgentSessionsPayload(TypedDict):
    sessions: list[str]


class AgentSessionPayloadDict(TypedDict):
    workspace: str
    story_id: int
    session_id: str
    title: str


class AgentSessionCreatePayload(AgentSessionPayloadDict):
    status: Literal["created"]


class AgentStatsPayload(TypedDict):
    total_duration_ms: float
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cached_tokens: int
    call_count: int


class AgentToolRecordPayload(TypedDict):
    tool_calls: JsonValue
    tool_results: list[JsonObject]
    reasoning_content: str | None


class AgentReplyPayloadBase(TypedDict):
    reply: str


class AgentReplyPayload(AgentReplyPayloadBase, total=False):
    tool_records: list[AgentToolRecordPayload]
    status_sub_agent_records: list[JsonObject]
    stats: AgentStatsPayload


class AgentCommandResultPayloadBase(TypedDict):
    reply: str
    handled: bool


class AgentCommandResultPayload(AgentCommandResultPayloadBase, total=False):
    stats: JsonObject
    active_session: str


class AgentStreamEventPayload(TypedDict):
    kind: str
    content: NotRequired[str]
    tool_name: NotRequired[str]
    tool_arguments: NotRequired[str]
    tool_result_preview: NotRequired[str]
    round_index: NotRequired[int]
    usage: NotRequired[JsonObject]
    duration_ms: NotRequired[float]
    model: NotRequired[str]
    finish_reason: NotRequired[str]
