"""Agent service request/response schemas."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from commons.types import JsonObject, JsonValue
from rpg_core.agent.agent_types import TurnCancelStatus
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
    request_id: str | None = None


class AgentStopRequest(AgentRequestBase):
    request_id: str | None = None


class AgentSessionMutationRequest(AgentRequestBase):
    pass


class AgentCommandRequest(AgentRequestBase):
    command: str


class AgentPlayerCharacterBindRequest(AgentRequestBase):
    player_character_id: int


class AgentMainLLMStoryUpdateRequest(_BaseSchema):
    workspace_id: str
    story_id: int
    provider_key: str | None


class AgentMainLLMSessionUpdateRequest(AgentRequestBase):
    provider_key: str | None


class AgentSessionEnsureRequest(_BaseSchema):
    workspace_id: str
    story_id: int
    session_id: str | None = None
    title: str = ""
    player_character_id: int | None = None

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
    player_character_id: int | None = None


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


class AgentTurnCancelResponse(_BaseSchema):
    status: TurnCancelStatus
    session_id: str
    request_id: str | None = None


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
    usage_estimate: JsonObject | None = Field(default=None, alias="usageEstimate")


class AgentMainLLMProviderOptionResponse(_BaseSchema):
    provider_key: str
    backend: str
    model: str
    context_window: int | None = None


class AgentMainLLMInvalidOverrideResponse(_BaseSchema):
    source: Literal["story", "session"]
    provider_key: str


class AgentMainLLMProviderCatalogResponse(_BaseSchema):
    config_default_provider_key: str
    options: list[AgentMainLLMProviderOptionResponse] = Field(default_factory=list)


class AgentMainLLMSelectionResponse(_BaseSchema):
    config_default_provider_key: str
    story_provider_key: str | None = None
    session_provider_key: str | None = None
    effective_provider_key: str
    effective_source: Literal["config", "story", "session"]
    effective: AgentMainLLMProviderOptionResponse
    invalid_overrides: list[AgentMainLLMInvalidOverrideResponse] = Field(default_factory=list)


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


class AgentMainLLMProviderOptionPayload(TypedDict):
    provider_key: str
    backend: str
    model: str
    context_window: int | None


class AgentMainLLMInvalidOverridePayload(TypedDict):
    source: Literal["story", "session"]
    provider_key: str


class AgentMainLLMProviderCatalogPayload(TypedDict):
    config_default_provider_key: str
    options: list[AgentMainLLMProviderOptionPayload]


class AgentMainLLMSelectionPayload(TypedDict):
    config_default_provider_key: str
    story_provider_key: str | None
    session_provider_key: str | None
    effective_provider_key: str
    effective_source: Literal["config", "story", "session"]
    effective: AgentMainLLMProviderOptionPayload
    invalid_overrides: list[AgentMainLLMInvalidOverridePayload]


class AgentTurnCancelPayloadBase(TypedDict):
    status: TurnCancelStatus
    session_id: str


class AgentTurnCancelPayload(AgentTurnCancelPayloadBase, total=False):
    request_id: str


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
    usage: JsonObject


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
    tool_result: NotRequired[str]
    tool_result_preview: NotRequired[str]
    round_index: NotRequired[int]
    usage: NotRequired[JsonObject]
    duration_ms: NotRequired[float]
    model: NotRequired[str]
    finish_reason: NotRequired[str]
