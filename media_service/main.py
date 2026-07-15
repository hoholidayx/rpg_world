"""FastAPI adapter and process lifecycle for RPG media."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from media_service.schemas import (
    MediaAssetDeleteResponse,
    MediaBackgroundResponse,
    MediaBackgroundSetRequest,
    MediaBriefRequest,
    MediaBriefResponse,
    MediaGalleryItemResponse,
    MediaGalleryResponse,
    MediaHealthResponse,
    MediaJobCreateRequest,
    MediaJobResponse,
    MediaProviderCatalogResponse,
    MediaProviderResponse,
    MediaSourceReferenceResponse,
    MediaSourceTurnResponse,
    MediaSourceTurnsResponse,
    VisualBriefSchema,
)
from media_service.settings import settings as process_settings
from media_service.worker import MediaJobWorker
from rpg_data import models
from rpg_data.services import get_data_service_gateway
from rpg_data.services.gateway import DataServiceGateway
from rpg_data.services.media import MediaSourceRangeError
from rpg_media.errors import MediaError
from rpg_media.facade import MediaFacade
from rpg_media.types import MediaBackgroundView, SessionGalleryAsset, VisualBrief

logger = logging.getLogger("media_service")


class MediaRuntime:
    def __init__(
        self,
        *,
        gateway: DataServiceGateway,
        facade: MediaFacade,
        worker: MediaJobWorker,
    ) -> None:
        self.gateway = gateway
        self.facade = facade
        self.worker = worker

    @classmethod
    def create(cls) -> "MediaRuntime":
        gateway = get_data_service_gateway()
        facade = MediaFacade.from_gateway(gateway)
        worker_settings = process_settings.worker
        return cls(
            gateway=gateway,
            facade=facade,
            worker=MediaJobWorker(
                data=gateway.media,
                facade=facade,
                concurrency=worker_settings.concurrency,
                poll_interval_ms=worker_settings.poll_interval_ms,
            ),
        )


_runtime: MediaRuntime | None = None


def get_runtime() -> MediaRuntime:
    global _runtime
    if _runtime is None:
        _runtime = MediaRuntime.create()
    return _runtime


def set_runtime_for_tests(runtime: MediaRuntime | None) -> None:
    global _runtime
    _runtime = runtime


def _prefix() -> str:
    return process_settings.service.api_prefix


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = get_runtime()
    await runtime.worker.start()
    try:
        yield
    finally:
        await runtime.worker.stop()


app = FastAPI(title="RPG World Media Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"{_prefix()}/health", response_model=MediaHealthResponse)
async def health() -> MediaHealthResponse:
    return MediaHealthResponse()


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/providers",
    response_model=MediaProviderCatalogResponse,
)
async def list_providers(session_id: str) -> MediaProviderCatalogResponse:
    runtime = get_runtime()
    _require_session(runtime, session_id)
    return MediaProviderCatalogResponse(
        defaultKey=runtime.facade.default_provider_key,
        providers=[
            MediaProviderResponse(
                key=item.key,
                displayName=item.display_name,
                kind=item.kind,
                available=item.available,
                reason=item.reason,
            )
            for item in runtime.facade.list_providers()
        ],
    )


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/source-turns",
    response_model=MediaSourceTurnsResponse,
)
async def list_source_turns(session_id: str) -> MediaSourceTurnsResponse:
    try:
        turns = get_runtime().facade.list_source_turns(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return MediaSourceTurnsResponse(
        turns=[
            MediaSourceTurnResponse(
                turnId=turn.turn_id,
                roles=list(turn.roles),
                preview=turn.preview,
                messageCount=turn.message_count,
            )
            for turn in turns
        ]
    )


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/briefs",
    response_model=MediaBriefResponse,
)
async def create_brief(
    session_id: str,
    body: MediaBriefRequest,
) -> MediaBriefResponse:
    try:
        result = get_runtime().facade.create_visual_brief(
            session_id,
            start_turn_id=body.start_turn_id,
            end_turn_id=body.end_turn_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return MediaBriefResponse(
        startTurnId=result.source.start_turn_id,
        endTurnId=result.source.end_turn_id,
        sourceFingerprint=result.source.fingerprint,
        brief=VisualBriefSchema.from_domain(result.brief),
    )


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/jobs",
    response_model=MediaJobResponse,
)
async def create_job(
    session_id: str,
    body: MediaJobCreateRequest,
) -> MediaJobResponse:
    runtime = get_runtime()
    try:
        job = runtime.facade.create_job(
            session_id,
            provider_key=body.provider_key,
            start_turn_id=body.start_turn_id,
            end_turn_id=body.end_turn_id,
            source_fingerprint=body.source_fingerprint,
            visual_brief=body.visual_brief.to_domain(),
            generation_params=body.generation_params,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    runtime.worker.wake()
    return _job_response(job)


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/jobs/{{job_id}}",
    response_model=MediaJobResponse,
)
async def get_job(session_id: str, job_id: str) -> MediaJobResponse:
    try:
        job = get_runtime().facade.get_job(session_id, job_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="media job not found")
    return _job_response(job)


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/jobs/{{job_id}}/cancel",
    response_model=MediaJobResponse,
)
async def cancel_job(session_id: str, job_id: str) -> MediaJobResponse:
    try:
        job = get_runtime().facade.cancel_job(session_id, job_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="media job not found")
    get_runtime().worker.wake()
    return _job_response(job)


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/jobs/{{job_id}}/retry",
    response_model=MediaJobResponse,
)
async def retry_job(session_id: str, job_id: str) -> MediaJobResponse:
    runtime = get_runtime()
    try:
        job = runtime.facade.retry_job(session_id, job_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    runtime.worker.wake()
    return _job_response(job)


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/gallery",
    response_model=MediaGalleryResponse,
)
async def get_gallery(session_id: str) -> MediaGalleryResponse:
    runtime = get_runtime()
    try:
        items = runtime.facade.list_gallery(session_id)
        active_jobs = runtime.facade.list_active_jobs(session_id)
        recent_jobs = runtime.facade.list_jobs(session_id)[:30]
    except Exception as exc:
        raise _http_error(exc) from exc
    return MediaGalleryResponse(
        items=[_gallery_item_response(item) for item in items],
        activeJobs=[_job_response(job) for job in active_jobs],
        recentJobs=[_job_response(job) for job in recent_jobs],
    )


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/background",
    response_model=MediaBackgroundResponse,
)
async def get_background(session_id: str) -> MediaBackgroundResponse:
    try:
        background = get_runtime().facade.get_background(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return _background_response(background)


@app.put(
    f"{_prefix()}/sessions/{{session_id}}/background",
    response_model=MediaBackgroundResponse,
)
async def set_background(
    session_id: str,
    body: MediaBackgroundSetRequest,
) -> MediaBackgroundResponse:
    try:
        background = get_runtime().facade.set_background(session_id, body.asset_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return _background_response(background)


@app.delete(
    f"{_prefix()}/sessions/{{session_id}}/background",
    response_model=MediaBackgroundResponse,
)
async def clear_background(session_id: str) -> MediaBackgroundResponse:
    try:
        get_runtime().facade.clear_background(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return MediaBackgroundResponse(background=None)


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/assets/{{asset_id}}",
    response_model=MediaGalleryItemResponse,
)
async def get_asset(session_id: str, asset_id: str) -> MediaGalleryItemResponse:
    try:
        asset = get_runtime().facade.get_session_asset(session_id, asset_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="media asset not found")
    return _gallery_item_response(asset)


@app.delete(
    f"{_prefix()}/sessions/{{session_id}}/assets/{{asset_id}}",
    response_model=MediaAssetDeleteResponse,
)
async def delete_asset(session_id: str, asset_id: str) -> MediaAssetDeleteResponse:
    try:
        deleted = get_runtime().facade.delete_asset(session_id, asset_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="media asset not found")
    return MediaAssetDeleteResponse(assetId=asset_id, deleted=True)


@app.get(f"{_prefix()}/sessions/{{session_id}}/assets/{{asset_id}}/content")
async def get_asset_content(session_id: str, asset_id: str) -> FileResponse:
    try:
        path, mime_type = get_runtime().facade.resolve_asset_content(
            session_id,
            asset_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="media asset content not found")
    return FileResponse(
        path,
        media_type=mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


def _job_response(job: models.MediaJob) -> MediaJobResponse:
    params: object = json.loads(job.generation_params_json or "{}")
    if not isinstance(params, dict):
        params = {}
    return MediaJobResponse(
        jobId=job.id,
        sessionId=job.session_id,
        providerKey=job.provider_key,
        status=job.status,
        startTurnId=job.source_start_turn_id,
        endTurnId=job.source_end_turn_id,
        sourceFingerprint=job.source_fingerprint,
        visualBrief=VisualBriefSchema.from_domain(
            VisualBrief.from_json(job.visual_brief_json)
        ),
        generationParams=params,
        outputAssetId=job.output_asset_id,
        retryOfJobId=job.retry_of_job_id,
        errorCode=job.error_code,
        errorMessage=job.error_message,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
    )


def _gallery_item_response(item: SessionGalleryAsset) -> MediaGalleryItemResponse:
    bundle = item.bundle
    source = bundle.gallery_item
    return MediaGalleryItemResponse(
        assetId=bundle.asset.id,
        jobId=source.job_id,
        providerKey=bundle.asset.provider_key,
        sha256=bundle.blob.sha256,
        mimeType=bundle.blob.mime_type,
        byteSize=bundle.blob.byte_size,
        visualBrief=VisualBriefSchema.from_domain(
            VisualBrief.from_json(bundle.asset.visual_brief_json)
        ),
        source=MediaSourceReferenceResponse(
            startTurnId=source.source_start_turn_id,
            endTurnId=source.source_end_turn_id,
            fingerprint=source.source_fingerprint,
            stale=item.source_stale,
        ),
        createdAt=bundle.gallery_item.created_at,
    )


def _background_response(
    background: MediaBackgroundView | None,
) -> MediaBackgroundResponse:
    return MediaBackgroundResponse(
        background=(
            _gallery_item_response(background.asset)
            if background is not None
            else None
        )
    )


def _require_session(runtime: MediaRuntime, session_id: str) -> models.Session:
    session = runtime.gateway.catalog.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, MediaError):
        status_code = 409 if exc.code in {
            "MEDIA_SOURCE_CHANGED",
            "MEDIA_ASSET_IN_USE",
            "MEDIA_JOB_NOT_RETRYABLE",
        } else 422
        return HTTPException(
            status_code=status_code,
            detail={"errorCode": exc.code, "message": str(exc)},
        )
    if isinstance(exc, (MediaSourceRangeError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))
