from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from llm_client.manager import LLMClientManager
from play_events import PlayEventPublisher
from play_events.auth import uses_default_play_event_token

from dream_service.contracts import AsyncDreamRepository, DreamProposalItemUpdate
from dream_service.notifications import DreamTerminalNotificationSink
from dream_service.play_event_notifications import DreamPlayEventSink
from dream_service.repository import (
    build_rpg_data_dream_repository,
)
from dream_service.runtime import DreamTaskManager
from dream_service.worker import DreamRepositoryWorker
from dream_service.schemas import (
    DreamHealthResponse,
    DreamMemoryListResponse,
    DreamMemoryResponse,
    DreamProposalCreateRequest,
    DreamProposalListResponse,
    DreamProposalResponse,
    DreamProposalUpdateRequest,
    memory_list_response,
    memory_response,
    proposal_response,
    proposal_list_response,
)
from dream_service.settings import settings
from rp_memory.dream.engine import DreamEngine
from rp_memory.dream.errors import (
    DreamActiveMemoryLimitError,
    DreamAlreadyRunningError,
    DreamEvidenceInvalidError,
    DreamProposalConflictError,
    DreamProposalStaleError,
    DreamProposalStateError,
)
from rp_memory.dream.model import LLMDreamModel
from rp_memory.dream.source import DreamSourceSelector
from rp_memory.dream.types import DreamDepth, DreamScope

logger = logging.getLogger("dream_service.main")


class DreamRuntime:
    def __init__(
        self,
        *,
        repository: AsyncDreamRepository,
        tasks: DreamTaskManager,
    ) -> None:
        self.repository = repository
        self.tasks = tasks

    @classmethod
    def create(
        cls,
        notification_sink: DreamTerminalNotificationSink | None = None,
    ) -> "DreamRuntime":
        repository = DreamRepositoryWorker(build_rpg_data_dream_repository)
        config = settings.engine
        engine = DreamEngine(
            model=LLMDreamModel(),
            selector=DreamSourceSelector(
                max_map_turns=config.max_map_turns,
                max_map_chars=config.max_map_chars,
            ),
            map_concurrency=config.map_concurrency,
            reduce_candidate_batch_size=config.reduce_candidate_batch_size,
        )
        return cls(
            repository=repository,
            tasks=DreamTaskManager(
                repository=repository,
                engine=engine,
                notification_sink=notification_sink,
            ),
        )

    async def close(self) -> None:
        await self.repository.close()


_runtime: DreamRuntime | None = None


def get_runtime() -> DreamRuntime:
    global _runtime
    if _runtime is None:
        _runtime = DreamRuntime.create()
    return _runtime


def set_runtime_for_tests(runtime: DreamRuntime | None) -> None:
    global _runtime
    _runtime = runtime


def _prefix() -> str:
    return settings.service.api_prefix


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runtime
    del app
    llm = settings.llm_client
    await LLMClientManager.aconfigure(
        base_url=llm.base_url,
        token=llm.token,
        request_timeout_ms=llm.request_timeout_ms,
        stream_timeout_ms=llm.stream_timeout_ms,
    )
    runtime: DreamRuntime | None = None
    event_publisher: PlayEventPublisher | None = None
    try:
        event_cfg = settings.play_events
        notification_sink = None
        if event_cfg.enabled:
            if uses_default_play_event_token(event_cfg.token_env):
                logger.warning(
                    "%s is not set; using the local Play event token fallback",
                    event_cfg.token_env,
                )
            event_publisher = PlayEventPublisher(
                endpoint_url=event_cfg.endpoint_url,
                token=event_cfg.token,
                timeout_ms=event_cfg.timeout_ms,
            )
            notification_sink = DreamPlayEventSink(event_publisher)
        if _runtime is None:
            _runtime = DreamRuntime.create(notification_sink)
        runtime = _runtime
        await runtime.repository.start()
        await runtime.tasks.start()
        yield
    finally:
        try:
            if runtime is not None:
                try:
                    await runtime.tasks.stop()
                finally:
                    await runtime.close()
        finally:
            if _runtime is runtime:
                _runtime = None
            try:
                if event_publisher is not None:
                    await event_publisher.close()
            finally:
                await LLMClientManager.areset()


app = FastAPI(title="RPG World Dream Service", lifespan=lifespan)


@app.get(f"{_prefix()}/health", response_model=DreamHealthResponse)
async def health() -> DreamHealthResponse:
    return DreamHealthResponse()


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/dream/proposals",
    response_model=DreamProposalResponse,
    status_code=202,
)
async def create_proposal(
    session_id: str,
    request: DreamProposalCreateRequest,
) -> DreamProposalResponse:
    try:
        proposal = await get_runtime().tasks.create_proposal(
            session_id,
            depth=DreamDepth(request.depth),
            scope=DreamScope(request.scope),
            recover_proposal_id=request.recover_proposal_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return proposal_response(proposal)


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/dream/proposals",
    response_model=DreamProposalListResponse,
)
async def list_proposals(session_id: str) -> DreamProposalListResponse:
    try:
        proposals = await get_runtime().repository.list_proposals(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return proposal_list_response(proposals)


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/dream/proposals/{{proposal_id}}",
    response_model=DreamProposalResponse,
)
async def get_proposal(
    session_id: str,
    proposal_id: str,
) -> DreamProposalResponse:
    try:
        proposal = await get_runtime().repository.get_proposal(session_id, proposal_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if proposal is None:
        raise _not_found("DREAM_PROPOSAL_NOT_FOUND", "Dream proposal not found")
    return proposal_response(proposal)


@app.patch(
    f"{_prefix()}/sessions/{{session_id}}/dream/proposals/{{proposal_id}}",
    response_model=DreamProposalResponse,
)
async def update_proposal(
    session_id: str,
    proposal_id: str,
    request: DreamProposalUpdateRequest,
) -> DreamProposalResponse:
    updates = tuple(
        DreamProposalItemUpdate(
            item_id=item.item_id,
            selected=item.selected,
            text=item.text,
            memory_kind=item.memory_kind,
            epistemic_status=item.epistemic_status,
            salience=item.salience,
        )
        for item in request.items
    )
    try:
        proposal = await get_runtime().repository.update_proposal_items(
            session_id,
            proposal_id,
            updates,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return proposal_response(proposal)


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/dream/proposals/{{proposal_id}}/apply",
    response_model=DreamProposalResponse,
)
async def apply_proposal(
    session_id: str,
    proposal_id: str,
) -> DreamProposalResponse:
    try:
        proposal = await get_runtime().repository.apply_proposal(session_id, proposal_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return proposal_response(proposal)


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/dream/proposals/{{proposal_id}}/reject",
    response_model=DreamProposalResponse,
)
async def reject_proposal(
    session_id: str,
    proposal_id: str,
) -> DreamProposalResponse:
    try:
        proposal = await get_runtime().repository.reject_proposal(session_id, proposal_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return proposal_response(proposal)


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/dream/memories",
    response_model=DreamMemoryListResponse,
)
async def list_memories(
    session_id: str,
    lifecycle: str | None = Query(default=None),
) -> DreamMemoryListResponse:
    try:
        result = await get_runtime().repository.list_memories(
            session_id,
            lifecycle=lifecycle,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return memory_list_response(result)


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/dream/memories/{{memory_id}}/restore",
    response_model=DreamMemoryResponse,
)
async def restore_memory(
    session_id: str,
    memory_id: str,
) -> DreamMemoryResponse:
    try:
        result = await get_runtime().repository.restore_memory(session_id, memory_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return memory_response(result)


def _not_found(error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"errorCode": error_code, "message": message},
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return _not_found("DREAM_NOT_FOUND", str(exc))
    if isinstance(exc, (DreamAlreadyRunningError, DreamProposalConflictError)):
        return HTTPException(
            status_code=409,
            detail={"errorCode": "DREAM_ALREADY_RUNNING", "message": str(exc)},
        )
    if isinstance(exc, DreamProposalStaleError):
        return HTTPException(
            status_code=409,
            detail={"errorCode": "DREAM_PROPOSAL_STALE", "message": str(exc)},
        )
    if isinstance(exc, DreamEvidenceInvalidError):
        return HTTPException(
            status_code=409,
            detail={"errorCode": "DREAM_EVIDENCE_INVALID", "message": str(exc)},
        )
    if isinstance(exc, DreamActiveMemoryLimitError):
        return HTTPException(
            status_code=409,
            detail={
                "errorCode": "DREAM_ACTIVE_LIMIT_EXCEEDED",
                "message": str(exc),
            },
        )
    if isinstance(exc, DreamProposalStateError):
        return HTTPException(
            status_code=409,
            detail={
                "errorCode": "DREAM_PROPOSAL_STATE_INVALID",
                "message": str(exc),
            },
        )
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(
            status_code=422,
            detail={"errorCode": "DREAM_REQUEST_INVALID", "message": str(exc)},
        )
    return HTTPException(
        status_code=503,
        detail={"errorCode": "DREAM_SERVICE_UNAVAILABLE", "message": str(exc)},
    )
