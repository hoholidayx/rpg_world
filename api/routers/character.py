"""Character routes — full CRUD, delegates to CharacterManager."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from rpg_world.api.deps import get_character_manager
from rpg_world.rpg_core.character import CharacterManager
from rpg_world.rpg_core.models.models import CharacterData, CharacterDetail

router = APIRouter(tags=["character"])


@router.get("/characters")
def list_characters(
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Return all character cards (summary)."""
    return {"characters": manager.list_characters()}


@router.get("/characters/{name}")
def get_character(
    name: str,
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Return a single character card by name."""
    try:
        return manager.get_character(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Character not found: {name}")


@router.post("/characters")
def create_character(
    body: CharacterData,
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Create a new character card."""
    try:
        data = manager.create_character(body.model_dump())
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "created", "data": data}


@router.put("/characters/{name}")
def update_character(
    name: str,
    body: CharacterData,
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Update an existing character card."""
    try:
        data = manager.update_character(name, body.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "updated", "data": data}


@router.delete("/characters/{name}")
def delete_character(
    name: str,
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Delete a character card."""
    try:
        manager.delete_character(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "deleted", "name": name}


# --- L2 Detail routes ---


@router.get("/characters/{name}/details")
def list_details(
    name: str,
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Return all L2 details for a character."""
    try:
        return {"details": manager.list_details(name)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/characters/{name}/details/{detail_name}")
def get_detail(
    name: str,
    detail_name: str,
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Return a single L2 detail by name."""
    try:
        return manager.get_detail(name, detail_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/characters/{name}/details")
def create_detail(
    name: str,
    body: CharacterDetail,
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Create a new L2 detail for a character."""
    try:
        data = manager.add_detail(name, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "created", "data": data}


@router.put("/characters/{name}/details/{detail_name}")
def update_detail(
    name: str,
    detail_name: str,
    body: CharacterDetail,
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Update an existing L2 detail."""
    try:
        data = manager.update_detail(name, detail_name, body.model_dump(exclude_unset=True))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "updated", "data": data}


@router.delete("/characters/{name}/details/{detail_name}")
def delete_detail(
    name: str,
    detail_name: str,
    manager: CharacterManager = Depends(get_character_manager),
) -> dict:
    """Delete an L2 detail."""
    try:
        manager.remove_detail(name, detail_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "deleted", "name": detail_name}
