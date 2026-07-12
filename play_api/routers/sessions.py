"""Session endpoints for Play WebUI."""

from __future__ import annotations

import json
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Literal, TypeVar

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_service.client import AgentClientError, AgentServiceUnavailable
from play_api.backends import get_agent_backend, get_data_manager_backend
from play_api.routers._locator import resolve_session_or_404
from play_api.sse_protocol import (
    AgentEventKind,
    PlaySSEStream,
    SSE_MEDIA_TYPE,
    SSE_RESPONSE_HEADERS,
    agent_event_kind,
)
from rpg_core.context.usage import ContextPreviewUsagePayload, TurnUsageWirePayload
from rpg_core.rp_modules.narrative_outcome import (
    NARRATIVE_OUTCOME_DEFINITIONS,
)
from rpg_core.session.turn_metadata import (
    InvalidTurnMetadataError,
    has_trustworthy_turn_metadata,
    validate_turn_metadata,
)
from rpg_core.turns import normalize_turn_mode
from rpg_data.services import get_data_service_gateway

router = APIRouter(prefix="/sessions", tags=["play-sessions"])
T = TypeVar("T")
HistoryTransformSource = Literal["api", "agent_internal"]


class PlaySessionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    workspace_id: str = Field(alias="workspaceId")
    story_id: int = Field(alias="storyId")
    title: str = ""
    description: str = ""


class PlayPlayerCharacterSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    character_id: int = Field(alias="characterId")
    mount_id: int = Field(alias="mountId")
    story_id: int = Field(alias="storyId")
    name: str
    avatar_url: str = Field(default="", alias="avatarUrl")
    role_label: str = Field(default="", alias="roleLabel")
    updated_at: str = Field(default="", alias="updatedAt")


class PlaySessionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    workspace: str
    story_id: int = Field(alias="storyId")
    title: str | None = None
    description: str | None = None
    player_character: PlayPlayerCharacterSnapshot | None = Field(default=None, alias="playerCharacter")
    player_character_status: Literal["bound", "invalid"] = Field(default="invalid", alias="playerCharacterStatus")
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PlayPlayerCharacterBindRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    player_character_id: int = Field(alias="playerCharacterId")


class PlayCommand(BaseModel):
    name: str
    description: str
    detail: str
    mode: str = "slash"


class ContextPreviewTotals(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    layer_count: int = Field(alias="layerCount")
    active_layers: int = Field(alias="activeLayers")
    token_count: int = Field(alias="tokenCount")
    message_count: int = Field(alias="messageCount")


class ContextPreviewLayer(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    index: int
    type: str
    role: str
    status: str
    char_count: int = Field(alias="charCount")
    token_count: int = Field(alias="tokenCount")
    description: str
    content: str


class ContextPreviewPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    format_version: str = Field(alias="formatVersion")
    session_id: str = Field(alias="sessionId")
    hot_history_rounds: int | None = Field(alias="hotHistoryRounds")
    totals: ContextPreviewTotals
    layers: list[ContextPreviewLayer] = Field(default_factory=list)
    messages: list[dict[str, object]] = Field(default_factory=list)
    usage_estimate: dict[str, object] | None = Field(default=None, alias="usageEstimate")


class PlayChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    text: str
    mode: Literal["ic", "ooc", "gm"] = "ic"
    narrative_style_id: int | None = Field(default=None, alias="narrativeStyleId", gt=0)
    request_id: str | None = Field(default=None, alias="requestId")

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: object) -> str:
        return normalize_turn_mode(value).value


class PlayStopRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_id: str | None = Field(default=None, alias="requestId")


class PlayScene(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    attrs: dict[str, str] = Field(default_factory=dict)
    time: str | None = None
    location: str | None = None
    present_characters: list[str] = Field(default_factory=list, alias="presentCharacters")
    mood: str | None = None


class PlayHistoryMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: int = Field(alias="messageId")
    turn_id: int = Field(alias="turnId")
    seq_in_turn: int = Field(alias="seqInTurn")
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    mode: Literal["ic", "ooc", "gm"] = "ic"
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str | None = Field(default=None, alias="createdAt")


class PlayTurn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    turn_id: int = Field(alias="turnId")
    messages: list[PlayHistoryMessage] = Field(default_factory=list)
    outcome: "PlayNarrativeOutcome | None" = None


class PlayNarrativeOutcome(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    outcome_code: str = Field(alias="outcomeCode")
    label: str
    narrative_guidance: str = Field(alias="narrativeGuidance")
    reason: str
    actor: str | None = None


class PlayHistoryPage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    turns: list[PlayTurn] = Field(default_factory=list)
    start_turn_id: int | None = Field(default=None, alias="startTurnId")
    end_turn_id: int | None = Field(default=None, alias="endTurnId")
    latest_turn_id: int = Field(alias="latestTurnId")
    has_before: bool = Field(alias="hasBefore")
    has_after: bool = Field(alias="hasAfter")
    limit: int


class PlaySummaryPreview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: Literal["overall", "batch"]
    batch_id: int | None = Field(default=None, alias="batchId")
    last_batch_id: int | None = Field(default=None, alias="lastBatchId")
    title: str
    excerpt: str
    time: str | None = None
    location: str | None = None
    characters: list[str] = Field(default_factory=list)
    turn_start: int | None = Field(default=None, alias="turnStart")
    turn_end: int | None = Field(default=None, alias="turnEnd")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PlaySummaryDetail(PlaySummaryPreview):
    markdown: str


class PlaySummaryIndex(BaseModel):
    overall: PlaySummaryPreview | None = None
    batches: list[PlaySummaryPreview] = Field(default_factory=list)


def _session_summary(session: dict[str, object]) -> PlaySessionSummary:
    now = datetime.now(UTC).isoformat()
    player = session.get("player_character")
    return PlaySessionSummary(
        id=str(session["id"]),
        workspace=str(session["workspace"]),
        story_id=int(session["story_id"]),
        title=str(session["title"]) if session.get("title") is not None else None,
        description=str(session["description"]) if session.get("description") is not None else None,
        player_character=(
            PlayPlayerCharacterSnapshot.model_validate(player)
            if isinstance(player, dict)
            else None
        ),
        player_character_status=(
            "bound"
            if str(session.get("player_character_status") or "") == "bound"
            else "invalid"
        ),
        created_at=str(session.get("created_at") or now),
        updated_at=str(session.get("updated_at") or now),
    )


def _session_context(session: dict[str, object]) -> tuple[str, int, str]:
    # Play API 负责校验公开 session id；Agent 服务运行态只需要 session_id。
    return (
        str(session["workspace"]),
        int(session["story_id"]),
        str(session["id"]),
    )


async def _agent_call(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except AgentServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentClientError as exc:
        if exc.status_code in {404, 409, 422}:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc


_SCENE_TIME_KEYS = ("time", "时间")
_SCENE_LOCATION_KEYS = ("location", "位置", "地点")
_SCENE_PRESENT_KEYS = ("presentCharacters", "present_characters", "在场人物", "在场角色", "在场")
_SCENE_MOOD_KEYS = ("mood", "氛围", "气氛", "情绪")


def _first_present(raw: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        value = raw.get(key)
        if value is not None and value != "":
            return value
    return None


def _positive_int(value: object | None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _history_role(raw: dict[str, object]) -> Literal["user", "assistant", "tool", "system"]:
    role = str(raw.get("role") or "assistant").lower()
    if role == "user":
        return "user"
    if role == "tool":
        return "tool"
    if role == "system":
        return "system"
    return "assistant"


def _history_message(
    raw: dict[str, object],
    fallback_turn_id: int,
    fallback_seq: int,
    *,
    use_raw_turn_ids: bool = True,
) -> PlayHistoryMessage:
    metadata = raw.get("metadata")
    raw_turn_id = _positive_int(_first_present(raw, "turnId", "turn_id")) if use_raw_turn_ids else None
    raw_seq = _positive_int(_first_present(raw, "seqInTurn", "seq_in_turn")) if use_raw_turn_ids else None
    return PlayHistoryMessage(
        message_id=_positive_int(_first_present(raw, "messageId", "uid")) or 0,
        turn_id=raw_turn_id or fallback_turn_id,
        seq_in_turn=raw_seq or fallback_seq,
        role=_history_role(raw),
        content=str(raw.get("content") or ""),
        mode=normalize_turn_mode(raw.get("mode")).value,
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=str(raw.get("createdAt")) if raw.get("createdAt") is not None else None,
    )


def _pair_history_groups(history: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    return [history[index:index + 2] for index in range(0, len(history), 2)]


def _legacy_history_groups(history: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    user_indices = [index for index, raw in enumerate(history) if _history_role(raw) == "user"]
    if not user_indices:
        return _pair_history_groups(history)

    groups: list[list[dict[str, object]]] = []
    for index, user_index in enumerate(user_indices):
        start = 0 if index == 0 else user_index
        end = user_indices[index + 1] if index + 1 < len(user_indices) else len(history)
        groups.append(history[start:end])
    return groups


def _turns_from_history(
    history: list[dict[str, object]],
    *,
    source: HistoryTransformSource = "api",
) -> list[PlayTurn]:
    if not history:
        return []

    if source == "api":
        validate_turn_metadata(history, label="history")
    elif not has_trustworthy_turn_metadata(history):
        return [
            PlayTurn(
                turn_id=turn_id,
                messages=[
                    _history_message(raw, turn_id, seq, use_raw_turn_ids=False)
                    for seq, raw in enumerate(group, start=1)
                ],
            )
            for turn_id, group in enumerate(_legacy_history_groups(history), start=1)
        ]

    turn_messages: dict[int, list[PlayHistoryMessage]] = {}
    for raw in history:
        turn_id = _positive_int(_first_present(raw, "turnId", "turn_id")) or 1
        seq_by_turn = len(turn_messages.get(turn_id, [])) + 1
        message = _history_message(raw, turn_id, seq_by_turn)
        turn_messages.setdefault(message.turn_id, []).append(message)

    turns: list[PlayTurn] = []
    for turn_id in sorted(turn_messages):
        messages = sorted(turn_messages[turn_id], key=lambda item: item.seq_in_turn)
        turns.append(PlayTurn(turn_id=turn_id, messages=messages))
    return turns


def _attach_narrative_outcomes(
    session_id: str,
    turns: list[PlayTurn],
) -> list[PlayTurn]:
    if not turns:
        return turns
    definitions = {
        definition.code: definition for definition in NARRATIVE_OUTCOME_DEFINITIONS
    }
    records = get_data_service_gateway().narrative_outcomes.list_for_turns(
        session_id,
        (turn.turn_id for turn in turns),
    )
    records_by_turn = {record.turn_id: record for record in records}
    for turn in turns:
        record = records_by_turn.get(turn.turn_id)
        if record is None:
            continue
        definition = definitions[record.outcome_code]
        turn.outcome = PlayNarrativeOutcome(
            outcomeCode=record.outcome_code,
            label=definition.label,
            narrativeGuidance=definition.narrative_guidance,
            reason=record.reason,
            actor=record.actor or None,
        )
    return turns


def _history_payload_from_row(row: object) -> dict[str, object]:
    metadata = _json_dict_from_text(str(getattr(row, "metadata_json", "") or "{}"))
    payload: dict[str, object] = {
        "messageId": int(getattr(row, "id", 0) or 0),
        "turnId": int(getattr(row, "turn_id", 0) or 0),
        "seqInTurn": int(getattr(row, "seq_in_turn", 0) or 0),
        "role": str(getattr(row, "role", "") or "assistant"),
        "content": str(getattr(row, "content", "") or ""),
        "mode": str(getattr(row, "mode", "") or "ic"),
        "metadata": metadata,
    }
    created_at = str(getattr(row, "created_at", "") or "")
    if created_at:
        payload["createdAt"] = created_at
    return payload


def _json_dict_from_text(raw: str) -> dict[str, object]:
    try:
        payload: object = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _scene_from_attrs(attrs: dict[str, str] | None) -> PlayScene:
    if not attrs:
        return PlayScene()
    used: set[str] = set()
    time_value, time_key = _first_attr(attrs, _SCENE_TIME_KEYS)
    location_value, location_key = _first_attr(attrs, _SCENE_LOCATION_KEYS)
    present_value, present_key = _first_attr(attrs, _SCENE_PRESENT_KEYS)
    mood_value, mood_key = _first_attr(attrs, _SCENE_MOOD_KEYS)
    used.update(key for key in (time_key, location_key, present_key, mood_key) if key)
    return PlayScene(
        attrs={key: value for key, value in attrs.items() if key not in used},
        time=time_value,
        location=location_value,
        present_characters=_split_scene_list(present_value),
        mood=mood_value,
    )


def _first_attr(attrs: dict[str, str], keys: tuple[str, ...]) -> tuple[str | None, str | None]:
    for key in keys:
        if key in attrs and str(attrs[key]).strip():
            return str(attrs[key]), key
    return None, None


def _split_scene_list(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = value.replace("、", ",").replace("，", ",").replace("；", ",").replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


@router.get("", response_model=list[PlaySessionSummary])
async def list_sessions(
    workspace: str = Query(...),
    story_id: int = Query(...),
) -> list[PlaySessionSummary]:
    sessions = await get_data_manager_backend().list_sessions(workspace, story_id)
    if sessions is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return [_session_summary(session) for session in sessions]


@router.post("", response_model=PlaySessionSummary)
async def create_session(payload: PlaySessionCreateRequest) -> PlaySessionSummary:
    # 创建是 session 绑定 workspace/story 的唯一入口；会话内接口之后只收 session_id。
    session = await get_data_manager_backend().create_session(
        payload.workspace_id,
        payload.story_id,
        title=payload.title,
        description=payload.description,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _session_summary(session)


@router.get("/{session_id}", response_model=PlaySessionSummary)
async def get_session(session_id: str) -> PlaySessionSummary:
    return _session_summary(await resolve_session_or_404(session_id))


@router.patch("/{session_id}/player-character", response_model=PlaySessionSummary)
async def bind_player_character(session_id: str, payload: PlayPlayerCharacterBindRequest) -> PlaySessionSummary:
    session = await resolve_session_or_404(session_id)
    workspace, story_id, agent_session_id = _session_context(session)
    logger.info(
        "[PlayAPI] player character bind requested: session_id={}, workspace={}, story_id={}, character_id={}",
        agent_session_id,
        workspace,
        story_id,
        payload.player_character_id,
    )
    await _agent_call(
        get_agent_backend().bind_player_character(
            workspace,
            story_id,
            agent_session_id,
            payload.player_character_id,
        )
    )
    updated = await get_data_manager_backend().get_session(agent_session_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="session not found")
    logger.info(
        "[PlayAPI] player character bind summary refreshed: session_id={}, status={}, bound_character_id={}",
        agent_session_id,
        updated.get("player_character_status"),
        (updated.get("player_character") or {}).get("character_id") if isinstance(updated.get("player_character"), dict) else None,
    )
    return _session_summary(updated)


@router.get("/{session_id}/history", response_model=list[PlayTurn])
async def get_session_history(
    session_id: str,
) -> list[PlayTurn]:
    workspace, story_id, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    history = await _agent_call(
        get_agent_backend().get_history(workspace, story_id, agent_session_id)
    )
    try:
        return _attach_narrative_outcomes(
            agent_session_id,
            _turns_from_history(history, source="api"),
        )
    except InvalidTurnMetadataError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{session_id}/history-page", response_model=PlayHistoryPage)
async def get_session_history_page(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before_turn_id: int | None = Query(default=None, alias="beforeTurnId", gt=0),
    after_turn_id: int | None = Query(default=None, alias="afterTurnId", gt=0),
) -> PlayHistoryPage:
    if before_turn_id is not None and after_turn_id is not None:
        raise HTTPException(status_code=400, detail="beforeTurnId and afterTurnId are mutually exclusive")

    _, _, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    messages = get_data_service_gateway().messages

    rows = messages.list_turn_window(
        agent_session_id,
        limit=limit,
        before_turn_id=before_turn_id,
        after_turn_id=after_turn_id,
    )
    raw_history = [_history_payload_from_row(row) for row in rows]
    try:
        turns = _attach_narrative_outcomes(
            agent_session_id,
            _turns_from_history(raw_history, source="api"),
        )
    except InvalidTurnMetadataError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    start_turn_id = turns[0].turn_id if turns else None
    end_turn_id = turns[-1].turn_id if turns else None
    latest_turn_id = messages.latest_turn_id(agent_session_id)
    return PlayHistoryPage(
        turns=turns,
        startTurnId=start_turn_id,
        endTurnId=end_turn_id,
        latestTurnId=latest_turn_id,
        hasBefore=bool(start_turn_id and messages.has_turn_before(agent_session_id, start_turn_id)),
        hasAfter=bool(end_turn_id and messages.has_turn_after(agent_session_id, end_turn_id)),
        limit=limit,
    )


@router.get("/{session_id}/scene", response_model=PlayScene)
async def get_current_scene(session_id: str) -> PlayScene:
    _, _, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    attrs = get_data_service_gateway().status.get_scene_attrs(agent_session_id)
    return _scene_from_attrs(attrs)


@router.get("/{session_id}/summaries", response_model=PlaySummaryIndex)
async def list_session_summaries(session_id: str) -> PlaySummaryIndex:
    await resolve_session_or_404(session_id)
    payload = await get_data_manager_backend().list_session_summaries(session_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="session not found")
    return PlaySummaryIndex.model_validate(payload)


@router.get(
    "/{session_id}/summaries/{summary_key}",
    response_model=PlaySummaryDetail,
)
async def get_session_summary(
    session_id: str,
    summary_key: str,
) -> PlaySummaryDetail:
    await resolve_session_or_404(session_id)
    if summary_key != "overall" and not summary_key.isdecimal():
        raise HTTPException(status_code=404, detail="summary not found")
    normalized_key: str | int = (
        "overall" if summary_key == "overall" else int(summary_key)
    )
    payload = await get_data_manager_backend().get_session_summary(
        session_id,
        normalized_key,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="summary not found")
    return PlaySummaryDetail.model_validate(payload)


@router.get("/{session_id}/commands", response_model=list[PlayCommand])
async def list_commands(session_id: str) -> list[PlayCommand]:
    workspace, story_id, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    commands = await _agent_call(
        get_agent_backend().list_commands(workspace, story_id, agent_session_id)
    )
    return [
        PlayCommand(
            name=str(item.get("name", "")),
            description=str(item.get("description", "")),
            detail=str(item.get("detail", "")),
            mode=str(item.get("mode", "slash")),
        )
        for item in commands
    ]


@router.get("/{session_id}/context-preview", response_model=ContextPreviewPayload)
async def get_context_preview(
    session_id: str,
    mode: str | None = Query(default=None),
    narrative_style_id: int | None = Query(default=None, alias="narrativeStyleId", gt=0),
) -> ContextPreviewPayload:
    workspace, story_id, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    try:
        normalized_mode = normalize_turn_mode(mode).value
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    preview = await _agent_call(
        get_agent_backend().get_context_preview(
            workspace,
            story_id,
            agent_session_id,
            mode=normalized_mode,
            narrative_style_id=narrative_style_id,
        )
    )
    _log_context_preview_usage(session_id=agent_session_id, preview=preview)
    return ContextPreviewPayload.model_validate(preview)


@router.post("/{session_id}/turn")
async def create_turn(session_id: str, payload: PlayChatRequest) -> dict[str, object]:
    session = await resolve_session_or_404(session_id)
    workspace, story_id, agent_session_id = _session_context(session)
    result = await _agent_call(
        get_agent_backend().send(
            workspace,
            story_id,
            agent_session_id,
            payload.text,
            payload.mode,
            payload.narrative_style_id,
        )
    )
    _log_turn_usage(session_id=agent_session_id, usage=result.get("usage"), mode=payload.mode)
    return {
        "turnId": f"turn_{agent_session_id}",
        "status": "completed",
        "workspace": workspace,
        "storyId": story_id,
        "sessionId": agent_session_id,
        "mode": payload.mode,
        "committedTurnId": _positive_int(
            result.get("committedTurnId") or result.get("committed_turn_id")
        ),
        "reply": result.get("reply", ""),
        "usage": result.get("usage"),
        "agent": result,
    }


@router.post("/{session_id}/turns/{turn_id}/truncate")
async def truncate_turn(session_id: str, turn_id: int) -> dict[str, object]:
    session = await resolve_session_or_404(session_id)
    workspace, story_id, agent_session_id = _session_context(session)
    result = await _agent_call(
        get_agent_backend().truncate_turn(workspace, story_id, agent_session_id, turn_id)
    )
    logger.info(
        "[PlayAPI] session truncate result: session_id={}, turn_id={}, removed={}, sync_status={}",
        agent_session_id,
        turn_id,
        result.get("removed"),
        result.get("agent_sync_status"),
    )
    return {
        "status": "truncated",
        "workspace": workspace,
        "storyId": story_id,
        "sessionId": agent_session_id,
        "turnId": turn_id,
        "removed": int(result.get("removed") or 0),
        "agent": result,
    }


@router.delete("/{session_id}/messages/{message_id}")
async def delete_message(session_id: str, message_id: int) -> dict[str, object]:
    session = await resolve_session_or_404(session_id)
    workspace, story_id, agent_session_id = _session_context(session)
    result = await _agent_call(
        get_agent_backend().delete_message(workspace, story_id, agent_session_id, message_id)
    )
    return {
        "status": "deleted",
        "workspace": workspace,
        "storyId": story_id,
        "sessionId": agent_session_id,
        "messageId": message_id,
        "agent": result,
    }


@router.post("/{session_id}/stream")
async def stream_turn(session_id: str, payload: PlayChatRequest) -> StreamingResponse:
    workspace, story_id, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    stream = PlaySSEStream(agent_session_id)

    async def event_generator():
        yield stream.turn_started(mode=payload.mode)
        try:
            async for event in get_agent_backend().stream(
                workspace,
                story_id,
                agent_session_id,
                payload.text,
                payload.mode,
                payload.narrative_style_id,
                request_id=payload.request_id,
            ):
                kind = agent_event_kind(event)
                encoded = stream.agent_event(event)
                if encoded is None:
                    logger.debug(
                        "[PlayAPI] ignored unsupported agent stream event: session_id={}, kind={}",
                        agent_session_id,
                        kind,
                    )
                    continue
                if kind == AgentEventKind.DONE.value:
                    _log_stream_done_usage(session_id=agent_session_id, usage=event.get("usage"), mode=payload.mode)
                yield encoded
        except (AgentServiceUnavailable, AgentClientError) as exc:
            yield stream.error(str(exc), status_code=exc.status_code)

    return StreamingResponse(
        event_generator(),
        media_type=SSE_MEDIA_TYPE,
        headers=SSE_RESPONSE_HEADERS,
    )


@router.post("/{session_id}/stop")
async def stop_turn(session_id: str, payload: PlayStopRequest | None = None) -> dict[str, object]:
    session = await resolve_session_or_404(session_id)
    workspace, story_id, agent_session_id = _session_context(session)
    result = await _agent_call(
        get_agent_backend().stop(
            workspace,
            story_id,
            agent_session_id,
            request_id=payload.request_id if payload else None,
        )
    )
    return {
        "status": result.get("status", "not_running"),
        "workspace": workspace,
        "storyId": story_id,
        "sessionId": agent_session_id,
        "requestId": result.get("request_id"),
        "agent": result,
    }


def _log_context_preview_usage(*, session_id: str, preview: dict[str, object]) -> None:
    usage = ContextPreviewUsagePayload.from_payload(preview)
    if usage is None:
        logger.warning("[PlayAPI] context preview missing usageEstimate: session_id={}", session_id)
        return
    logger.debug(
        "[PlayAPI] context preview usage estimate: session_id={}, used_tokens={}, context_limit={}, source={}, accuracy={}, token_count={}",
        session_id,
        usage.used_tokens,
        usage.context_limit,
        usage.source,
        usage.accuracy,
        usage.token_count,
    )


def _log_turn_usage(*, session_id: str, usage: object, mode: str) -> None:
    usage_view = TurnUsageWirePayload.from_payload(usage)
    if usage_view is None:
        logger.warning("[PlayAPI] turn completed without usage: session_id={}, mode={}", session_id, mode)
        return
    logger.debug(
        "[PlayAPI] turn usage forwarded: session_id={}, mode={}, prompt={}, completion={}, total={}, cached={}, source={}, accuracy={}",
        session_id,
        mode,
        usage_view.prompt_tokens,
        usage_view.completion_tokens,
        usage_view.total_tokens,
        usage_view.cached_tokens,
        usage_view.source,
        usage_view.accuracy,
    )


def _log_stream_done_usage(*, session_id: str, usage: object, mode: str) -> None:
    usage_view = TurnUsageWirePayload.from_payload(usage)
    if usage_view is None:
        logger.warning("[PlayAPI] stream completed without usage: session_id={}, mode={}", session_id, mode)
        return
    logger.debug(
        "[PlayAPI] stream usage forwarded: session_id={}, mode={}, prompt={}, completion={}, total={}, cached={}, source={}, accuracy={}",
        session_id,
        mode,
        usage_view.prompt_tokens,
        usage_view.completion_tokens,
        usage_view.total_tokens,
        usage_view.cached_tokens,
        usage_view.source,
        usage_view.accuracy,
    )
