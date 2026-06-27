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
    AgentSessionCloneRequest,
    AgentSessionCreateRequest,
)
from agent_service.settings import settings as process_settings
from llm_service.client import configure_llama_client_from_runtime_config
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind, TurnStats
from rpg_core.agent.command import CommandResult
from rpg_core.agent.loop import AgentReply
from rpg_core.agent.manager import AgentManager
from rpg_core.session import SessionManager


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
    api_key: str | None = Query(default=None),
) -> dict[str, Any]:
    agent = _get_agent(workspace, session_id, api_key)
    try:
        await agent._ensure_initialized()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Agent initialization failed: {exc}") from exc
    return {"history": [m.to_dict() for m in agent.history]}


@app.get(f"{_service_prefix()}/chat/commands")
async def list_commands(
    workspace: str = Query(...),
    session_id: str = Query(...),
    api_key: str | None = Query(default=None),
) -> dict[str, Any]:
    agent = _get_agent(workspace, session_id, api_key)
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
    workspace: str = Query(...),
    session_id: str = Query(...),
    api_key: str | None = Query(default=None),
) -> dict[str, Any]:
    del api_key
    workspace = _require_workspace(workspace)
    session_id = _require_session_id(session_id)
    return {
        "sessions": SessionManager.list_sessions(workspace),
        "active_session": session_id,
    }


@app.post(f"{_service_prefix()}/chat/sessions")
async def create_session(body: AgentSessionCreateRequest) -> dict[str, Any]:
    workspace = _require_workspace(body.workspace)
    session_id = _require_session_id(body.session_id)
    try:
        SessionManager.create(workspace, session_id)
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"Session {session_id!r} already exists")
    return {"status": "created", "session_id": session_id}


@app.delete(f"{_service_prefix()}/chat/sessions/{{session_id}}")
async def delete_session(
    session_id: str,
    workspace: str = Query(...),
) -> dict[str, Any]:
    workspace = _require_workspace(workspace)
    session_id = _require_session_id(session_id)
    available = set(SessionManager.list_sessions(workspace))
    if session_id not in available:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    SessionManager.delete(workspace, session_id)
    AgentManager.drop_session(workspace, session_id)
    return {"status": "deleted", "session_id": session_id}


@app.post(f"{_service_prefix()}/chat/sessions/{{session_id}}/clone")
async def clone_session(session_id: str, body: AgentSessionCloneRequest) -> dict[str, Any]:
    workspace = _require_workspace(body.workspace)
    session_id = _require_session_id(session_id)
    target_id = _require_session_id(body.target_session_id)
    try:
        SessionManager.clone(workspace, session_id, target_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Source session {session_id!r} not found")
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"Target session {target_id!r} already exists")
    return {"status": "cloned", "source": session_id, "target": target_id}


@app.post(f"{_service_prefix()}/chat/send")
async def chat_send(body: AgentMessageRequest) -> dict[str, Any]:
    agent = _get_agent(body.workspace, body.session_id, body.api_key)
    try:
        reply = await agent.send(body.message)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Chat send failed: {exc}") from exc
    return _reply_to_dict(reply)


@app.post(f"{_service_prefix()}/chat/command")
async def chat_command(body: AgentCommandRequest) -> dict[str, Any]:
    agent = _get_agent(body.workspace, body.session_id, body.api_key)
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
    agent = _get_agent(body.workspace, body.session_id, body.api_key)

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


def _get_agent(workspace: str, session_id: str, api_key: str | None = None):
    workspace = _require_workspace(workspace)
    session_id = _require_session_id(session_id)
    return AgentManager.get_or_create(
        workspace=workspace,
        session_id=session_id,
        api_key=api_key,
    )


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
