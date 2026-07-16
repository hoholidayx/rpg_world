"""FastAPI adapter and process lifecycle for RPG media."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from llm_client.manager import LLMClientManager

from media_service.schemas import (
    MediaAssetDeleteResponse,
    MediaBackgroundResponse,
    MediaBackgroundEvaluationRequest,
    MediaBackgroundEvaluationResponse,
    MediaDisplayAssetResponse,
    MediaBackgroundSetRequest,
    MediaBriefRequest,
    MediaBriefResponse,
    MediaGalleryItemResponse,
    MediaGalleryResponse,
    MediaHealthResponse,
    MediaLibraryItemResponse,
    MediaLibraryDeleteResponse,
    MediaLibraryReconcileResponse,
    MediaLibraryResponse,
    MediaLibraryUpdateRequest,
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
from media_service.worker import MediaBackgroundWorker, MediaJobWorker
from rpg_data import models
from rpg_data.services import get_data_service_gateway
from rpg_data.services.gateway import DataServiceGateway
from rpg_data.services.media import MediaSourceRangeError
from rpg_media.errors import MediaError
from rpg_media.facade import MediaFacade
from rpg_media.types import MediaBackgroundView, SessionGalleryAsset, VisualBrief

logger = logging.getLogger("media_service")

_MAX_UPLOAD_BYTES = 32 * 1024 * 1024


class MediaRuntime:
    def __init__(
        self,
        *,
        gateway: DataServiceGateway,
        facade: MediaFacade,
        worker: MediaJobWorker,
        background_worker: MediaBackgroundWorker | None = None,
    ) -> None:
        self.gateway = gateway
        self.facade = facade
        self.worker = worker
        self.background_worker = background_worker or MediaBackgroundWorker(
            data=gateway.media,
            facade=facade,
            concurrency=process_settings.background_worker.concurrency,
        )

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
            ),
            background_worker=MediaBackgroundWorker(
                data=gateway.media,
                facade=facade,
                concurrency=process_settings.background_worker.concurrency,
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
    llm = process_settings.llm_client
    await LLMClientManager.aconfigure(
        base_url=llm.base_url,
        token=llm.token,
        request_timeout_ms=llm.request_timeout_ms,
        stream_timeout_ms=llm.stream_timeout_ms,
    )
    runtime: MediaRuntime | None = None
    try:
        runtime = get_runtime()
        await runtime.worker.start()
        await runtime.background_worker.start()
        yield
    finally:
        if runtime is not None:
            await runtime.background_worker.stop()
            await runtime.worker.stop()
        await LLMClientManager.areset()


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
    f"{_prefix()}/workspaces/{{workspace_id}}/library",
    response_model=MediaLibraryResponse,
)
async def list_library_assets(
    workspace_id: str,
    scope: str | None = Query(default=None),
    story_id: int | None = Query(default=None, alias="storyId"),
) -> MediaLibraryResponse:
    try:
        items = get_runtime().facade.list_library_assets(
            workspace_id,
            scope=scope,
            story_id=story_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return MediaLibraryResponse(items=[_library_item_response(item) for item in items])


@app.post(
    f"{_prefix()}/workspaces/{{workspace_id}}/library/reconcile",
    response_model=MediaLibraryReconcileResponse,
)
async def reconcile_library_assets(
    workspace_id: str,
) -> MediaLibraryReconcileResponse:
    try:
        result = await get_runtime().facade.reconcile_library_assets(workspace_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return MediaLibraryReconcileResponse(
        workspaceId=result.workspace_id,
        scannedBlobs=result.scanned_blobs,
        removedBlobs=result.removed_blobs,
        removedAssets=result.removed_assets,
        removedLibraryItems=result.removed_library_items,
        removedGalleryItems=result.removed_gallery_items,
        clearedBackgrounds=result.cleared_backgrounds,
    )


@app.post(
    f"{_prefix()}/workspaces/{{workspace_id}}/library",
    response_model=MediaLibraryItemResponse,
)
async def upload_library_asset(
    workspace_id: str,
    file: UploadFile = File(...),
    scope: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    tags: str = Form(...),
    story_id: int | None = Form(default=None, alias="storyId"),
    is_default: bool = Form(default=False, alias="isDefault"),
) -> MediaLibraryItemResponse:
    try:
        parsed_tags = json.loads(tags)
        if not isinstance(parsed_tags, list):
            raise ValueError("media library tags must be a JSON array")
        payload = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(payload) > _MAX_UPLOAD_BYTES:
            raise ValueError("media library image exceeds the 32 MiB upload limit")
        bundle = await get_runtime().facade.upload_library_asset(
            workspace_id=workspace_id,
            scope=scope,
            story_id=story_id,
            title=title,
            description=description,
            tags=tuple(str(tag) for tag in parsed_tags),
            is_default=is_default,
            data=payload,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await file.close()
    return _library_item_response(bundle)


@app.patch(
    f"{_prefix()}/workspaces/{{workspace_id}}/library/{{item_id}}",
    response_model=MediaLibraryItemResponse,
)
async def update_library_asset(
    workspace_id: str,
    item_id: str,
    body: MediaLibraryUpdateRequest,
) -> MediaLibraryItemResponse:
    try:
        bundle = get_runtime().facade.update_library_asset(
            workspace_id,
            item_id,
            title=body.title,
            description=body.description,
            tags=tuple(body.tags),
            is_default=body.is_default,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    if bundle is None:
        raise HTTPException(status_code=404, detail="media library item not found")
    return _library_item_response(bundle)


@app.delete(
    f"{_prefix()}/workspaces/{{workspace_id}}/library/{{item_id}}",
    response_model=MediaLibraryDeleteResponse,
)
async def delete_library_asset(
    workspace_id: str,
    item_id: str,
) -> MediaLibraryDeleteResponse:
    try:
        deleted = get_runtime().facade.delete_library_asset(workspace_id, item_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="media library item not found")
    return MediaLibraryDeleteResponse(itemId=item_id, deleted=True)


@app.get(f"{_prefix()}/workspaces/{{workspace_id}}/library/{{item_id}}/content")
async def get_library_asset_content(workspace_id: str, item_id: str) -> FileResponse:
    try:
        path, mime_type = get_runtime().facade.resolve_library_asset_content(
            workspace_id,
            item_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="media library content not found")
    return FileResponse(
        path,
        media_type=mime_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
    runtime = get_runtime()
    try:
        background = runtime.facade.get_background(session_id)
        latest = runtime.facade.get_latest_background_evaluation(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return _background_response(background, latest)


@app.put(
    f"{_prefix()}/sessions/{{session_id}}/background",
    response_model=MediaBackgroundResponse,
)
async def set_background(
    session_id: str,
    body: MediaBackgroundSetRequest,
) -> MediaBackgroundResponse:
    runtime = get_runtime()
    try:
        background = runtime.facade.set_background(session_id, body.asset_id)
        latest = runtime.facade.get_latest_background_evaluation(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return _background_response(background, latest)


@app.delete(
    f"{_prefix()}/sessions/{{session_id}}/background",
    response_model=MediaBackgroundResponse,
)
async def clear_background(session_id: str) -> MediaBackgroundResponse:
    runtime = get_runtime()
    try:
        runtime.facade.clear_background(session_id)
        background = runtime.facade.get_background(session_id)
        latest = runtime.facade.get_latest_background_evaluation(session_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return _background_response(background, latest)


@app.post(
    f"{_prefix()}/sessions/{{session_id}}/background-evaluations",
    response_model=MediaBackgroundEvaluationResponse,
)
async def queue_background_evaluation(
    session_id: str,
    body: MediaBackgroundEvaluationRequest,
) -> MediaBackgroundEvaluationResponse:
    runtime = get_runtime()
    try:
        evaluation = runtime.facade.queue_background_evaluation(
            session_id,
            observed_turn_id=body.observed_turn_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    runtime.background_worker.wake()
    return _background_evaluation_response(evaluation)


@app.get(
    f"{_prefix()}/sessions/{{session_id}}/background-evaluations/{{evaluation_id}}",
    response_model=MediaBackgroundEvaluationResponse,
)
async def get_background_evaluation(
    session_id: str,
    evaluation_id: str,
) -> MediaBackgroundEvaluationResponse:
    try:
        evaluation = get_runtime().facade.get_background_evaluation(
            session_id,
            evaluation_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    if evaluation is None:
        raise HTTPException(status_code=404, detail="media background evaluation not found")
    return _background_evaluation_response(evaluation)


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
    latest_evaluation: models.MediaBackgroundEvaluation | None = None,
) -> MediaBackgroundResponse:
    if background is None:
        return MediaBackgroundResponse(
            background=None,
            sourceMode="none",
            manualLocked=False,
            revisionToken="none",
            latestEvaluation=(
                _background_evaluation_response(latest_evaluation)
                if latest_evaluation is not None
                else None
            ),
        )
    return MediaBackgroundResponse(
        background=(
            _display_asset_response(background.asset)
            if background.asset is not None
            else None
        ),
        sourceMode=background.source_mode,
        manualLocked=background.manual_locked,
        revisionToken=background.revision_token,
        lastDecision=background.state.last_decision,
        lastReason=background.state.last_reason,
        latestEvaluation=(
            _background_evaluation_response(latest_evaluation)
            if latest_evaluation is not None
            else None
        ),
    )


def _display_asset_response(
    bundle: models.MediaDisplayAssetBundle,
) -> MediaDisplayAssetResponse:
    library_item = bundle.library_item
    if library_item is not None:
        title = library_item.title
    else:
        try:
            title = VisualBrief.from_json(bundle.asset.visual_brief_json).scene_description
        except (TypeError, ValueError, json.JSONDecodeError):
            title = ""
    return MediaDisplayAssetResponse(
        assetId=bundle.asset.id,
        libraryItemId=library_item.id if library_item is not None else None,
        origin=bundle.asset.origin_kind,
        mimeType=bundle.blob.mime_type,
        byteSize=bundle.blob.byte_size,
        title=title,
        tags=list(bundle.tags),
        createdAt=bundle.asset.created_at,
    )


def _library_item_response(
    bundle: models.MediaLibraryAssetBundle,
) -> MediaLibraryItemResponse:
    item = bundle.item
    return MediaLibraryItemResponse(
        itemId=item.id,
        assetId=bundle.asset.id,
        workspaceId=item.workspace_id,
        scope=item.scope,
        storyId=item.story_id,
        title=item.title,
        description=item.description,
        tags=list(bundle.tags),
        isDefault=item.is_default,
        origin=bundle.asset.origin_kind,
        mimeType=bundle.blob.mime_type,
        byteSize=bundle.blob.byte_size,
        createdAt=item.created_at,
        updatedAt=item.updated_at,
    )


def _background_evaluation_response(
    evaluation: models.MediaBackgroundEvaluation,
) -> MediaBackgroundEvaluationResponse:
    return MediaBackgroundEvaluationResponse(
        evaluationId=evaluation.id,
        sessionId=evaluation.session_id,
        status=evaluation.status,
        targetTurnId=evaluation.target_turn_id,
        decision=evaluation.decision,
        selectedAssetId=evaluation.selected_asset_id,
        reason=evaluation.reason,
        errorCode=evaluation.error_code,
        errorMessage=evaluation.error_message,
        createdAt=evaluation.created_at,
        updatedAt=evaluation.updated_at,
        startedAt=evaluation.started_at,
        finishedAt=evaluation.finished_at,
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
