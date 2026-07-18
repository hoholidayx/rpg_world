"""Session Composer mode, narrative-style, and quick-reply APIs."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from peewee import IntegrityError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from play_api.routers._locator import resolve_session_or_404
from rpg_core.agent.turn.models import normalize_turn_mode
from rpg_data import models
from rpg_data.services import get_data_service_gateway

router = APIRouter(tags=["play-session-composer"])


class PlayTurnMode(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: Literal["ic", "ooc", "gm"]
    short_name: str = Field(alias="shortName")
    prompt: str
    sort_order: int = Field(alias="sortOrder")
    version: int


class PlayTurnModePatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    short_name: str = Field(alias="shortName")
    prompt: str

    @field_validator("short_name")
    @classmethod
    def _short_name_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("shortName must not be empty")
        return value


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


def _mode_response(item: models.WorkspaceTurnMode) -> PlayTurnMode:
    return PlayTurnMode(
        mode=normalize_turn_mode(item.mode).value,
        shortName=item.short_name,
        prompt=item.prompt,
        sortOrder=item.sort_order,
        version=item.version,
    )


def _style_response(item: models.NarrativeStyle) -> PlayNarrativeStyle:
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


def _story_style_response(item: models.StoryNarrativeStyle) -> PlayStoryNarrativeStyle:
    return PlayStoryNarrativeStyle(
        mountId=item.id,
        narrativeStyleId=item.narrative_style_id,
        name=item.name,
        prompt=item.prompt,
        isBase=item.is_base,
        sortOrder=item.sort_order,
        version=item.version,
    )


def _quick_reply_response(item: models.StoryQuickReply) -> PlayQuickReply:
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


def _composer_service():
    return get_data_service_gateway().session_composer


def _conflict(exc: IntegrityError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/workspaces/{workspace_id}/turn-modes", response_model=list[PlayTurnMode])
async def list_turn_modes(workspace_id: str) -> list[PlayTurnMode]:
    items = _composer_service().list_modes(workspace_id)
    if items is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return [_mode_response(item) for item in items]


@router.patch(
    "/workspaces/{workspace_id}/turn-modes/{mode}",
    response_model=PlayTurnMode,
)
async def update_turn_mode(
    workspace_id: str,
    mode: str,
    body: PlayTurnModePatch,
) -> PlayTurnMode:
    try:
        item = _composer_service().update_mode(
            workspace_id,
            mode,
            short_name=body.short_name,
            prompt=body.prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _mode_response(item)


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
    except IntegrityError as exc:
        raise _conflict(exc) from exc
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
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="narrative style not found")
    return _style_response(item)


@router.delete("/workspaces/{workspace_id}/narrative-styles/{style_id}", status_code=204)
async def delete_narrative_style(workspace_id: str, style_id: int) -> Response:
    deleted = _composer_service().delete_style(workspace_id, style_id)
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
    deleted = _composer_service().unmount_story_style(workspace_id, story_id, mount_id)
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
    except IntegrityError as exc:
        raise _conflict(exc) from exc
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
    except IntegrityError as exc:
        raise _conflict(exc) from exc
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
    deleted = _composer_service().delete_quick_reply(workspace_id, story_id, reply_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="quick reply not found")
    return Response(status_code=204)


@router.get("/sessions/{session_id}/composer", response_model=PlaySessionComposer)
async def get_session_composer(session_id: str) -> PlaySessionComposer:
    session_payload = await resolve_session_or_404(session_id)
    agent_session_id = str(session_payload["id"])
    session = get_data_service_gateway().catalog.get_session(agent_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    service = _composer_service()
    modes = service.list_modes(session.workspace_id) or []
    styles = service.list_story_styles(session.workspace_id, session.story_id) or []
    quick_replies = service.list_quick_replies(
        session.workspace_id,
        session.story_id,
        enabled_only=True,
    ) or []
    base_style = next((item for item in styles if item.is_base), None)
    return PlaySessionComposer(
        sessionId=session.id,
        workspaceId=session.workspace_id,
        storyId=session.story_id,
        modes=[_mode_response(item) for item in modes],
        narrativeStyles=[_story_style_response(item) for item in styles],
        baseNarrativeStyleId=(
            base_style.narrative_style_id if base_style is not None else None
        ),
        quickReplies=[_quick_reply_response(item) for item in quick_replies],
    )
