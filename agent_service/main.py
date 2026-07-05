"""Agent service FastAPI app.

This process is the sole owner of ``AgentManager`` / ``RPGGameAgent`` runtime.
Other processes access it through ``agent_service.client.AgentClient``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger

from agent_service.schemas import (
    AgentCommandRequest,
    AgentCommandResultPayload,
    AgentCommandsPayload,
    AgentCommandsResponse,
    AgentContextPreviewResponse,
    AgentHistoryPayload,
    AgentHistoryResponse,
    AgentHealthResponse,
    AgentMessageRequest,
    AgentPlayerCharacterBindRequest,
    AgentReplyPayload,
    AgentSessionCreatePayload,
    AgentSessionCreateRequest,
    AgentSessionCreateResponse,
    AgentSessionEnsureRequest,
    AgentSessionMutationRequest,
    AgentSessionPayload,
    AgentSessionPayloadDict,
    AgentSessionsPayload,
    AgentSessionsResponse,
    AgentStatsPayload,
)
from agent_service.settings import settings as process_settings
from commons.types import JsonObject, JsonValue
from llm_service.client import configure_llama_client_from_runtime_config
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind, TurnStats
from rpg_core.agent.command import CommandResult
from rpg_core.agent.loop import AgentReply
from rpg_core.agent.manager import AgentManager
from rpg_core.session import InvalidTurnMetadataError, SessionManager, validate_turn_metadata
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


@app.get(f"{_service_prefix()}/chat/history", response_model=AgentHistoryResponse)
async def get_history(
    session_id: str = Query(...),
) -> AgentHistoryPayload:
    agent = _get_agent(session_id)
    try:
        await agent._ensure_initialized()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Agent initialization failed: {exc}") from exc
    rows = get_data_service_gateway().messages.list(session_id)
    try:
        validate_turn_metadata(rows, label="history")
    except InvalidTurnMetadataError as exc:
        raise _turn_metadata_http_error(exc) from exc
    return {"history": [_message_payload(row) for row in rows]}


@app.get(f"{_service_prefix()}/chat/commands", response_model=AgentCommandsResponse)
async def list_commands(
    session_id: str = Query(...),
) -> AgentCommandsPayload:
    agent = _get_agent(session_id)
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


@app.get(f"{_service_prefix()}/chat/context-preview", response_model=AgentContextPreviewResponse)
async def get_context_preview(
    session_id: str = Query(...),
) -> AgentContextPreviewResponse:
    agent = _get_agent(session_id)
    try:
        payload = await agent.get_context_payload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Context preview failed: {exc}") from exc
    return AgentContextPreviewResponse.model_validate(payload)


@app.get(f"{_service_prefix()}/chat/sessions", response_model=AgentSessionsResponse)
async def list_sessions(
    workspace_id: str = Query(...),
    story_id: int = Query(...),
) -> AgentSessionsPayload:
    workspace_id = _require_workspace(workspace_id)
    sessions = get_data_service_gateway().catalog.list_sessions(workspace_id, story_id)
    if sessions is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return {
        "sessions": [str(session.id) for session in sessions],
    }


@app.post(f"{_service_prefix()}/chat/sessions", response_model=AgentSessionCreateResponse)
async def create_session(body: AgentSessionCreateRequest) -> AgentSessionCreatePayload:
    session = _create_catalog_session(
        body.workspace_id,
        int(body.story_id),
        title=str(body.title or ""),
    )
    await _bind_session_player_character_if_present(session.id, body.player_character_id)
    return {"status": "created", **_session_payload(session)}


@app.post(f"{_service_prefix()}/chat/session/ensure", response_model=AgentSessionPayload)
async def ensure_session(body: AgentSessionEnsureRequest) -> AgentSessionPayloadDict:
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

    await _bind_session_player_character_if_present(session.id, body.player_character_id)
    return _session_payload(session)


@app.post(f"{_service_prefix()}/chat/send")
async def chat_send(body: AgentMessageRequest) -> AgentReplyPayload:
    agent = _get_agent(body.session_id)
    try:
        reply = await agent.send(body.message)
    except InvalidTurnMetadataError as exc:
        raise _turn_metadata_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Chat send failed: {exc}") from exc
    return _reply_to_dict(reply)


@app.post(f"{_service_prefix()}/chat/session/reload-history")
async def reload_history(body: AgentSessionMutationRequest) -> JsonObject:
    agent = _get_agent(body.session_id)
    try:
        await agent.reload_history()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTurnMetadataError as exc:
        raise _turn_metadata_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"History reload failed: {exc}") from exc
    return {"status": "reloaded", "session_id": body.session_id}


@app.post(f"{_service_prefix()}/chat/session/player-character")
async def bind_player_character(body: AgentPlayerCharacterBindRequest) -> JsonObject:
    logger.info(
        "[AgentService] player character bind requested: session_id={}, character_id={}",
        body.session_id,
        body.player_character_id,
    )
    try:
        result = await _bind_agent_player_character(body.session_id, body.player_character_id)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning(
            "[AgentService] player character bind rejected: session_id={}, character_id={}, error={}",
            body.session_id,
            body.player_character_id,
            exc,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "[AgentService] player character bind failed: session_id={}, character_id={}",
            body.session_id,
            body.player_character_id,
        )
        raise HTTPException(status_code=400, detail=f"Player character bind failed: {exc}") from exc
    return {
        "status": "bound",
        "session_id": body.session_id,
        "player_character_id": int(body.player_character_id),
        "reply": result.reply,
    }


@app.post(f"{_service_prefix()}/chat/session/turns/{{turn_id}}/truncate")
async def truncate_history(turn_id: int, body: AgentSessionMutationRequest) -> JsonObject:
    agent = _get_agent(body.session_id)
    try:
        result = await agent.truncate_history_from_turn(turn_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTurnMetadataError as exc:
        raise _turn_metadata_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"History truncate failed: {exc}") from exc

    logger.info(
        "[AgentService] history truncate result: session_id={}, turn_id={}, removed={}, sync_status={}",
        body.session_id,
        turn_id,
        result.get("removed"),
        result.get("agent_sync_status"),
    )
    if result.get("agent_sync_status") != "synced":
        logger.warning(
            "[AgentService] dropping cached agent after truncate sync issue: session_id={}, turn_id={}, sync_status={}",
            body.session_id,
            turn_id,
            result.get("agent_sync_status"),
        )
        AgentManager.drop_session(body.session_id)
    return result


@app.delete(f"{_service_prefix()}/chat/messages/{{message_id}}")
async def delete_message(
    message_id: int,
    session_id: str = Query(...),
) -> JsonObject:
    agent = _get_agent(session_id)
    try:
        deleted = await agent.delete_message(message_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTurnMetadataError as exc:
        raise _turn_metadata_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Message delete failed: {exc}") from exc
    return {
        "status": "deleted",
        "message_id": deleted.uid,
        "turn_id": deleted.turn_id,
    }


@app.post(f"{_service_prefix()}/chat/command")
async def chat_command(body: AgentCommandRequest) -> AgentCommandResultPayload:
    agent = _get_agent(body.session_id)
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
    agent = _get_agent(body.session_id)

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


def _get_agent(session_id: str):
    session_id = _require_session_id(session_id)
    if get_data_service_gateway().catalog.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return AgentManager.get_or_create(session_id=session_id)


def _create_catalog_session(workspace_id: str, story_id: int, *, title: str) -> models.Session:
    workspace_id = _require_workspace(workspace_id)
    session = get_data_service_gateway().catalog.create_session(workspace_id, story_id, title=title)
    if session is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return session


async def _bind_session_player_character_if_present(session_id: str, player_character_id: int | None) -> None:
    if player_character_id is None:
        logger.debug("[AgentService] skip optional player character bind: session_id={}", session_id)
        return
    logger.info(
        "[AgentService] optional player character bind requested: session_id={}, character_id={}",
        session_id,
        player_character_id,
    )
    try:
        await _bind_agent_player_character(session_id, int(player_character_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _bind_agent_player_character(session_id: str, player_character_id: int) -> CommandResult:
    session_id = _require_session_id(session_id)
    character_id = int(player_character_id)
    command = _role_bind_command_for_character_id(session_id, character_id)
    logger.debug(
        "[AgentService] resolved player character bind command: session_id={}, character_id={}, command={}",
        session_id,
        character_id,
        command,
    )
    agent = _get_agent(session_id)
    result = await agent.execute_command(command)
    if not result.handled:
        logger.error(
            "[AgentService] role bind command not handled: session_id={}, character_id={}, command={}, reply={}",
            session_id,
            character_id,
            command,
            result.reply,
        )
        raise ValueError(f"role bind command was not handled: {command}")

    state = get_data_service_gateway().session_roles.get_state(session_id)
    if (
        state.status != models.PLAYER_CHARACTER_STATUS_BOUND
        or state.player is None
        or int(state.player.character_id) != character_id
    ):
        logger.error(
            "[AgentService] player character bind post-check failed: session_id={}, requested_character_id={}, status={}, bound_character_id={}, reply={}",
            session_id,
            character_id,
            state.status,
            getattr(state.player, "character_id", None),
            result.reply,
        )
        raise ValueError(result.reply or f"player character binding failed: {character_id}")
    logger.info(
        "[AgentService] player character bound via command: session_id={}, character_id={}, command={}, reply_chars={}",
        session_id,
        character_id,
        command,
        len(result.reply or ""),
    )
    return result


def _role_bind_command_for_character_id(session_id: str, player_character_id: int) -> str:
    options = get_data_service_gateway().session_roles.list_options(session_id)
    logger.debug(
        "[AgentService] resolving role bind index: session_id={}, character_id={}, option_count={}",
        session_id,
        player_character_id,
        len(options),
    )
    for index, option in enumerate(options, start=1):
        if int(option.snapshot.character_id) == int(player_character_id):
            return f"/role_bind {index}"
    logger.warning(
        "[AgentService] role bind index not found: session_id={}, character_id={}, option_count={}",
        session_id,
        player_character_id,
        len(options),
    )
    raise ValueError(f"player character is not mounted to this session story: {int(player_character_id)}")


def _session_payload(session: models.Session) -> AgentSessionPayloadDict:
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


def _turn_metadata_http_error(exc: InvalidTurnMetadataError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def _reply_to_dict(reply: AgentReply) -> AgentReplyPayload:
    result: AgentReplyPayload = {"reply": reply.text}
    if reply.tool_records:
        result["tool_records"] = [
            {
                "tool_calls": _json_value(r.assistant_message.get("tool_calls", [])),
                "tool_results": cast(list[JsonObject], r.tool_results),
                "reasoning_content": r.reasoning_content,
            }
            for r in reply.tool_records
        ]
    if reply.status_sub_agent_records:
        result["status_sub_agent_records"] = cast(list[JsonObject], reply.status_sub_agent_records)
    if reply.stats:
        result["stats"] = _stats_to_dict(reply.stats)
    return result


def _message_payload(row: models.SessionMessage) -> JsonObject:
    payload: dict[str, JsonValue] = {
        "messageId": int(row.id),
        "turnId": int(row.turn_id),
        "seqInTurn": int(row.seq_in_turn),
        "role": str(row.role),
        "content": str(row.content or ""),
        "metadata": _metadata_from_json(row.metadata_json),
    }
    if row.created_at:
        payload["createdAt"] = str(row.created_at)
    if row.tool_call_id:
        payload["toolCallId"] = str(row.tool_call_id)
    if row.tool_calls_json:
        payload["toolCalls"] = _json_value(_json_from_text(row.tool_calls_json, fallback=[]))

    # Backward-friendly aliases for lower-level clients that still expect raw
    # Message.to_dict()-style fields.
    payload["uid"] = int(row.id)
    payload["turn_id"] = int(row.turn_id)
    payload["seq_in_turn"] = int(row.seq_in_turn)
    return cast(JsonObject, payload)


def _metadata_from_json(raw: str) -> JsonObject:
    try:
        payload: object = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return cast(JsonObject, payload) if isinstance(payload, dict) else {}


def _json_from_text(raw: str, *, fallback: object) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _command_result_to_dict(result: CommandResult) -> AgentCommandResultPayload:
    payload: AgentCommandResultPayload = {"reply": result.reply, "handled": result.handled}
    if result.stats is not None:
        payload["stats"] = cast(JsonObject, dict(result.stats))
    return payload


def _stats_to_dict(stats: TurnStats) -> AgentStatsPayload:
    return {
        "total_duration_ms": stats.total_duration_ms,
        "total_prompt_tokens": stats.total_prompt_tokens,
        "total_completion_tokens": stats.total_completion_tokens,
        "total_tokens": stats.total_tokens,
        "total_cached_tokens": stats.total_cached_tokens,
        "call_count": len(stats.calls),
    }


def _json_value(value: object) -> JsonValue:
    return cast(JsonValue, value)
