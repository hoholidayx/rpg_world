"""Session endpoints for Play WebUI."""

from __future__ import annotations

import json
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Literal, TypeVar

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from agent_service.client import AgentClientError, AgentServiceUnavailable
from play_api.backends import get_agent_backend, get_data_manager_backend
from play_api.routers._locator import resolve_session_or_404
from rpg_core.session.turn_metadata import (
    InvalidTurnMetadataError,
    has_trustworthy_turn_metadata,
    validate_turn_metadata,
)
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


class PlaySessionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    workspace: str
    story_id: int = Field(alias="storyId")
    title: str | None = None
    description: str | None = None
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PlayCommand(BaseModel):
    name: str
    description: str
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


class PlayChatRequest(BaseModel):
    text: str
    mode: str = "ic"


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
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str | None = Field(default=None, alias="createdAt")


class PlayTurn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    turn_id: int = Field(alias="turnId")
    messages: list[PlayHistoryMessage] = Field(default_factory=list)


def _session_summary(session: dict[str, object]) -> PlaySessionSummary:
    now = datetime.now(UTC).isoformat()
    return PlaySessionSummary(
        id=str(session["id"]),
        workspace=str(session["workspace"]),
        story_id=int(session["story_id"]),
        title=str(session["title"]) if session.get("title") is not None else None,
        description=str(session["description"]) if session.get("description") is not None else None,
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


def _agent_error_event(exc: AgentClientError) -> dict[str, object]:
    return {"kind": "error", "content": str(exc)}


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


@router.get("/{session_id}/history", response_model=list[PlayTurn])
async def get_session_history(
    session_id: str,
) -> list[PlayTurn]:
    workspace, story_id, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    history = await _agent_call(
        get_agent_backend().get_history(workspace, story_id, agent_session_id)
    )
    try:
        return _turns_from_history(history, source="api")
    except InvalidTurnMetadataError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{session_id}/scene", response_model=PlayScene)
async def get_current_scene(session_id: str) -> PlayScene:
    _, _, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    attrs = get_data_service_gateway().status.get_scene_attrs(agent_session_id)
    return _scene_from_attrs(attrs)


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
            mode=str(item.get("mode", "slash")),
        )
        for item in commands
    ]


@router.get("/{session_id}/context-preview", response_model=ContextPreviewPayload)
async def get_context_preview(session_id: str) -> ContextPreviewPayload:
    workspace, story_id, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    preview = await _agent_call(
        get_agent_backend().get_context_preview(workspace, story_id, agent_session_id)
    )
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
        )
    )
    return {
        "turnId": f"turn_{agent_session_id}",
        "status": "completed",
        "workspace": workspace,
        "storyId": story_id,
        "sessionId": agent_session_id,
        "mode": payload.mode,
        "reply": result.get("reply", ""),
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

    async def event_generator():
        # SSE 事件保持 Agent 服务原始结构，Play API 这里只负责转发与 session 解析。
        try:
            async for event in get_agent_backend().stream(
                workspace,
                story_id,
                agent_session_id,
                payload.text,
                payload.mode,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except (AgentServiceUnavailable, AgentClientError) as exc:
            yield f"data: {json.dumps(_agent_error_event(exc), ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
