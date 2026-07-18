"""Agent service request/response schemas."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from commons.types import JsonObject, JsonValue
from rpg_core.agent.protocol import TurnCancelStatus
from rpg_core.session.manager import DEFAULT_SESSION_ID, SessionManager
from rpg_core.agent.turn.models import normalize_turn_mode


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
    mode: Literal["ic", "ooc", "gm"] = "ic"
    narrative_style_id: int | None = Field(default=None, gt=0)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: object) -> str:
        return normalize_turn_mode(value).value


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


class AgentSessionDerivationCreateRequest(AgentRequestBase):
    branch_turn_id: int = Field(gt=0)
    title: str = ""


class AgentHealthResponse(_BaseSchema):
    status: str = "ok"
    llm_service: str = "unknown"


class AgentHistoryResponse(_BaseSchema):
    history: list[JsonObject] = Field(default_factory=list)


class AgentCommandInfo(_BaseSchema):
    command: str
    description: str
    detail: str


class AgentCommandsResponse(_BaseSchema):
    commands: list[AgentCommandInfo] = Field(default_factory=list)


class AgentSessionSummaryResponse(_BaseSchema):
    session_id: str
    title: str


class AgentSessionsResponse(_BaseSchema):
    sessions: list[AgentSessionSummaryResponse] = Field(default_factory=list)


class AgentPlayerCharacterInfoResponse(_BaseSchema):
    character_id: int
    name: str


class AgentSessionOverviewResponse(_BaseSchema):
    workspace_id: str
    workspace_title: str
    story_id: int
    story_title: str
    session_id: str
    session_title: str
    player_character_status: Literal["bound", "invalid"]
    player_character: AgentPlayerCharacterInfoResponse | None = None
    role_options: list[AgentPlayerCharacterInfoResponse] = Field(default_factory=list)


class AgentPlayerCharacterBindResponse(_BaseSchema):
    status: Literal["bound"] = "bound"
    session_id: str
    player_character_id: int
    player_character: AgentPlayerCharacterInfoResponse
    first_message: str = ""
    reply: str


class AgentSessionPayload(_BaseSchema):
    workspace: str
    story_id: int
    session_id: str
    title: str


class AgentSessionCreateResponse(AgentSessionPayload):
    status: Literal["created"] = "created"


class AgentSessionDeleteResponse(_BaseSchema):
    status: Literal["deleted"] = "deleted"
    session_id: str
    runtime_cleanup: Literal["deleted", "absent", "pending"]


class AgentSessionDerivationJobResponse(_BaseSchema):
    job_id: str
    source_session_id: str
    target_session_id: str | None = None
    branch_turn_id: int
    status: Literal["queued", "running", "ready", "failed", "interrupted"]
    stage: str
    error_code: str = ""
    error_message: str = ""
    context_usage: JsonObject | None = None
    context_threshold_exceeded: bool = False
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    updated_at: str = ""


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
    llm_service: NotRequired[str]


class AgentHistoryPayload(TypedDict):
    history: list[JsonObject]


class AgentCommandPayload(TypedDict):
    command: str
    description: str
    detail: str


class AgentCommandsPayload(TypedDict):
    commands: list[AgentCommandPayload]


class AgentSessionSummaryPayload(TypedDict):
    session_id: str
    title: str


class AgentSessionsPayload(TypedDict):
    sessions: list[AgentSessionSummaryPayload]


class AgentPlayerCharacterInfoPayload(TypedDict):
    character_id: int
    name: str


class AgentSessionOverviewPayload(TypedDict):
    workspace_id: str
    workspace_title: str
    story_id: int
    story_title: str
    session_id: str
    session_title: str
    player_character_status: Literal["bound", "invalid"]
    player_character: AgentPlayerCharacterInfoPayload | None
    role_options: list[AgentPlayerCharacterInfoPayload]


class AgentPlayerCharacterBindPayload(TypedDict):
    status: Literal["bound"]
    session_id: str
    player_character_id: int
    player_character: AgentPlayerCharacterInfoPayload
    first_message: str
    reply: str


class AgentSessionPayloadDict(TypedDict):
    workspace: str
    story_id: int
    session_id: str
    title: str


class AgentSessionCreatePayload(AgentSessionPayloadDict):
    status: Literal["created"]


class AgentSessionDeletePayload(TypedDict):
    status: Literal["deleted"]
    session_id: str
    runtime_cleanup: Literal["deleted", "absent", "pending"]


class AgentSessionDerivationJobPayload(TypedDict):
    job_id: str
    source_session_id: str
    target_session_id: str | None
    branch_turn_id: int
    status: Literal["queued", "running", "ready", "failed", "interrupted"]
    stage: str
    error_code: str
    error_message: str
    context_usage: JsonObject | None
    context_threshold_exceeded: bool
    created_at: str
    started_at: str
    finished_at: str
    updated_at: str


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
    committed_turn_id: int
    active_session: str


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
    committed_turn_id: NotRequired[int]
    active_session: NotRequired[str]
