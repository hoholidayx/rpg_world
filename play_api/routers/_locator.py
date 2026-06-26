"""Shared Play API session resolution."""

from __future__ import annotations

from fastapi import HTTPException

from play_api.backends import get_data_manager_backend


async def resolve_session_or_404(session_id: str) -> dict[str, object]:
    session = await get_data_manager_backend().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session
