"""Agent service FastAPI app.

This process is the sole owner of ``AgentManager`` / ``RPGGameAgent`` runtime.
Other processes access it through ``agent_service.client.AgentClient``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agent_service.schemas import (
    AgentCommandRequest,
    AgentHealthResponse,
    AgentMessageRequest,
    AgentSessionCreateRequest,
    AgentSessionEnsureRequest,
)
from agent_service.settings import settings as process_settings
from llm_service.client import configure_llama_client_from_runtime_config
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind, TurnStats
from rpg_core.agent.command import CommandResult
from rpg_core.agent.loop import AgentReply
from rpg_core.agent.manager import AgentManager
from rpg_core.session import SessionManager
from rpg_data import models
from rpg_data.services import get_data_service_gateway


def _service_prefix() -> str:
    return process_settings.service.api_prefix


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_llama_client_from_runtime_config()
    yield
    AgentManager.reset()


app = FastAPI(title="RPG World Agent Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"{_service_prefix()}/health", response_model=AgentHealthResponse)
async def health() -> AgentHealthResponse:
    return AgentHealthResponse()


@app.get(f"{_service_prefix()}/chat/history")
async def get_history(
    workspace: str = Query(...),
    session_id: str = Query(...),
) -> dict[str, Any]:
    agent = _get_agent(workspace, session_id)
    try:
        await agent._ensure_initialized()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Agent initialization failed: {exc}") from exc
    return {"history": [m.to_dict() for m in agent.history]}


@app.get(f"{_service_prefix()}/chat/commands")
async def list_commands(
    workspace: str = Query(...),
    session_id: str = Query(...),
) -> dict[str, Any]:
    agent = _get_agent(workspace, session_id)
    try:
        await agent._ensure_initialized()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Agent initialization failed: {exc}") from exc
    return {
        "commands": [
            {"command": c.name, "description": c.description, "detail": c.detail}
            for c in agent.list_commands()
        ],
    }


@app.get(f"{_service_prefix()}/chat/sessions")
async def list_sessions(
    workspace_id: str = Query(...),
    story_id: int = Query(...),
) -> dict[str, Any]:
    workspace_id = _require_workspace(workspace_id)
    sessions = get_data_service_gateway().catalog.list_sessions(workspace_id, story_id)
    if sessions is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return {
        "sessions": [str(session.id) for session in sessions],
    }


@app.post(f"{_service_prefix()}/chat/sessions")
async def create_session(body: AgentSessionCreateRequest) -> dict[str, Any]:
    session = _create_catalog_session(
        body.workspace_id,
        int(body.story_id),
        title=str(body.title or ""),
    )
    return {"status": "created", **_session_payload(session)}


@app.post(f"{_service_prefix()}/chat/session/ensure")
async def ensure_session(body: AgentSessionEnsureRequest) -> dict[str, Any]:
    workspace_id = _require_workspace(body.workspace_id)
    story_id = int(body.story_id)
    gateway = get_data_service_gateway()

    if body.session_id:
        session = gateway.catalog.get_session(body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {body.session_id!r} not found")
        if str(session.workspace_id) != workspace_id or int(session.story_id) != story_id:
            raise HTTPException(status_code=400, detail=f"Session {body.session_id!r} does not belong to workspace/story")
    else:
        session = gateway.catalog.create_session(
            workspace_id,
            story_id,
            title=str(body.title or ""),
        )
        if session is None:
            raise HTTPException(status_code=404, detail="story not found in workspace")

    return _session_payload(session)


@app.post(f"{_service_prefix()}/chat/send")
async def chat_send(body: AgentMessageRequest) -> dict[str, Any]:
    agent = _get_agent(body.workspace, body.session_id)
    try:
        reply = await agent.send(body.message)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Chat send failed: {exc}") from exc
    return _reply_to_dict(reply)


@app.post(f"{_service_prefix()}/chat/command")
async def chat_command(body: AgentCommandRequest) -> dict[str, Any]:
    agent = _get_agent(body.workspace, body.session_id)
    command = body.command.strip()
    try:
        result = await agent.execute_command(command)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Command failed: {exc}") from exc
    if not result.handled:
        raise HTTPException(
            status_code=400,
            detail=f"未知命令: {command.split()[0] if command else '(empty)'}",
        )
    data = _command_result_to_dict(result)
    data["active_session"] = getattr(agent, "_session_id", body.session_id)
    return data


@app.post(f"{_service_prefix()}/chat/stream")
async def chat_stream(body: AgentMessageRequest) -> StreamingResponse:
    agent = _get_agent(body.workspace, body.session_id)

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in agent.send_stream(body.message):
                yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
        except Exception as exc:
            event = AgentStreamEvent(kind=StreamEventKind.ERROR, content=str(exc))
            yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _get_agent(workspace: str, session_id: str):
    workspace = _require_workspace(workspace)
    session_id = _require_session_id(session_id)
    return AgentManager.get_or_create(
        workspace=workspace,
        session_id=session_id,
    )


def _create_catalog_session(workspace_id: str, story_id: int, *, title: str) -> models.Session:
    workspace_id = _require_workspace(workspace_id)
    session = get_data_service_gateway().catalog.create_session(workspace_id, story_id, title=title)
    if session is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return session


def _session_payload(session: models.Session) -> dict[str, Any]:
    return {
        "workspace": str(session.workspace_id),
        "story_id": int(session.story_id),
        "session_id": str(session.id),
        "title": str(session.title or session.id),
    }


def _require_workspace(workspace: str) -> str:
    value = str(workspace or "").strip()
    if not value:
        raise HTTPException(status_code=422, detail="workspace is required")
    return value


def _require_session_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not value:
        raise HTTPException(status_code=422, detail="session_id is required")
    try:
        return SessionManager.validate_session_id(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _reply_to_dict(reply: AgentReply) -> dict[str, Any]:
    result: dict[str, Any] = {"reply": reply.text}
    if reply.tool_records:
        result["tool_records"] = [
            {
                "tool_calls": r.assistant_message.get("tool_calls", []),
                "tool_results": r.tool_results,
                "reasoning_content": r.reasoning_content,
            }
            for r in reply.tool_records
        ]
    if reply.status_sub_agent_records:
        result["status_sub_agent_records"] = reply.status_sub_agent_records
    if reply.stats:
        result["stats"] = _stats_to_dict(reply.stats)
    return result


def _command_result_to_dict(result: CommandResult) -> dict[str, Any]:
    payload: dict[str, Any] = {"reply": result.reply, "handled": result.handled}
    if result.stats is not None:
        payload["stats"] = result.stats
    return payload


def _stats_to_dict(stats: TurnStats) -> dict[str, Any]:
    return {
        "total_duration_ms": stats.total_duration_ms,
        "total_prompt_tokens": stats.total_prompt_tokens,
        "total_completion_tokens": stats.total_completion_tokens,
        "total_tokens": stats.total_tokens,
        "total_cached_tokens": stats.total_cached_tokens,
        "call_count": len(stats.calls),
    }
