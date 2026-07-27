"""Session Composer mode, narrative-style, and quick-reply APIs."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from play_api.composition import session_composer_service
from play_api.routers._data_errors import data_integrity_conflict
from play_api.routers._locator import resolve_session_or_404
from rpg_core.rp_modules.message_mode import MessageModeOption
from rpg_core.session.composer import SessionComposerApplicationService
from rpg_data.errors import DataIntegrityError
from rpg_data.model.composer import (
    NarrativeStyle,
    StoryNarrativeStyle,
    StoryQuickReply,
)

router = APIRouter(tags=["play-session-composer"])


class PlayTurnMode(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: Literal["neutral", "ic", "ooc", "gm"]
    short_name: str = Field(alias="shortName")
    sort_order: int = Field(alias="sortOrder")


class PlayNarrativeStyle(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    workspace_id: str = Field(alias="workspaceId")
    name: str
    prompt: str
    sort_order: int = Field(alias="sortOrder")
    version: int
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PlayNarrativeStyleCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    prompt: str = ""
    sort_order: int = Field(default=0, alias="sortOrder")

    @field_validator("name")
    @classmethod
    def _name_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class PlayNarrativeStylePatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str | None = None
    prompt: str | None = None
    sort_order: int | None = Field(default=None, alias="sortOrder")

    @field_validator("name")
    @classmethod
    def _optional_name_required(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class PlayStoryNarrativeStyle(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mount_id: int = Field(alias="mountId")
    narrative_style_id: int = Field(alias="narrativeStyleId")
    name: str
    prompt: str
    is_base: bool = Field(alias="isBase")
    sort_order: int = Field(alias="sortOrder")
    version: int


class PlayStoryStyleMountRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    narrative_style_id: int = Field(alias="narrativeStyleId", gt=0)


class PlayStoryBaseStyleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    mount_id: int | None = Field(alias="mountId", gt=0)


class PlayQuickReply(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    title: str
    message: str
    sort_order: int = Field(alias="sortOrder")
    enabled: bool
    version: int
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PlayQuickReplyCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str
    message: str
    sort_order: int = Field(default=0, alias="sortOrder")
    enabled: bool = True

    @field_validator("title", "message")
    @classmethod
    def _required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title and message must not be empty")
        return value


class PlayQuickReplyPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str | None = None
    message: str | None = None
    sort_order: int | None = Field(default=None, alias="sortOrder")
    enabled: bool | None = None

    @field_validator("title", "message")
    @classmethod
    def _optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("title and message must not be empty")
        return value


class PlaySessionComposer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    workspace_id: str = Field(alias="workspaceId")
    story_id: int = Field(alias="storyId")
    modes: list[PlayTurnMode]
    narrative_styles: list[PlayStoryNarrativeStyle] = Field(alias="narrativeStyles")
    base_narrative_style_id: int | None = Field(alias="baseNarrativeStyleId")
    quick_replies: list[PlayQuickReply] = Field(alias="quickReplies")


def _mode_response(item: MessageModeOption) -> PlayTurnMode:
    return PlayTurnMode(
        mode=item.mode.value,
        shortName=item.short_name,
        sortOrder=item.sort_order,
    )


def _style_response(item: NarrativeStyle) -> PlayNarrativeStyle:
    return PlayNarrativeStyle(
        id=item.id,
        workspaceId=item.workspace_id,
        name=item.name,
        prompt=item.prompt,
        sortOrder=item.sort_order,
        version=item.version,
        createdAt=item.created_at or None,
        updatedAt=item.updated_at or None,
    )


def _story_style_response(item: StoryNarrativeStyle) -> PlayStoryNarrativeStyle:
    return PlayStoryNarrativeStyle(
        mountId=item.id,
        narrativeStyleId=item.narrative_style_id,
        name=item.name,
        prompt=item.prompt,
        isBase=item.is_base,
        sortOrder=item.sort_order,
        version=item.version,
    )


def _quick_reply_response(item: StoryQuickReply) -> PlayQuickReply:
    return PlayQuickReply(
        id=item.id,
        title=item.title,
        message=item.message,
        sortOrder=item.sort_order,
        enabled=item.enabled,
        version=item.version,
        createdAt=item.created_at or None,
        updatedAt=item.updated_at or None,
    )


def _composer_service() -> SessionComposerApplicationService:
    return session_composer_service()


@router.get(
    "/workspaces/{workspace_id}/narrative-styles",
    response_model=list[PlayNarrativeStyle],
)
async def list_narrative_styles(workspace_id: str) -> list[PlayNarrativeStyle]:
    items = _composer_service().list_styles(workspace_id)
    if items is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return [_style_response(item) for item in items]


@router.post(
    "/workspaces/{workspace_id}/narrative-styles",
    response_model=PlayNarrativeStyle,
)
async def create_narrative_style(
    workspace_id: str,
    body: PlayNarrativeStyleCreate,
) -> PlayNarrativeStyle:
    try:
        item = _composer_service().create_style(
            workspace_id,
            name=body.name,
            prompt=body.prompt,
            sort_order=body.sort_order,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="narrative_style.create",
            workspace_id=workspace_id,
        ) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _style_response(item)


@router.patch(
    "/workspaces/{workspace_id}/narrative-styles/{style_id}",
    response_model=PlayNarrativeStyle,
)
async def update_narrative_style(
    workspace_id: str,
    style_id: int,
    body: PlayNarrativeStylePatch,
) -> PlayNarrativeStyle:
    try:
        item = _composer_service().update_style(
            workspace_id,
            style_id,
            name=body.name,
            prompt=body.prompt,
            sort_order=body.sort_order,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="narrative_style.update",
            workspace_id=workspace_id,
            resource_id=style_id,
        ) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="narrative style not found")
    return _style_response(item)


@router.delete("/workspaces/{workspace_id}/narrative-styles/{style_id}", status_code=204)
async def delete_narrative_style(workspace_id: str, style_id: int) -> Response:
    try:
        deleted = _composer_service().delete_style(workspace_id, style_id)
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="narrative_style.delete",
            workspace_id=workspace_id,
            resource_id=style_id,
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="narrative style not found")
    return Response(status_code=204)


@router.get(
    "/workspaces/{workspace_id}/stories/{story_id}/narrative-styles",
    response_model=list[PlayStoryNarrativeStyle],
)
async def list_story_narrative_styles(
    workspace_id: str,
    story_id: int,
) -> list[PlayStoryNarrativeStyle]:
    items = _composer_service().list_story_styles(workspace_id, story_id)
    if items is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return [_story_style_response(item) for item in items]


@router.post(
    "/workspaces/{workspace_id}/stories/{story_id}/narrative-styles",
    response_model=PlayStoryNarrativeStyle,
)
async def mount_story_narrative_style(
    workspace_id: str,
    story_id: int,
    body: PlayStoryStyleMountRequest,
) -> PlayStoryNarrativeStyle:
    try:
        item = _composer_service().mount_story_style(
            workspace_id,
            story_id,
            body.narrative_style_id,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="story_narrative_style.mount",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=body.narrative_style_id,
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _story_style_response(item)


@router.delete(
    "/workspaces/{workspace_id}/stories/{story_id}/narrative-styles/{mount_id}",
    status_code=204,
)
async def unmount_story_narrative_style(
    workspace_id: str,
    story_id: int,
    mount_id: int,
) -> Response:
    try:
        deleted = _composer_service().unmount_story_style(
            workspace_id,
            story_id,
            mount_id,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="story_narrative_style.unmount",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=mount_id,
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="story narrative style mount not found")
    return Response(status_code=204)


@router.patch(
    "/workspaces/{workspace_id}/stories/{story_id}/narrative-styles/base",
    response_model=PlayStoryNarrativeStyle | None,
)
async def set_story_base_narrative_style(
    workspace_id: str,
    story_id: int,
    body: PlayStoryBaseStyleRequest,
) -> PlayStoryNarrativeStyle | None:
    try:
        item = _composer_service().set_story_base_style(
            workspace_id,
            story_id,
            body.mount_id,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="story_narrative_style.set_base",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=body.mount_id,
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _story_style_response(item) if item is not None else None


@router.get(
    "/workspaces/{workspace_id}/stories/{story_id}/quick-replies",
    response_model=list[PlayQuickReply],
)
async def list_quick_replies(workspace_id: str, story_id: int) -> list[PlayQuickReply]:
    items = _composer_service().list_quick_replies(workspace_id, story_id)
    if items is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return [_quick_reply_response(item) for item in items]


@router.post(
    "/workspaces/{workspace_id}/stories/{story_id}/quick-replies",
    response_model=PlayQuickReply,
)
async def create_quick_reply(
    workspace_id: str,
    story_id: int,
    body: PlayQuickReplyCreate,
) -> PlayQuickReply:
    try:
        item = _composer_service().create_quick_reply(
            workspace_id,
            story_id,
            title=body.title,
            message=body.message,
            sort_order=body.sort_order,
            enabled=body.enabled,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="quick_reply.create",
            workspace_id=workspace_id,
            story_id=story_id,
        ) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _quick_reply_response(item)


@router.patch(
    "/workspaces/{workspace_id}/stories/{story_id}/quick-replies/{reply_id}",
    response_model=PlayQuickReply,
)
async def update_quick_reply(
    workspace_id: str,
    story_id: int,
    reply_id: int,
    body: PlayQuickReplyPatch,
) -> PlayQuickReply:
    try:
        item = _composer_service().update_quick_reply(
            workspace_id,
            story_id,
            reply_id,
            title=body.title,
            message=body.message,
            sort_order=body.sort_order,
            enabled=body.enabled,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="quick_reply.update",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=reply_id,
        ) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="quick reply not found")
    return _quick_reply_response(item)


@router.delete(
    "/workspaces/{workspace_id}/stories/{story_id}/quick-replies/{reply_id}",
    status_code=204,
)
async def delete_quick_reply(
    workspace_id: str,
    story_id: int,
    reply_id: int,
) -> Response:
    try:
        deleted = _composer_service().delete_quick_reply(
            workspace_id,
            story_id,
            reply_id,
        )
    except DataIntegrityError as exc:
        raise data_integrity_conflict(
            exc,
            operation="quick_reply.delete",
            workspace_id=workspace_id,
            story_id=story_id,
            resource_id=reply_id,
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="quick reply not found")
    return Response(status_code=204)


@router.get("/sessions/{session_id}/composer", response_model=PlaySessionComposer)
async def get_session_composer(session_id: str) -> PlaySessionComposer:
    session_payload = await resolve_session_or_404(session_id)
    agent_session_id = str(session_payload["id"])
    snapshot = _composer_service().get_snapshot(agent_session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="session not found")
    return PlaySessionComposer(
        sessionId=snapshot.session_id,
        workspaceId=snapshot.workspace_id,
        storyId=snapshot.story_id,
        modes=[_mode_response(item) for item in snapshot.modes],
        narrativeStyles=[
            _story_style_response(item) for item in snapshot.narrative_styles
        ],
        baseNarrativeStyleId=snapshot.base_narrative_style_id,
        quickReplies=[_quick_reply_response(item) for item in snapshot.quick_replies],
    )
