"""Chat routes — send messages to the RPG Agent and stream responses via SSE."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from rpg_world.api.schemas import ChatCommandBody, ChatMessageBody
from rpg_world.rpg_core.agent.agent_types import StreamEventKind
from rpg_world.rpg_core.agent.manager import AgentManager
from rpg_world.rpg_core.utils.path_utils import (
    ensure_workspace_dir,
    resolve_api_workspace,
)
from rpg_world.rpg_core.utils.path_utils import PACKAGE_ROOT as _PACKAGE_ROOT

from rpg_world.api.logger import chat_logger
from rpg_world.api.settings import api_settings
from rpg_world.rpg_core.utils.stats_formatter import format_event_stats, format_turn_stats

router = APIRouter(tags=["chat"])


def _get_agent(
    workspace: str = "",
    session_id: str = "default",
    api_key: str | None = None,
) -> "RPGGameAgent":
    """Get or create an RPGGameAgent via the shared AgentManager.

    Agent instances are managed by ``AgentManager`` (process-wide singleton),
    ensuring all modules (API / Telegram / CLI) share the same cache and
    FileWatcher.

    The cache key includes *workspace* so that the same session_id under
    different workspaces gets distinct agent instances.

    When *api_key* is provided it takes precedence over the environment
    variable ``OPENAI_API_KEY`` (the RPGGameAgent default fallback).

    When *workspace* is empty it defaults to ``"data/api_default_workspace"``,
    and the workspace directory is created automatically if missing.
    """
    workspace = resolve_api_workspace(workspace)
    ensure_workspace_dir(_PACKAGE_ROOT, workspace)
    return AgentManager.get_or_create(
        workspace=workspace, session_id=session_id, api_key=api_key
    )


# ── Routes ──────────────────────────────────────────────────────────────


@router.get("/chat/history")
async def get_chat_history(
    workspace: str = "",
    session_id: str = "default",
    x_openai_api_key: str | None = Header(None),
) -> dict:
    """Return the conversation history for the given session.

    The agent maintains history in-memory and persists to a JSONL file
    under the session's data directory.
    """
    agent = _get_agent(workspace, session_id, api_key=x_openai_api_key)
    try:
        await agent._ensure_initialized()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Agent initialization failed (api_key missing or invalid?): {exc}",
        )
    return {"history": [m.to_dict() for m in agent.history]}


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

    agent = _get_agent(workspace, session_id, api_key=x_openai_api_key)
    try:
        reply = await agent.send(message)
    except Exception as exc:
        chat_logger.error("SEND ERROR [%s]: %s", session_id, exc)
        raise HTTPException(
            status_code=400,
            detail=f"Chat send failed (api_key missing or invalid?): {exc}",
        )

    # Log raw output and stats
    if api_settings.log_chat_messages:
        chat_logger.info("ASSISTANT [%s]: %s", session_id, reply.text)
    if api_settings.log_llm_stats and reply.stats:
        chat_logger.info("LLM Stats [%s]:\n%s", session_id, format_turn_stats(reply.stats))

    result: dict = {"reply": reply.text}
    if reply.tool_records:
        result["tool_records"] = [
            {
                "tool_calls": r.assistant_message.get("tool_calls", []),
                "tool_results": r.tool_results,
                "reasoning_content": r.reasoning_content,
            }
            for r in reply.tool_records
        ]
    if reply.stats:
        result["stats"] = {
            "total_duration_ms": reply.stats.total_duration_ms,
            "total_prompt_tokens": reply.stats.total_prompt_tokens,
            "total_completion_tokens": reply.stats.total_completion_tokens,
            "total_tokens": reply.stats.total_tokens,
            "total_cached_tokens": reply.stats.total_cached_tokens,
            "call_count": len(reply.stats.calls),
        }
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

    agent = _get_agent(workspace, session_id, api_key=x_openai_api_key)

    try:
        await agent._ensure_initialized()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Agent initialization failed: {exc}",
        )

    # 交由 agent 的消息队列执行（与 send() 共享同一队列，避免竞态）
    cmd_result = await agent.execute_command(command)
    if cmd_result.handled:
        if api_settings.log_chat_messages:
            chat_logger.info("CMD REPLY [%s]: %s", session_id, cmd_result.reply)
        return {
            "reply": cmd_result.reply,
            "stats": cmd_result.stats,
            "active_session": getattr(agent, "_session_id", session_id),
        }
    raise HTTPException(status_code=400, detail=f"未知命令: {command.split()[0] if command.strip() else '(empty)'}")


@router.get("/chat/commands")
async def list_commands(
    workspace: str = "",
    session_id: str = "default",
    x_openai_api_key: str | None = Header(None),
) -> dict:
    """返回所有可用的斜杠命令定义（供前端动态渲染命令弹窗）。"""
    agent = _get_agent(workspace, session_id, api_key=x_openai_api_key)
    try:
        await agent._ensure_initialized()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Agent initialization failed: {exc}",
        )
    commands = agent.list_commands()
    return {
        "commands": [
            {"command": c.name, "description": c.description, "detail": c.detail}
            for c in commands
        ],
    }


@router.post("/chat/stream")
async def chat_stream(
    body: ChatMessageBody,
    workspace: str = "",
    x_openai_api_key: str | None = Header(None),
) -> StreamingResponse:
    """Send a message and stream the response via Server-Sent Events."""
    session_id = body.session_id
    message = body.message
    agent = _get_agent(workspace, session_id, api_key=x_openai_api_key)

    async def event_generator():
        # Log raw user input
        if api_settings.log_chat_messages:
            chat_logger.info("USER [%s]: %s", session_id, message)

        try:
            await agent._ensure_initialized()
            async for event in agent.send_stream(message):
                yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"

                # Log on DONE
                if event.kind == StreamEventKind.DONE:
                    if api_settings.log_chat_messages:
                        chat_logger.info("ASSISTANT [%s]: %s", session_id, event.content)
                    if api_settings.log_llm_stats and event.usage:
                        chat_logger.info("LLM Stats [%s]:\n%s", session_id, format_event_stats(event))
        except Exception as exc:
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
