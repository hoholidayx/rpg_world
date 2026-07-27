"""Shared Play API mapping for deterministic persistence conflicts."""

from __future__ import annotations

from fastapi import HTTPException
from loguru import logger

from rpg_data.errors import DataIntegrityError


def data_integrity_conflict(
    exc: DataIntegrityError,
    *,
    operation: str,
    workspace_id: str,
    story_id: int | None = None,
    resource_id: int | str | None = None,
) -> HTTPException:
    """Log the chained storage failure and preserve the stable 409 wire shape."""
    logger.opt(exception=exc).warning(
        "Play API data conflict operation={} workspace_id={} "
        "story_id={} resource_id={}",
        operation,
        workspace_id,
        story_id if story_id is not None else "<none>",
        resource_id if resource_id is not None else "<none>",
    )
    return HTTPException(status_code=409, detail=str(exc))


__all__ = ["data_integrity_conflict"]
