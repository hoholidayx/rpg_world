"""Shared Play API locator validation."""

from __future__ import annotations

from fastapi import HTTPException

from play_api.backends import get_data_manager_backend


async def require_session_locator(workspace: str, story_id: int, session_id: str) -> None:
    session = await get_data_manager_backend().get_session_by_locator(
        workspace,
        story_id,
        session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="session locator not found")
