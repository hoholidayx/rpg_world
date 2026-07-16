"""Session-scoped TTS proxy isolated from Agent chat endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Response

from play_api.routers._locator import resolve_session_or_404
from play_api.tts_client import get_tts_client
from tts_service.client import TTSClientError
from tts_service.schemas import TTSAudioPartResponse, TTSJobResponse

router = APIRouter(tags=["play-tts"])


@router.post(
    "/sessions/{session_id}/tts/messages/{message_id}/jobs",
    response_model=TTSJobResponse,
)
async def create_tts_job(session_id: str, message_id: int) -> TTSJobResponse:
    await resolve_session_or_404(session_id)
    return _rewrite_parts(await _call(get_tts_client().create_job(session_id, message_id)))


@router.get(
    "/sessions/{session_id}/tts/jobs/{job_id}",
    response_model=TTSJobResponse,
)
async def get_tts_job(session_id: str, job_id: str) -> TTSJobResponse:
    await resolve_session_or_404(session_id)
    return _rewrite_parts(await _call(get_tts_client().get_job(session_id, job_id)))


@router.post(
    "/sessions/{session_id}/tts/jobs/{job_id}/retry",
    response_model=TTSJobResponse,
)
async def retry_tts_job(session_id: str, job_id: str) -> TTSJobResponse:
    await resolve_session_or_404(session_id)
    return _rewrite_parts(await _call(get_tts_client().retry_job(session_id, job_id)))


@router.get("/sessions/{session_id}/tts/jobs/{job_id}/parts/{part_index}/audio")
async def get_tts_audio(
    session_id: str,
    job_id: str,
    part_index: int,
    range_header: str | None = Header(default=None, alias="Range"),
) -> Response:
    await resolve_session_or_404(session_id)
    upstream = await _call(
        get_tts_client().get_audio(
            session_id,
            job_id,
            part_index,
            range_header=range_header,
        )
    )
    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in {
            "accept-ranges",
            "content-range",
            "content-length",
            "etag",
            "last-modified",
        }
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type="audio/mpeg",
        headers=headers,
    )


async def _call(awaitable):  # noqa: ANN001, ANN202
    try:
        return await awaitable
    except TTSClientError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"errorCode": exc.error_code, "message": str(exc)},
        ) from exc


def _rewrite_parts(job: TTSJobResponse) -> TTSJobResponse:
    return job.model_copy(
        update={
            "parts": [
                TTSAudioPartResponse(
                    partIndex=part.part_index,
                    audioUrl=(
                        f"/sessions/{job.session_id}/tts/jobs/{job.job_id}"
                        f"/parts/{part.part_index}/audio"
                    ),
                )
                for part in job.parts
            ]
        }
    )
