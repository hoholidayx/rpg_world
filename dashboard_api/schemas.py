"""FastAPI request schemas for API routes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from rpg_core.session.manager import DEFAULT_SESSION_ID


class _BaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceNameBody(_BaseSchema):
    name: str


class SessionIdBody(_BaseSchema):
    session_id: str


class SessionCloneBody(_BaseSchema):
    target_session_id: str


class ChatMessageBody(_BaseSchema):
    session_id: str = DEFAULT_SESSION_ID
    message: str


class ChatCommandBody(_BaseSchema):
    session_id: str = DEFAULT_SESSION_ID
    command: str


class StatusNameBody(_BaseSchema):
    name: str


class StatusTableCreateBody(_BaseSchema):
    name: str
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class StatusTableSaveBody(_BaseSchema):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
