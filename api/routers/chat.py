"""Chat routes — send messages to the RPG Agent and stream responses via SSE."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from rpg_world.rpg_core.agent import RPGGameAgent
from rpg_world.rpg_core.agent.agent_types import StreamEventKind
from rpg_world.rpg_core.settings import settings

from rpg_world.api.logger import chat_logger
from rpg_world.api.settings import api_settings
from rpg_world.rpg_core.agent.stats_formatter import format_event_stats, format_turn_stats

router = APIRouter(tags=["chat"])

# ── Agent instance cache (per-session + per-api-key) ─────────────────────

_agent_instances: dict[str, RPGGameAgent] = {}


def _cache_key(session_id: str, api_key: str | None) -> str:
    """Build a cache key from session_id and api_key.

    Including api_key in the key ensures that if a user changes their
    key, a new agent is created rather than reusing one with the old key.
    """
    return f"{session_id}::{api_key or ''}"


def _get_agent(
    session_id: str = "default",
    api_key: str | None = None,
) -> RPGGameAgent:
    """Get or create an RPGGameAgent for the given session.

    Agent instances are cached by session_id (+ api_key) to preserve
    in-memory conversation history and avoid re-initialization on each
    request.

    When *api_key* is provided it takes precedence over the environment
    variable ``OPENAI_API_KEY`` (the RPGGameAgent default fallback).
    """
    key = _cache_key(session_id, api_key)
    if key not in _agent_instances:
        agent = RPGGameAgent(
            session_id=session_id,
            model=settings.agent_model,
            api_key=api_key,
            base_url=settings.agent_base_url or None,
            max_tokens=settings.agent_max_tokens,
            temperature=settings.agent_temperature,
        )
        _agent_instances[key] = agent
    return _agent_instances[key]


# ── Routes ──────────────────────────────────────────────────────────────


@router.get("/chat/history")
async def get_chat_history(
    session_id: str = "default",
    x_openai_api_key: str | None = Header(None),
) -> dict:
    """Return the conversation history for the given session.

    The agent maintains history in-memory and persists to a JSONL file
    under the session's data directory.
    """
    agent = _get_agent(session_id, api_key=x_openai_api_key)
    try:
        await agent._ensure_initialized()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Agent initialization failed (api_key missing or invalid?): {exc}",
        )
    return {"history": agent.history}


@router.post("/chat/send")
async def chat_send(
    body: dict,
    x_openai_api_key: str | None = Header(None),
) -> dict:
    """Send a message and receive the full buffered reply.

    This is a thin wrapper around ``RPGGameAgent.send()``.  The primary
    WebUI uses the streaming endpoint instead; this endpoint exists for
    external integrations (Telegram bots, etc.) where streaming may not
    be convenient.
    """
    session_id = body.get("session_id", "default")
    message = body.get("message", "")

    # Log raw user input
    if api_settings.log_chat_messages:
        chat_logger.info("USER [%s]: %s", session_id, message)

    agent = _get_agent(session_id, api_key=x_openai_api_key)
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
    body: dict,
    x_openai_api_key: str | None = Header(None),
) -> dict:
    """Execute a slash command on the agent (not sent to LLM).

    Supported commands:
      - ``/clear`` — clear conversation history
      - ``/compact`` — compress old conversation rounds into summary
      - ``/reload`` — reload RPG context from disk
      - ``/context`` — show current context structure and token usage
    """
    session_id = body.get("session_id", "default")
    command: str = body.get("command", "").strip()

    if api_settings.log_chat_messages:
        chat_logger.info("CMD [%s]: %s", session_id, command)

    agent = _get_agent(session_id, api_key=x_openai_api_key)

    try:
        await agent._ensure_initialized()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Agent initialization failed: {exc}",
        )

    # 交由 agent 的 CommandDispatcher 执行，与 send() 逻辑一致
    cmd_result = await agent._cmd_dispatcher.dispatch(command)
    if cmd_result.handled:
        if api_settings.log_chat_messages:
            chat_logger.info("CMD REPLY [%s]: %s", session_id, cmd_result.reply)
        return {"reply": cmd_result.reply, "stats": cmd_result.stats}
    raise HTTPException(status_code=400, detail=f"未知命令: {command.split()[0] if command.strip() else '(empty)'}")


@router.post("/chat/stream")
async def chat_stream(
    body: dict,
    x_openai_api_key: str | None = Header(None),
) -> StreamingResponse:
    """Send a message and stream the response via Server-Sent Events.

    Each event is a ``data: {json}\n\n`` line.  See ``AgentStreamEvent.to_dict()``
    for the event payload structure.

    Event types:
      * ``text`` — incremental text content
      * ``thinking`` — reasoning/thinking content
      * ``tool_call`` — model initiated a tool call
      * ``tool_result`` — a tool execution completed
      * ``round_start`` — a new LLM round begins
      * ``done`` — stream complete, carries aggregated usage/duration/metadata
      * ``error`` — an error occurred during streaming
    """
    session_id = body.get("session_id", "default")
    message = body.get("message", "")
    agent = _get_agent(session_id, api_key=x_openai_api_key)

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
