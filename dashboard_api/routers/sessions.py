"""Session routes — CRUD for sessions under an explicit workspace."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent_service.client import AgentClientError
from dashboard_api.schemas import SessionCloneBody, SessionIdBody
from dashboard_api.routers import chat as chat_router
from rpg_core.session import SessionManager
from rpg_core.utils.path_utils import resolve_api_workspace

router = APIRouter(tags=["session"])


def _require_valid_session_id(session_id: str, field_name: str = "session_id") -> str:
    if not session_id:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    try:
        return SessionManager.validate_session_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_ws(workspace: str) -> str:
    """Resolve workspace, defaulting to the API default when empty."""
    return resolve_api_workspace(workspace)


@router.get("/workspaces/{workspace:path}/sessions")
async def list_sessions(workspace: str) -> dict:
    """Return all session IDs for the given workspace."""
    try:
        return await chat_router._get_agent_client().list_sessions(_resolve_ws(workspace), "default")
    except AgentClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workspaces/{workspace:path}/sessions")
async def create_session(workspace: str, body: SessionIdBody) -> dict:
    """Create a new session under the given workspace."""
    ws = _resolve_ws(workspace)
    session_id = _require_valid_session_id(body.session_id.strip())
    try:
        return await chat_router._get_agent_client().create_session(ws, session_id)
    except AgentClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/workspaces/{workspace:path}/sessions/{session_id}")
async def delete_session(workspace: str, session_id: str) -> dict:
    """Delete a session and all its data."""
    ws = _resolve_ws(workspace)
    session_id = _require_valid_session_id(session_id)
    try:
        return await chat_router._get_agent_client().delete_session(ws, session_id)
    except AgentClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workspaces/{workspace:path}/sessions/{session_id}/clone")
async def clone_session(workspace: str, session_id: str, body: SessionCloneBody) -> dict:
    """Clone a session's data to a new session ID."""
    ws = _resolve_ws(workspace)
    session_id = _require_valid_session_id(session_id)
    target_id = _require_valid_session_id(body.target_session_id.strip(), field_name="target_session_id")
    try:
        return await chat_router._get_agent_client().clone_session(ws, session_id, target_id)
    except AgentClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
