"""Status routes — full CRUD for types and CSV tables, delegates to StatusManager."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from rpg_world.api.deps import get_session_status_manager
from rpg_world.rpg_core.status import StatusManager

router = APIRouter(tags=["status"])


# ============================================================================
# Type CRUD
# ============================================================================


@router.get("/status/types")
def list_types(
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Return all status type names."""
    return {"types": manager.list_types()}


@router.post("/status/types")
def create_type(
    body: dict,
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Create a new status type (directory)."""
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Type name is required")
    try:
        manager.create_type(name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "created", "name": name}


@router.put("/status/types/{type_name}")
def rename_type(
    type_name: str,
    body: dict,
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Rename a status type."""
    new_name = body.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New type name is required")
    try:
        manager.rename_type(type_name, new_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "renamed", "name": new_name}


@router.delete("/status/types/{type_name}")
def delete_type(
    type_name: str,
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Delete a status type and all its tables."""
    try:
        manager.delete_type(type_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "deleted", "name": type_name}


# ============================================================================
# Table CRUD
# ============================================================================


@router.get("/status/types/{type_name}/tables")
def list_tables(
    type_name: str,
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Return all table names for a type."""
    try:
        tables = manager.list_tables(type_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"tables": tables}


@router.post("/status/types/{type_name}/tables")
def create_table(
    type_name: str,
    body: dict,
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Create a new table in a type."""
    table_name = body.get("name", "").strip()
    if not table_name:
        raise HTTPException(status_code=400, detail="Table name is required")
    headers = body.get("headers", [])
    rows = body.get("rows", [])
    try:
        data = manager.create_table(type_name, table_name, headers, rows)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "created", "data": data}


@router.get("/status/types/{type_name}/tables/{table_name}")
def get_table(
    type_name: str,
    table_name: str,
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Return a single table's CSV data (headers + rows)."""
    try:
        return manager.get_table(type_name, table_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/status/types/{type_name}/tables/{table_name}")
def save_table(
    type_name: str,
    table_name: str,
    body: dict,
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Save (overwrite) a table's CSV data."""
    headers = body.get("headers", [])
    rows = body.get("rows", [])
    try:
        data = manager.save_table(type_name, table_name, headers, rows)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "saved", "data": data}


@router.put("/status/types/{type_name}/tables/{table_name}/rename")
def rename_table(
    type_name: str,
    table_name: str,
    body: dict,
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Rename a table."""
    new_name = body.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New table name is required")
    try:
        data = manager.rename_table(type_name, table_name, new_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "renamed", "data": data}


@router.delete("/status/types/{type_name}/tables/{table_name}")
def delete_table(
    type_name: str,
    table_name: str,
    session_id: str = "default",
    manager: StatusManager = Depends(get_session_status_manager),
) -> dict:
    """Delete a table."""
    try:
        manager.delete_table(type_name, table_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "deleted", "name": table_name}
