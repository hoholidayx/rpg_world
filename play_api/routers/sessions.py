"""Session endpoints for Play WebUI."""

from __future__ import annotations

import json
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import TypeVar

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agent_service.client import AgentClientError, AgentServiceUnavailable
from play_api.backends import get_agent_backend, get_data_manager_backend
from play_api.routers._locator import resolve_session_or_404

router = APIRouter(prefix="/sessions", tags=["play-sessions"])
T = TypeVar("T")


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


class PlayTurn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    turn_id: int = Field(alias="turnId")
    user_message: str = Field(alias="userMessage")
    assistant_message: str | None = Field(default=None, alias="assistantMessage")
    source: str = "play_webui"
    created_at: str | None = Field(default=None, alias="createdAt")


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
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _agent_error_event(exc: AgentClientError) -> dict[str, object]:
    return {"kind": "error", "content": str(exc)}


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
    now = datetime.now(UTC).isoformat()
    turns: list[PlayTurn] = []
    pending_user: str | None = None
    turn_id = 1
    history = await _agent_call(
        get_agent_backend().get_history(workspace, story_id, agent_session_id)
    )
    for message in history:
        role = message.get("role")
        content = str(message.get("content", ""))
        if role == "user":
            pending_user = content
            continue
        if role == "assistant" and pending_user is not None:
            turns.append(
                PlayTurn(
                    turn_id=turn_id,
                    user_message=pending_user,
                    assistant_message=content,
                    created_at=now,
                )
            )
            turn_id += 1
            pending_user = None
    if pending_user is not None:
        turns.append(PlayTurn(turn_id=turn_id, user_message=pending_user, created_at=now))
    return turns


@router.get("/{session_id}/scene", response_model=PlayScene)
async def get_current_scene(session_id: str) -> PlayScene:
    workspace, story_id, agent_session_id = _session_context(await resolve_session_or_404(session_id))
    scene = await get_agent_backend().get_scene(workspace, story_id, agent_session_id)
    return PlayScene(
        attrs=dict(scene.get("attrs", {})),
        time=str(scene["time"]) if scene.get("time") is not None else None,
        location=str(scene["location"]) if scene.get("location") is not None else None,
        present_characters=list(scene.get("presentCharacters", [])),
        mood=str(scene["mood"]) if scene.get("mood") is not None else None,
    )


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
