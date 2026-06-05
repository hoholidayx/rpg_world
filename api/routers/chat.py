"""Chat routes — send messages to the RPG Agent and stream responses via SSE."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from rpg_world.rpg_core.agent import RPGGameAgent
from rpg_world.rpg_core.settings import settings

router = APIRouter(tags=["chat"])

# ── Agent instance cache (per-session) ───────────────────────────────────

_agent_instances: dict[str, RPGGameAgent] = {}


def _get_agent(session_id: str = "default") -> RPGGameAgent:
    """Get or create an RPGGameAgent for the given session.

    Agent instances are cached by session_id to preserve in-memory
    conversation history and avoid re-initialization on each request.
    """
    if session_id not in _agent_instances:
        agent = RPGGameAgent(
            session_id=session_id,
            model=settings.agent_model,
            base_url=settings.agent_base_url or None,
            max_tokens=settings.agent_max_tokens,
            temperature=settings.agent_temperature,
        )
        _agent_instances[session_id] = agent
    return _agent_instances[session_id]


# ── Routes ──────────────────────────────────────────────────────────────


@router.get("/chat/history")
async def get_chat_history(session_id: str = "default") -> dict:
    """Return the conversation history for the given session.

    The agent maintains history in-memory and persists to a JSONL file
    under the session's data directory.
    """
    agent = _get_agent(session_id)
    return {"history": agent.history}


@router.post("/chat/send")
async def chat_send(body: dict) -> dict:
    """Send a message and receive the full buffered reply.

    This is a thin wrapper around ``RPGGameAgent.send()``.  The primary
    WebUI uses the streaming endpoint instead; this endpoint exists for
    external integrations (Telegram bots, etc.) where streaming may not
    be convenient.
    """
    session_id = body.get("session_id", "default")
    message = body.get("message", "")
    agent = _get_agent(session_id)
    reply = await agent.send(message)

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


@router.post("/chat/stream")
async def chat_stream(body: dict) -> StreamingResponse:
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

    Usage (JavaScript / fetch):

    .. code-block:: javascript

        const response = await fetch('/api/v1/chat/stream', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: 'hello', session_id: 'default'}),
        });
        const reader = response.body.getReader();
        // read lines with reader.read(), parse "data: {json}" lines
    """
    session_id = body.get("session_id", "default")
    message = body.get("message", "")
    agent = _get_agent(session_id)

    async def event_generator():
        try:
            async for event in agent.send_stream(message):
                yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
        except Exception as exc:
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
