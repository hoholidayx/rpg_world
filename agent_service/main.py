"""Agent service FastAPI app.

This process is the sole owner of ``AgentManager`` / ``RPGGameAgent`` runtime.
Other processes access it through ``agent_service.client.AgentClient``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, cast

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
    AgentMainLLMProviderCatalogPayload,
    AgentMainLLMProviderCatalogResponse,
    AgentMainLLMProviderOptionPayload,
    AgentMainLLMSelectionPayload,
    AgentMainLLMSelectionResponse,
    AgentMainLLMSessionUpdateRequest,
    AgentMainLLMStoryUpdateRequest,
    AgentMessageRequest,
    AgentPlayerCharacterBindPayload,
    AgentPlayerCharacterBindRequest,
    AgentPlayerCharacterBindResponse,
    AgentReplyPayload,
    AgentSessionCreatePayload,
    AgentSessionCreateRequest,
    AgentSessionCreateResponse,
    AgentSessionDeletePayload,
    AgentSessionDeleteResponse,
    AgentSessionEnsureRequest,
    AgentSessionMutationRequest,
    AgentSessionOverviewPayload,
    AgentSessionOverviewResponse,
    AgentSessionPayload,
    AgentSessionPayloadDict,
    AgentSessionsPayload,
    AgentSessionsResponse,
    AgentStatsPayload,
    AgentStopRequest,
    AgentTurnCancelResponse,
)
from agent_service.settings import settings as process_settings
from commons.errors import (
    LLM_SERVICE_UNAVAILABLE_ERROR_CODE,
    LLM_SERVICE_UNAVAILABLE_STATUS_CODE,
    MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE,
    MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE,
    TURN_METADATA_INVALID_ERROR_CODE,
    TURN_METADATA_INVALID_STATUS_CODE,
    MainContextWindowThresholdExceededError,
    format_turn_metadata_error_message,
)
from commons.types import JsonObject, JsonValue
from llm_client.manager import LLMClientManager
from llm_client.client import LLMServiceClientError
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind, TurnStats
from rpg_core.context.usage import ContextPreviewUsagePayload, TurnUsageWirePayload, usage_payload_from_records
from rpg_core.agent.command import CommandResult
from rpg_core.agent.loop import AgentReply
from rpg_core.agent.manager import AgentManager, SessionDeletionInProgressError
from rpg_core.main_llm import (
    InvalidMainLLMProviderKey,
    MainLLMProviderCatalog,
    MainLLMSelection,
    MainLLMSelectionService,
)
from rpg_core.session import InvalidTurnMetadataError, SessionManager, validate_turn_metadata
from rpg_data import models
from rpg_data.services import get_data_service_gateway


def _service_prefix() -> str:
    return process_settings.service.api_prefix


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = process_settings.llm_client
    await LLMClientManager.aconfigure(
        base_url=cfg.base_url,
        token=cfg.token,
        request_timeout_ms=cfg.request_timeout_ms,
        stream_timeout_ms=cfg.stream_timeout_ms,
    )
    try:
        yield
    finally:
        await AgentManager.areset()
        await LLMClientManager.areset()


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
    try:
        payload = await LLMClientManager.get().client.health()
        llm_status = "ok" if payload.get("status") == "ok" else "degraded"
    except Exception:
        llm_status = "unavailable"
    return AgentHealthResponse(
        status="ok" if llm_status == "ok" else "degraded",
        llm_service=llm_status,
    )


@app.get(f"{_service_prefix()}/chat/history", response_model=AgentHistoryResponse)
async def get_history(
    session_id: str = Query(...),
) -> AgentHistoryPayload:
    agent = _get_agent(session_id)
    try:
        await agent.initialize()
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
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
        await agent.initialize()
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
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
    mode: str | None = Query(default=None),
    narrative_style_id: int | None = Query(default=None, gt=0),
) -> AgentContextPreviewResponse:
    agent = _get_agent(session_id)
    try:
        if mode is None and narrative_style_id is None:
            payload = await agent.get_context_payload()
        else:
            payload = await agent.get_context_payload(
                mode=mode,
                narrative_style_id=narrative_style_id,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Context preview failed: {exc}") from exc
    _log_context_preview_payload(body_session_id=session_id, payload=payload)
    return AgentContextPreviewResponse.model_validate(payload)


@app.get(
    f"{_service_prefix()}/chat/main-llm/options",
    response_model=AgentMainLLMProviderCatalogResponse,
)
async def get_main_llm_options() -> AgentMainLLMProviderCatalogPayload:
    try:
        return _main_llm_catalog_payload(
            await _main_llm_selection_service().get_provider_catalog()
        )
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc


@app.get(
    f"{_service_prefix()}/chat/main-llm/story",
    response_model=AgentMainLLMSelectionResponse,
)
async def get_story_main_llm(
    workspace_id: str = Query(...),
    story_id: int = Query(...),
) -> AgentMainLLMSelectionPayload:
    workspace_id = _require_workspace(workspace_id)
    try:
        selection = await _main_llm_selection_service().resolve_story(
            workspace_id,
            story_id,
        )
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
    if selection is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _main_llm_selection_payload(selection)


@app.post(
    f"{_service_prefix()}/chat/main-llm/story",
    response_model=AgentMainLLMSelectionResponse,
)
async def set_story_main_llm(
    body: AgentMainLLMStoryUpdateRequest,
) -> AgentMainLLMSelectionPayload:
    workspace_id = _require_workspace(body.workspace_id)
    try:
        selection = await _main_llm_selection_service().set_story_provider_key(
            workspace_id,
            body.story_id,
            body.provider_key,
        )
    except InvalidMainLLMProviderKey as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
    if selection is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _main_llm_selection_payload(selection)


@app.get(
    f"{_service_prefix()}/chat/main-llm/session",
    response_model=AgentMainLLMSelectionResponse,
)
async def get_session_main_llm(
    session_id: str = Query(...),
) -> AgentMainLLMSelectionPayload:
    session_id = _require_session_id(session_id)
    try:
        selection = await _main_llm_selection_service().resolve_session(session_id)
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
    if selection is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _main_llm_selection_payload(selection)


@app.post(
    f"{_service_prefix()}/chat/main-llm/session",
    response_model=AgentMainLLMSelectionResponse,
)
async def set_session_main_llm(
    body: AgentMainLLMSessionUpdateRequest,
) -> AgentMainLLMSelectionPayload:
    try:
        selection = await _main_llm_selection_service().set_session_provider_key(
            body.session_id,
            body.provider_key,
        )
    except InvalidMainLLMProviderKey as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
    if selection is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _main_llm_selection_payload(selection)


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
        "sessions": [
            {"session_id": str(session.id), "title": str(session.title or "")}
            for session in sessions
        ],
    }


@app.get(
    f"{_service_prefix()}/chat/session/overview",
    response_model=AgentSessionOverviewResponse,
)
async def get_session_overview(
    session_id: str = Query(...),
) -> AgentSessionOverviewPayload:
    session_id = _require_session_id(session_id)
    gateway = get_data_service_gateway()
    session = gateway.catalog.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    story = gateway.catalog.get_session_story(session_id)
    if story is None:
        raise HTTPException(status_code=404, detail=f"Story for session {session_id!r} not found")
    workspace = next(
        (item for item in gateway.catalog.list_workspaces() if item.id == session.workspace_id),
        None,
    )
    state = gateway.session_roles.get_state(session_id)
    options = gateway.session_roles.list_options(session_id)
    player = state.player
    player_status: Literal["bound", "invalid"] = (
        "bound"
        if state.status == models.PLAYER_CHARACTER_STATUS_BOUND
        else "invalid"
    )
    return {
        "workspace_id": str(session.workspace_id),
        "workspace_title": str(workspace.name if workspace is not None else session.workspace_id),
        "story_id": int(story.id),
        "story_title": str(story.title or ""),
        "session_id": str(session.id),
        "session_title": str(session.title or ""),
        "player_character_status": player_status,
        "player_character": (
            {"character_id": int(player.character_id), "name": str(player.name)}
            if player is not None
            else None
        ),
        "role_options": [
            {
                "character_id": int(option.snapshot.character_id),
                "name": str(option.snapshot.name),
            }
            for option in options
        ],
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
        if body.mode == "ic" and body.narrative_style_id is None:
            reply = await agent.send(body.message)
        else:
            reply = await agent.send(
                body.message,
                mode=body.mode,
                narrative_style_id=body.narrative_style_id,
            )
    except MainContextWindowThresholdExceededError as exc:
        raise _main_context_threshold_http_error(exc) from exc
    except InvalidTurnMetadataError as exc:
        raise _turn_metadata_http_error(exc) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Chat send failed: {exc}") from exc
    return _reply_to_dict(reply, session_id=body.session_id)


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
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"History reload failed: {exc}") from exc
    return {"status": "reloaded", "session_id": body.session_id}


@app.delete(
    f"{_service_prefix()}/chat/session",
    response_model=AgentSessionDeleteResponse,
)
async def delete_session(
    session_id: str = Query(...),
) -> AgentSessionDeletePayload:
    normalized_session_id = _require_session_id(session_id)
    gateway = get_data_service_gateway()
    if gateway.catalog.get_session(normalized_session_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {normalized_session_id!r} not found",
        )

    try:
        await AgentManager.begin_session_deletion(normalized_session_id)
    except SessionDeletionInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "[AgentService] failed to close session runtime before deletion: session_id={}",
            normalized_session_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Session runtime close failed: {exc}",
        ) from exc

    try:
        result = gateway.session_deletion.delete(normalized_session_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {normalized_session_id!r} not found",
            )
        logger.info(
            "[AgentService] deleted session: session_id={}, runtime_cleanup={}",
            normalized_session_id,
            result.runtime_cleanup,
        )
        return {
            "status": "deleted",
            "session_id": normalized_session_id,
            "runtime_cleanup": result.runtime_cleanup,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "[AgentService] session deletion failed: session_id={}",
            normalized_session_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Session deletion failed: {exc}",
        ) from exc
    finally:
        AgentManager.finish_session_deletion(normalized_session_id)


@app.post(
    f"{_service_prefix()}/chat/session/player-character",
    response_model=AgentPlayerCharacterBindResponse,
)
async def bind_player_character(
    body: AgentPlayerCharacterBindRequest,
) -> AgentPlayerCharacterBindPayload:
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
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
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
    bind_result = result.role_bind_result
    player = bind_result.state.player if bind_result is not None else None
    if player is None:
        raise HTTPException(status_code=400, detail="Player character bind returned no typed player state")
    return {
        "status": "bound",
        "session_id": body.session_id,
        "player_character_id": int(body.player_character_id),
        "player_character": {
            "character_id": int(player.character_id),
            "name": str(player.name),
        },
        "first_message": str(bind_result.first_message or ""),
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
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
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
        await AgentManager.drop_session(body.session_id)
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
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
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
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Command failed: {exc}") from exc
    if not result.handled:
        raise HTTPException(
            status_code=400,
            detail=f"未知命令: {command.split()[0] if command else '(empty)'}",
        )
    data = _command_result_to_dict(result)
    data["active_session"] = agent.session_id
    return data


@app.post(f"{_service_prefix()}/chat/stream")
async def chat_stream(body: AgentMessageRequest) -> StreamingResponse:
    agent = _get_agent(body.session_id)

    async def event_generator() -> AsyncIterator[str]:
        try:
            stream_events = (
                agent.send_stream(body.message, request_id=body.request_id)
                if body.mode == "ic" and body.narrative_style_id is None
                else agent.send_stream(
                    body.message,
                    request_id=body.request_id,
                    mode=body.mode,
                    narrative_style_id=body.narrative_style_id,
                )
            )
            async for event in stream_events:
                yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
        except MainContextWindowThresholdExceededError as exc:
            event = _main_context_threshold_stream_error(exc)
            yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
        except InvalidTurnMetadataError as exc:
            event = _turn_metadata_stream_error(exc)
            yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
        except LLMServiceClientError as exc:
            event = AgentStreamEvent(
                kind=StreamEventKind.ERROR,
                content=str(exc),
                error_code=LLM_SERVICE_UNAVAILABLE_ERROR_CODE,
                status_code=LLM_SERVICE_UNAVAILABLE_STATUS_CODE,
            )
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


@app.post(f"{_service_prefix()}/chat/stop", response_model=AgentTurnCancelResponse)
async def chat_stop(body: AgentStopRequest) -> AgentTurnCancelResponse:
    agent = _get_agent(body.session_id)
    result = await agent.cancel_current_turn(request_id=body.request_id)
    return AgentTurnCancelResponse.model_validate(result.to_dict())


def _get_agent(session_id: str):
    session_id = _require_session_id(session_id)
    if get_data_service_gateway().catalog.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    try:
        return AgentManager.get_or_create(session_id=session_id)
    except SessionDeletionInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
    except LLMServiceClientError as exc:
        raise _llm_dependency_http_error(exc) from exc
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


def _main_llm_option_payload(option) -> AgentMainLLMProviderOptionPayload:  # noqa: ANN001
    return {
        "provider_key": option.provider_key,
        "backend": option.backend,
        "model": option.model,
        "context_window": option.context_window,
    }


def _main_llm_selection_service() -> MainLLMSelectionService:
    return MainLLMSelectionService(get_data_service_gateway())


def _main_llm_catalog_payload(
    catalog: MainLLMProviderCatalog,
) -> AgentMainLLMProviderCatalogPayload:
    return {
        "config_default_provider_key": catalog.config_default_provider_key,
        "options": [_main_llm_option_payload(option) for option in catalog.options],
    }


def _main_llm_selection_payload(
    selection: MainLLMSelection,
) -> AgentMainLLMSelectionPayload:
    return {
        "config_default_provider_key": selection.config_default_provider_key,
        "story_provider_key": selection.story_provider_key,
        "session_provider_key": selection.session_provider_key,
        "effective_provider_key": selection.effective_provider_key,
        "effective_source": selection.effective_source,
        "effective": _main_llm_option_payload(selection.effective),
        "invalid_overrides": [
            {"source": item.source, "provider_key": item.provider_key}
            for item in selection.invalid_overrides
        ],
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
    return HTTPException(status_code=TURN_METADATA_INVALID_STATUS_CODE, detail=str(exc))


def _llm_dependency_http_error(exc: LLMServiceClientError) -> HTTPException:
    return HTTPException(
        status_code=LLM_SERVICE_UNAVAILABLE_STATUS_CODE,
        detail={
            "error_code": LLM_SERVICE_UNAVAILABLE_ERROR_CODE,
            "message": str(exc),
        },
    )


def _main_context_threshold_http_error(
    exc: MainContextWindowThresholdExceededError,
) -> HTTPException:
    return HTTPException(
        status_code=MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE,
        detail=str(exc),
    )


def _main_context_threshold_stream_error(
    exc: MainContextWindowThresholdExceededError,
) -> AgentStreamEvent:
    return AgentStreamEvent(
        kind=StreamEventKind.ERROR,
        content=str(exc),
        error_code=MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE,
        status_code=MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE,
    )


def _turn_metadata_stream_error(exc: InvalidTurnMetadataError) -> AgentStreamEvent:
    return AgentStreamEvent(
        kind=StreamEventKind.ERROR,
        content=format_turn_metadata_error_message(exc),
        error_code=TURN_METADATA_INVALID_ERROR_CODE,
        status_code=TURN_METADATA_INVALID_STATUS_CODE,
    )


def _reply_to_dict(reply: AgentReply, *, session_id: str = "-") -> AgentReplyPayload:
    result: AgentReplyPayload = {"reply": reply.text}
    if reply.committed_turn_id is not None:
        if reply.committed_turn_id <= 0:
            raise ValueError("committed_turn_id must be a positive integer")
        result["committed_turn_id"] = int(reply.committed_turn_id)
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
        usage = usage_payload_from_records(reply.stats.calls, duration_ms=reply.stats.total_duration_ms)
        if usage is not None:
            result["usage"] = cast(JsonObject, usage)
            usage_view = TurnUsageWirePayload.from_payload(usage)
            logger.debug(
                "[AgentService] send usage attached: session_id={}, prompt={}, completion={}, total={}, cached={}, call_count={}",
                session_id,
                usage_view.prompt_tokens if usage_view else None,
                usage_view.completion_tokens if usage_view else None,
                usage_view.total_tokens if usage_view else None,
                usage_view.cached_tokens if usage_view else None,
                len(reply.stats.calls),
            )
        elif reply.stats.calls:
            logger.warning(
                "[AgentService] send completed without provider usage: session_id={}, call_count={}, duration_ms={:.1f}",
                session_id,
                len(reply.stats.calls),
                reply.stats.total_duration_ms,
            )
        else:
            logger.debug("[AgentService] send completed with no LLM calls: session_id={}", session_id)
    return result


def _log_context_preview_payload(*, body_session_id: str, payload: dict[str, object]) -> None:
    usage = ContextPreviewUsagePayload.from_payload(payload)
    if usage is None:
        logger.warning("[AgentService] context preview missing usageEstimate: session_id={}", body_session_id)
        return
    logger.debug(
        "[AgentService] context preview usage estimate: session_id={}, used_tokens={}, context_limit={}, source={}, accuracy={}, token_count={}",
        body_session_id,
        usage.used_tokens,
        usage.context_limit,
        usage.source,
        usage.accuracy,
        usage.token_count,
    )


def _message_payload(row: models.SessionMessage) -> JsonObject:
    payload: dict[str, JsonValue] = {
        "messageId": int(row.id),
        "turnId": int(row.turn_id),
        "seqInTurn": int(row.seq_in_turn),
        "role": str(row.role),
        "content": str(row.content or ""),
        "mode": str(row.mode or models.TURN_MODE_IC),
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
