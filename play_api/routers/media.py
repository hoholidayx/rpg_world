"""Session-scoped Play WebUI media proxy endpoints."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from media_service.client import (
    MediaClientError,
    MediaServiceUnavailable,
)
from media_service.schemas import (
    MediaAssetDeleteResponse,
    MediaBackgroundResponse,
    MediaBackgroundSetRequest,
    MediaBriefRequest,
    MediaBriefResponse,
    MediaGalleryItemResponse,
    MediaGalleryResponse,
    MediaJobCreateRequest,
    MediaJobResponse,
    MediaProviderCatalogResponse,
    MediaSourceTurnsResponse,
)
from play_api.media_client import get_media_client
from play_api.routers._locator import resolve_session_or_404

router = APIRouter(tags=["play-media"])
ResponseT = TypeVar("ResponseT")


@router.get(
    "/sessions/{session_id}/media/providers",
    response_model=MediaProviderCatalogResponse,
)
async def list_media_providers(session_id: str) -> MediaProviderCatalogResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().list_providers(session_id))


@router.get(
    "/sessions/{session_id}/media/source-turns",
    response_model=MediaSourceTurnsResponse,
)
async def list_media_source_turns(session_id: str) -> MediaSourceTurnsResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().list_source_turns(session_id))


@router.post(
    "/sessions/{session_id}/media/briefs",
    response_model=MediaBriefResponse,
)
async def create_media_brief(
    session_id: str,
    body: MediaBriefRequest,
) -> MediaBriefResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().create_brief(session_id, body))


@router.post(
    "/sessions/{session_id}/media/jobs",
    response_model=MediaJobResponse,
)
async def create_media_job(
    session_id: str,
    body: MediaJobCreateRequest,
) -> MediaJobResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().create_job(session_id, body))


@router.get(
    "/sessions/{session_id}/media/gallery",
    response_model=MediaGalleryResponse,
)
async def get_media_gallery(session_id: str) -> MediaGalleryResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().get_gallery(session_id))


@router.get(
    "/sessions/{session_id}/media/jobs/{job_id}",
    response_model=MediaJobResponse,
)
async def get_media_job(session_id: str, job_id: str) -> MediaJobResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().get_job(session_id, job_id))


@router.post(
    "/sessions/{session_id}/media/jobs/{job_id}/cancel",
    response_model=MediaJobResponse,
)
async def cancel_media_job(session_id: str, job_id: str) -> MediaJobResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().cancel_job(session_id, job_id))


@router.post(
    "/sessions/{session_id}/media/jobs/{job_id}/retry",
    response_model=MediaJobResponse,
)
async def retry_media_job(session_id: str, job_id: str) -> MediaJobResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().retry_job(session_id, job_id))


@router.get(
    "/sessions/{session_id}/media/background",
    response_model=MediaBackgroundResponse,
)
async def get_media_background(session_id: str) -> MediaBackgroundResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().get_background(session_id))


@router.put(
    "/sessions/{session_id}/media/background",
    response_model=MediaBackgroundResponse,
)
async def set_media_background(
    session_id: str,
    body: MediaBackgroundSetRequest,
) -> MediaBackgroundResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().set_background(session_id, body))


@router.delete(
    "/sessions/{session_id}/media/background",
    response_model=MediaBackgroundResponse,
)
async def clear_media_background(session_id: str) -> MediaBackgroundResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().clear_background(session_id))


@router.get(
    "/sessions/{session_id}/media/assets/{asset_id}",
    response_model=MediaGalleryItemResponse,
)
async def get_media_asset(
    session_id: str,
    asset_id: str,
) -> MediaGalleryItemResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().get_asset(session_id, asset_id))


@router.delete(
    "/sessions/{session_id}/media/assets/{asset_id}",
    response_model=MediaAssetDeleteResponse,
)
async def delete_media_asset(
    session_id: str,
    asset_id: str,
) -> MediaAssetDeleteResponse:
    await resolve_session_or_404(session_id)
    return await _media_call(get_media_client().delete_asset(session_id, asset_id))


@router.get("/sessions/{session_id}/media/assets/{asset_id}/content")
async def stream_media_asset(
    session_id: str,
    asset_id: str,
) -> StreamingResponse:
    await resolve_session_or_404(session_id)
    stream = await _media_call(
        get_media_client().stream_asset_content(session_id, asset_id)
    )
    headers = {
        "Cache-Control": "private, max-age=3600",
        "X-Content-Type-Options": "nosniff",
    }
    if stream.content_length is not None:
        headers["Content-Length"] = str(stream.content_length)
    return StreamingResponse(
        stream.chunks,
        media_type=stream.media_type,
        headers=headers,
    )


async def _media_call(awaitable: Awaitable[ResponseT]) -> ResponseT:
    try:
        return await awaitable
    except MediaServiceUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "errorCode": "MEDIA_SERVICE_UNAVAILABLE",
                "message": str(exc),
            },
        ) from exc
    except MediaClientError as exc:
        status_code = exc.status_code or 502
        raise HTTPException(
            status_code=status_code,
            detail={
                "errorCode": exc.error_code or "MEDIA_SERVICE_ERROR",
                "message": str(exc),
            },
        ) from exc
