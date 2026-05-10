"""Milestone routes — full CRUD, delegates to MilestoneManager."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from rpg_world.api.deps import get_milestone_manager
from rpg_world.rpg_core.models.models import MilestoneEntry
from rpg_world.rpg_core.milestone import MilestoneManager

router = APIRouter(tags=["milestone"])


@router.get("/milestone/entries")
def list_entries(
    manager: MilestoneManager = Depends(get_milestone_manager),
) -> dict:
    """Return all milestone entries."""
    return {"entries": manager.list_entries()}


@router.get("/milestone/entries/{name}")
def get_entry(
    name: str,
    manager: MilestoneManager = Depends(get_milestone_manager),
) -> dict:
    """Return a single milestone entry by name."""
    try:
        return manager.get_entry(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Entry not found: {name}")


@router.post("/milestone/entries")
def create_entry(
    body: MilestoneEntry,
    manager: MilestoneManager = Depends(get_milestone_manager),
) -> dict:
    """Create a new milestone entry."""
    try:
        data = manager.create_entry(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "created", "data": data}


@router.put("/milestone/entries/{name}")
def update_entry(
    name: str,
    body: MilestoneEntry,
    manager: MilestoneManager = Depends(get_milestone_manager),
) -> dict:
    """Update an existing milestone entry."""
    try:
        data = manager.update_entry(name, body.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "updated", "data": data}


@router.delete("/milestone/entries/{name}")
def delete_entry(
    name: str,
    manager: MilestoneManager = Depends(get_milestone_manager),
) -> dict:
    """Delete a milestone entry."""
    try:
        manager.delete_entry(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "deleted", "name": name}
