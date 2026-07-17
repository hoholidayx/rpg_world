"""Session-scoped Dream proposal and persistent-memory proxy endpoints."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Literal, TypeVar

from fastapi import APIRouter, HTTPException, Query, status

from dream_service.client import DreamClientError, DreamServiceUnavailable
from dream_service.schemas import (
    DreamMemoryListResponse,
    DreamMemoryResponse,
    DreamProposalCreateRequest,
    DreamProposalListResponse,
    DreamProposalResponse,
    DreamProposalUpdateRequest,
)
from play_api.dream_client import get_dream_client
from play_api.routers._locator import resolve_session_or_404

router = APIRouter(tags=["play-dream"])
ResponseT = TypeVar("ResponseT")


@router.post(
    "/sessions/{session_id}/dream/proposals",
    response_model=DreamProposalResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_dream_proposal(
    session_id: str,
    body: DreamProposalCreateRequest,
) -> DreamProposalResponse:
    await resolve_session_or_404(session_id)
    return await _dream_call(
        get_dream_client().create_proposal(
            session_id,
            depth=body.depth,
            scope=body.scope,
        )
    )


@router.get(
    "/sessions/{session_id}/dream/proposals",
    response_model=DreamProposalListResponse,
)
async def list_dream_proposals(session_id: str) -> DreamProposalListResponse:
    await resolve_session_or_404(session_id)
    return await _dream_call(get_dream_client().list_proposals(session_id))


@router.get(
    "/sessions/{session_id}/dream/proposals/{proposal_id}",
    response_model=DreamProposalResponse,
)
async def get_dream_proposal(
    session_id: str,
    proposal_id: str,
) -> DreamProposalResponse:
    await resolve_session_or_404(session_id)
    return await _dream_call(
        get_dream_client().get_proposal(session_id, proposal_id)
    )


@router.patch(
    "/sessions/{session_id}/dream/proposals/{proposal_id}",
    response_model=DreamProposalResponse,
)
async def update_dream_proposal(
    session_id: str,
    proposal_id: str,
    body: DreamProposalUpdateRequest,
) -> DreamProposalResponse:
    await resolve_session_or_404(session_id)
    return await _dream_call(
        get_dream_client().update_proposal(session_id, proposal_id, body)
    )


@router.post(
    "/sessions/{session_id}/dream/proposals/{proposal_id}/apply",
    response_model=DreamProposalResponse,
)
async def apply_dream_proposal(
    session_id: str,
    proposal_id: str,
) -> DreamProposalResponse:
    await resolve_session_or_404(session_id)
    return await _dream_call(
        get_dream_client().apply_proposal(session_id, proposal_id)
    )


@router.post(
    "/sessions/{session_id}/dream/proposals/{proposal_id}/reject",
    response_model=DreamProposalResponse,
)
async def reject_dream_proposal(
    session_id: str,
    proposal_id: str,
) -> DreamProposalResponse:
    await resolve_session_or_404(session_id)
    return await _dream_call(
        get_dream_client().reject_proposal(session_id, proposal_id)
    )


@router.get(
    "/sessions/{session_id}/dream/memories",
    response_model=DreamMemoryListResponse,
)
async def list_dream_memories(
    session_id: str,
    lifecycle: Literal["active", "retired", "superseded"] | None = Query(
        default=None
    ),
) -> DreamMemoryListResponse:
    await resolve_session_or_404(session_id)
    return await _dream_call(
        get_dream_client().list_memories(session_id, lifecycle=lifecycle)
    )


@router.post(
    "/sessions/{session_id}/dream/memories/{memory_id}/restore",
    response_model=DreamMemoryResponse,
)
async def restore_dream_memory(
    session_id: str,
    memory_id: str,
) -> DreamMemoryResponse:
    await resolve_session_or_404(session_id)
    return await _dream_call(
        get_dream_client().restore_memory(session_id, memory_id)
    )


async def _dream_call(awaitable: Awaitable[ResponseT]) -> ResponseT:
    try:
        return await awaitable
    except DreamServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "errorCode": "DREAM_SERVICE_UNAVAILABLE",
                "message": str(exc),
            },
        ) from exc
    except DreamClientError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail={
                "errorCode": exc.error_code or "DREAM_SERVICE_ERROR",
                "message": str(exc),
            },
        ) from exc
