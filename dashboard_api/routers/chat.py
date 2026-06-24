"""Chat routes — send messages to the RPG Agent and stream responses via SSE."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from agent_service.client import AgentClient, AgentClientError
from dashboard_api.schemas import ChatCommandBody, ChatMessageBody
from rpg_core.agent.agent_types import StreamEventKind
from rpg_core.utils.path_utils import (
    ensure_workspace_dir,
    resolve_api_workspace,
)
from rpg_core.utils.path_utils import PACKAGE_ROOT as _PACKAGE_ROOT

from dashboard_api.deps import DEFAULT_SESSION_ID
from dashboard_api.logger import chat_logger
from dashboard_api.settings import api_settings
from rpg_core.utils.stats_formatter import format_event_stats

router = APIRouter(tags=["chat"])
_agent_client: AgentClient | None = None


def _resolve_workspace(workspace: str = "") -> str:
    workspace = resolve_api_workspace(workspace)
    ensure_workspace_dir(_PACKAGE_ROOT, workspace)
    return workspace


def _get_agent_client() -> AgentClient:
    global _agent_client
    if _agent_client is None:
        _agent_client = AgentClient()
    return _agent_client


# ── Routes ──────────────────────────────────────────────────────────────


@router.get("/chat/history")
async def get_chat_history(
    workspace: str = "",
    session_id: str = DEFAULT_SESSION_ID,
    x_openai_api_key: str | None = Header(None),
) -> dict:
    """Return the conversation history for the given session.

    The agent maintains history in-memory and persists to a JSONL file
    under the session's data directory.
    """
    try:
        return await _get_agent_client().get_history(
            _resolve_workspace(workspace),
            session_id,
            api_key=x_openai_api_key,
        )
    except AgentClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/chat/send")
async def chat_send(
    body: ChatMessageBody,
    workspace: str = "",
    x_openai_api_key: str | None = Header(None),
) -> dict:
    """Send a message and receive the full buffered reply."""
    session_id = body.session_id
    message = body.message

    if api_settings.log_chat_messages:
        chat_logger.info("USER [%s][%s]: %s", workspace, session_id, message)

    try:
        result = await _get_agent_client().send(
            _resolve_workspace(workspace),
            session_id,
            message,
            api_key=x_openai_api_key,
        )
    except AgentClientError as exc:
        chat_logger.error("SEND ERROR [%s]: %s", session_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if api_settings.log_chat_messages:
        chat_logger.info("ASSISTANT [%s]: %s", session_id, result.get("reply", ""))
    return result


@router.post("/chat/command")
async def chat_command(
    body: ChatCommandBody,
    workspace: str = "",
    x_openai_api_key: str | None = Header(None),
) -> dict:
    """Execute a slash command on the agent (not sent to LLM)."""
    session_id = body.session_id
    command: str = body.command.strip()

    if api_settings.log_chat_messages:
        chat_logger.info("CMD [%s][%s]: %s", workspace, session_id, command)

    try:
        result = await _get_agent_client().execute_command(
            _resolve_workspace(workspace),
            session_id,
            command,
            api_key=x_openai_api_key,
        )
    except AgentClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("handled", True):
        if api_settings.log_chat_messages:
            chat_logger.info("CMD REPLY [%s]: %s", session_id, result.get("reply", ""))
        return result
    raise HTTPException(status_code=400, detail=f"未知命令: {command.split()[0] if command.strip() else '(empty)'}")


@router.get("/chat/commands")
async def list_commands(
    workspace: str = "",
    session_id: str = DEFAULT_SESSION_ID,
    x_openai_api_key: str | None = Header(None),
) -> dict:
    """返回所有可用的斜杠命令定义（供前端动态渲染命令弹窗）。"""
    try:
        return await _get_agent_client().list_commands(
            _resolve_workspace(workspace),
            session_id,
            api_key=x_openai_api_key,
        )
    except AgentClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/chat/stream")
async def chat_stream(
    body: ChatMessageBody,
    workspace: str = "",
    x_openai_api_key: str | None = Header(None),
) -> StreamingResponse:
    """Send a message and stream the response via Server-Sent Events."""
    session_id = body.session_id
    message = body.message
    resolved_workspace = _resolve_workspace(workspace)
    client = _get_agent_client()

    async def event_generator():
        # Log raw user input
        if api_settings.log_chat_messages:
            chat_logger.info("USER [%s]: %s", session_id, message)

        try:
            async for event in client.stream(
                resolved_workspace,
                session_id,
                message,
                api_key=x_openai_api_key,
            ):
                yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"

                # Log on DONE
                if event.kind == StreamEventKind.DONE:
                    if api_settings.log_chat_messages:
                        chat_logger.info("ASSISTANT [%s]: %s", session_id, event.content)
                    if api_settings.log_llm_stats and event.usage:
                        chat_logger.info("LLM Stats [%s]:\n%s", session_id, format_event_stats(event))
        except AgentClientError as exc:
            chat_logger.error("STREAM ERROR [%s]: %s", session_id, exc)
            yield f"data: {json.dumps({'kind': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
