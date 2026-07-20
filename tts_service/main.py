from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from llm_client.manager import LLMClientManager

from rpg_data.model import tts as models
from rpg_data.services import get_data_service_gateway
from rpg_data.services.gateway import DataServiceGateway
from rpg_tts.service import TTSApplicationService
from tts_service.schemas import (
    TTSAudioPartResponse,
    TTSHealthResponse,
    TTSJobResponse,
    TTSReconcileResponse,
)
from tts_service.settings import settings
from tts_service.worker import TTSJobWorker


class TTSRuntime:
    def __init__(
        self,
        *,
        gateway: DataServiceGateway,
        service: TTSApplicationService,
        worker: TTSJobWorker,
    ) -> None:
        self.gateway = gateway
        self.service = service
        self.worker = worker

    @classmethod
    def create(cls) -> "TTSRuntime":
        gateway = get_data_service_gateway()
        service = TTSApplicationService(data=gateway.tts)
        return cls(
            gateway=gateway,
            service=service,
            worker=TTSJobWorker(
                service=service,
                concurrency=settings.worker.concurrency,
            ),
        )


_runtime: TTSRuntime | None = None


def get_runtime() -> TTSRuntime:
    global _runtime
    if _runtime is None:
        _runtime = TTSRuntime.create()
    return _runtime


def set_runtime_for_tests(runtime: TTSRuntime | None) -> None:
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
    runtime: TTSRuntime | None = None
    try:
        runtime = get_runtime()
        await runtime.worker.start()
        yield
    finally:
        try:
            if runtime is not None:
                await runtime.worker.stop()
        finally:
            if _runtime is runtime:
                _runtime = None
            await LLMClientManager.areset()


app = FastAPI(title="RPG World TTS Service", lifespan=lifespan)


@app.get(f"{_prefix()}/health", response_model=TTSHealthResponse)
async def health() -> TTSHealthResponse:
    return TTSHealthResponse()


@app.post(
    f"{_prefix()}/workspaces/{{workspace_id}}/reconcile",
    response_model=TTSReconcileResponse,
)
async def reconcile_workspace(workspace_id: str) -> TTSReconcileResponse:
    try:
        result = await get_runtime().service.reconcile_workspace(workspace_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return TTSReconcileResponse(
        workspaceId=result.workspace_id,
        scannedBlobs=result.scanned_blobs,
        removedBlobs=result.removed_blobs,
        removedFiles=result.removed_files,
    )


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/messages/{{message_id}}/jobs",
    response_model=TTSJobResponse,
)
async def create_job(session_id: str, message_id: int) -> TTSJobResponse:
    try:
        job = await get_runtime().service.create_job(session_id, message_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if job.status == models.TTS_JOB_STATUS_QUEUED:
        get_runtime().worker.wake()
    return _job_response(job)


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/jobs/{{job_id}}",
    response_model=TTSJobResponse,
)
async def get_job(session_id: str, job_id: str) -> TTSJobResponse:
    job = get_runtime().service.get_job(session_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "errorCode": "TTS_JOB_NOT_FOUND",
                "message": "TTS job not found",
            },
        )
    return _job_response(job)


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/jobs/{{job_id}}/retry",
    response_model=TTSJobResponse,
)
async def retry_job(session_id: str, job_id: str) -> TTSJobResponse:
    try:
        job = await get_runtime().service.retry_job(session_id, job_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "errorCode": "TTS_JOB_NOT_FOUND",
                "message": "TTS job not found",
            },
        )
    if job.status == models.TTS_JOB_STATUS_QUEUED:
        get_runtime().worker.wake()
    return _job_response(job)


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/jobs/{{job_id}}/parts/{{part_index}}/audio"
)
async def get_audio(session_id: str, job_id: str, part_index: int) -> FileResponse:
    try:
        path = get_runtime().service.resolve_audio_part(session_id, job_id, part_index)
    except Exception as exc:
        raise _http_error(exc) from exc
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "errorCode": "TTS_AUDIO_NOT_FOUND",
                "message": "TTS audio file not found",
            },
        )
    return FileResponse(path, media_type="audio/mpeg", filename=None)


def _job_response(job: models.TTSJob) -> TTSJobResponse:
    parts = get_runtime().service.list_parts(job.session_id, job.id)
    return TTSJobResponse(
        jobId=job.id,
        sessionId=job.session_id,
        messageId=job.message_id,
        status=job.status,
        partCount=len(parts),
        parts=[
            TTSAudioPartResponse(
                partIndex=part.part_index,
                audioUrl=(
                    f"{_prefix()}/sessions/{job.session_id}/jobs/{job.id}"
                    f"/parts/{part.part_index}/audio"
                ),
            )
            for part, _blob in parts
        ],
        errorCode=job.error_code,
        errorMessage=job.error_message,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"errorCode": "TTS_NOT_FOUND", "message": str(exc)},
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=422,
            detail={"errorCode": "TTS_REQUEST_INVALID", "message": str(exc)},
        )
    return HTTPException(
        status_code=503,
        detail={"errorCode": "TTS_SERVICE_UNAVAILABLE", "message": str(exc)},
    )
