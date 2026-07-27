"""Shared Play API Session locator dependency."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from play_api.backends import PlayCatalogBackend
from play_api.dependencies import get_catalog_backend


async def resolve_session_or_404(
    session_id: str,
    catalog: PlayCatalogBackend = Depends(get_catalog_backend),
) -> dict[str, object]:
    session = await catalog.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session
