"""Story plot definitions and Session scheduling-runtime inspection."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from commons.scene_time import SceneTime
from play_api.routers._locator import resolve_session_or_404
from rpg_data import models
from rpg_data.services import PlotDefinitionInUseError, get_data_service_gateway

router = APIRouter(tags=["play-plot-scheduling"])
_T = TypeVar("_T")


class SceneTimePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=1)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)

    def to_scene_time(self) -> SceneTime:
        return SceneTime(**self.model_dump())


class PlotPoolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    description: str = ""
    selection_mode: str = Field(default=models.PLOT_POOL_RANDOM, alias="selectionMode")
    priority: int = 0
    enabled: bool = True


class PlotPoolPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = None
    description: str | None = None
    selection_mode: str | None = Field(default=None, alias="selectionMode")
    priority: int | None = None
    enabled: bool | None = None


class PlotPoolResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    story_id: int = Field(alias="storyId")
    name: str
    description: str
    selection_mode: str = Field(alias="selectionMode")
    priority: int
    enabled: bool
    version: int
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class PlotEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pool_id: int = Field(alias="poolId", gt=0)
    title: str
    directive: str
    description: str = ""
    suitability_hint: str = Field(default="", alias="suitabilityHint")
    dispatch_mode: str = Field(default=models.PLOT_DISPATCH_SOFT, alias="dispatchMode")
    scheduled_time: SceneTimePayload | None = Field(default=None, alias="scheduledTime")
    position: int | None = Field(default=None, ge=0)
    enabled: bool = True
    allow_repeat: bool = Field(default=False, alias="allowRepeat")
    repeat_cooldown_minutes: int = Field(
        default=0,
        alias="repeatCooldownMinutes",
        ge=0,
    )


class PlotEventPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pool_id: int | None = Field(default=None, alias="poolId", gt=0)
    title: str | None = None
    directive: str | None = None
    description: str | None = None
    suitability_hint: str | None = Field(default=None, alias="suitabilityHint")
    dispatch_mode: str | None = Field(default=None, alias="dispatchMode")
    scheduled_time: SceneTimePayload | None = Field(default=None, alias="scheduledTime")
    position: int | None = Field(default=None, ge=0)
    enabled: bool | None = None
    allow_repeat: bool | None = Field(default=None, alias="allowRepeat")
    repeat_cooldown_minutes: int | None = Field(
        default=None,
        alias="repeatCooldownMinutes",
        ge=0,
    )


class PlotEventResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    story_id: int = Field(alias="storyId")
    pool_id: int = Field(alias="poolId")
    title: str
    directive: str
    description: str
    suitability_hint: str = Field(alias="suitabilityHint")
    dispatch_mode: str = Field(alias="dispatchMode")
    scheduled_time: SceneTimePayload | None = Field(alias="scheduledTime")
    position: int
    enabled: bool
    allow_repeat: bool = Field(alias="allowRepeat")
    repeat_cooldown_minutes: int = Field(alias="repeatCooldownMinutes")
    version: int
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class PlotOutlineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    priority: int = 0
    enabled: bool = True


class PlotOutlinePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    priority: int | None = None
    enabled: bool | None = None


class PlotNodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    event_id: int = Field(alias="eventId", gt=0)
    scheduled_time: SceneTimePayload = Field(alias="scheduledTime")
    dispatch_mode: str = Field(default=models.PLOT_DISPATCH_SOFT, alias="dispatchMode")
    position: int | None = Field(default=None, ge=0)
    enabled: bool = True


class PlotNodePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    event_id: int | None = Field(default=None, alias="eventId", gt=0)
    scheduled_time: SceneTimePayload | None = Field(default=None, alias="scheduledTime")
    dispatch_mode: str | None = Field(default=None, alias="dispatchMode")
    position: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class PlotNodeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    story_id: int = Field(alias="storyId")
    outline_id: int = Field(alias="outlineId")
    event_id: int = Field(alias="eventId")
    scheduled_time: SceneTimePayload = Field(alias="scheduledTime")
    dispatch_mode: str = Field(alias="dispatchMode")
    position: int
    enabled: bool
    version: int
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class PlotOutlineResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    story_id: int = Field(alias="storyId")
    name: str
    description: str
    priority: int
    enabled: bool
    nodes: list[PlotNodeResponse]
    version: int
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class PlotScheduleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    story_id: int = Field(alias="storyId")
    pools: list[PlotPoolResponse]
    events: list[PlotEventResponse]
    outlines: list[PlotOutlineResponse]


class ReorderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[int]


class PlotOverridePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disabled: bool


class PlotOverridesResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    disabled_event_ids: list[int] = Field(alias="disabledEventIds")
    disabled_outline_node_ids: list[int] = Field(alias="disabledOutlineNodeIds")


class PlotDecisionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    session_id: str = Field(alias="sessionId")
    turn_id: int = Field(alias="turnId")
    source_kind: str = Field(alias="sourceKind")
    source_id: int = Field(alias="sourceId")
    event_id: int = Field(alias="eventId")
    container_id: int = Field(alias="containerId")
    decision_status: str = Field(alias="decisionStatus")
    dispatch_mode: str = Field(alias="dispatchMode")
    scene_time: SceneTimePayload = Field(alias="sceneTime")
    scene_time_ordinal: int = Field(alias="sceneTimeOrdinal")
    event_snapshot: dict[str, Any] = Field(alias="eventSnapshot")
    reason: str
    error_code: str = Field(alias="errorCode")
    error_message: str = Field(alias="errorMessage")
    created_at: str = Field(alias="createdAt")


class SessionPlotScheduleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    scene_time: SceneTimePayload | None = Field(alias="sceneTime")
    scene_time_error: str = Field(alias="sceneTimeError")
    schedule: PlotScheduleResponse
    overrides: PlotOverridesResponse
    decisions: list[PlotDecisionResponse]
    next_before_id: int | None = Field(alias="nextBeforeId")


def _service_call(call: Callable[[], _T]) -> _T:
    try:
        return call()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlotDefinitionInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _time_response(value: SceneTime | None) -> SceneTimePayload | None:
    return SceneTimePayload(**value.to_dict()) if value is not None else None


def _pool_response(value: models.StoryPlotEventPool) -> PlotPoolResponse:
    return PlotPoolResponse(
        id=value.id,
        storyId=value.story_id,
        name=value.name,
        description=value.description,
        selectionMode=value.selection_mode,
        priority=value.priority,
        enabled=value.enabled,
        version=value.version,
        createdAt=value.created_at,
        updatedAt=value.updated_at,
    )


def _event_response(value: models.StoryPlotEvent) -> PlotEventResponse:
    return PlotEventResponse(
        id=value.id,
        storyId=value.story_id,
        poolId=value.pool_id,
        title=value.title,
        directive=value.directive,
        description=value.description,
        suitabilityHint=value.suitability_hint,
        dispatchMode=value.dispatch_mode,
        scheduledTime=_time_response(value.scheduled_time),
        position=value.position,
        enabled=value.enabled,
        allowRepeat=value.allow_repeat,
        repeatCooldownMinutes=value.repeat_cooldown_minutes,
        version=value.version,
        createdAt=value.created_at,
        updatedAt=value.updated_at,
    )


def _node_response(value: models.StoryPlotOutlineNode) -> PlotNodeResponse:
    return PlotNodeResponse(
        id=value.id,
        storyId=value.story_id,
        outlineId=value.outline_id,
        eventId=value.event_id,
        scheduledTime=_time_response(value.scheduled_time),
        dispatchMode=value.dispatch_mode,
        position=value.position,
        enabled=value.enabled,
        version=value.version,
        createdAt=value.created_at,
        updatedAt=value.updated_at,
    )


def _outline_response(value: models.StoryPlotOutline) -> PlotOutlineResponse:
    return PlotOutlineResponse(
        id=value.id,
        storyId=value.story_id,
        name=value.name,
        description=value.description,
        priority=value.priority,
        enabled=value.enabled,
        nodes=[_node_response(node) for node in value.nodes],
        version=value.version,
        createdAt=value.created_at,
        updatedAt=value.updated_at,
    )


def _schedule_response(value: models.StoryPlotSchedule) -> PlotScheduleResponse:
    return PlotScheduleResponse(
        storyId=value.story_id,
        pools=[_pool_response(pool) for pool in value.pools],
        events=[_event_response(event) for event in value.events],
        outlines=[_outline_response(outline) for outline in value.outlines],
    )


def _overrides_response(value: models.SessionPlotOverrides) -> PlotOverridesResponse:
    return PlotOverridesResponse(
        sessionId=value.session_id,
        disabledEventIds=sorted(value.disabled_event_ids),
        disabledOutlineNodeIds=sorted(value.disabled_outline_node_ids),
    )


def _decision_response(
    value: models.SessionPlotScheduleDecision,
) -> PlotDecisionResponse:
    return PlotDecisionResponse(
        id=value.id,
        sessionId=value.session_id,
        turnId=value.turn_id,
        sourceKind=value.source_kind,
        sourceId=value.source_id,
        eventId=value.event_id,
        containerId=value.container_id,
        decisionStatus=value.decision_status,
        dispatchMode=value.dispatch_mode,
        sceneTime=_time_response(value.scene_time),
        sceneTimeOrdinal=value.scene_time_ordinal,
        eventSnapshot=dict(value.event_snapshot),
        reason=value.reason,
        errorCode=value.error_code,
        errorMessage=value.error_message,
        createdAt=value.created_at,
    )


def _event_values(payload: PlotEventInput | PlotEventPatch) -> dict[str, object]:
    values = payload.model_dump(exclude_unset=True)
    scheduled = values.get("scheduled_time")
    if isinstance(scheduled, dict):
        values["scheduled_time"] = SceneTime.from_mapping(scheduled)
    return values


def _node_values(payload: PlotNodeInput | PlotNodePatch) -> dict[str, object]:
    values = payload.model_dump(exclude_unset=True)
    scheduled = values.get("scheduled_time")
    if isinstance(scheduled, dict):
        values["scheduled_time"] = SceneTime.from_mapping(scheduled)
    return values


@router.get(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling",
    response_model=PlotScheduleResponse,
)
async def get_story_plot_schedule(
    workspace_id: str,
    story_id: int,
) -> PlotScheduleResponse:
    schedule = get_data_service_gateway().plot_scheduling.get_story_schedule(
        workspace_id,
        story_id,
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _schedule_response(schedule)


@router.post(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/pools",
    response_model=PlotPoolResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plot_pool(
    workspace_id: str,
    story_id: int,
    payload: PlotPoolInput,
) -> PlotPoolResponse:
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.create_pool(
        workspace_id,
        story_id,
        **payload.model_dump(),
    ))
    return _pool_response(value)


@router.patch(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/pools/{pool_id}",
    response_model=PlotPoolResponse,
)
async def update_plot_pool(
    workspace_id: str,
    story_id: int,
    pool_id: int,
    payload: PlotPoolPatch,
) -> PlotPoolResponse:
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.update_pool(
        workspace_id,
        story_id,
        pool_id,
        **payload.model_dump(exclude_unset=True),
    ))
    return _pool_response(value)


@router.delete(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/pools/{pool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plot_pool(workspace_id: str, story_id: int, pool_id: int) -> Response:
    _service_call(lambda: get_data_service_gateway().plot_scheduling.delete_pool(
        workspace_id, story_id, pool_id
    ))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/events",
    response_model=PlotEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plot_event(
    workspace_id: str,
    story_id: int,
    payload: PlotEventInput,
) -> PlotEventResponse:
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.create_event(
        workspace_id, story_id, **_event_values(payload)
    ))
    return _event_response(value)


@router.patch(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/events/{event_id}",
    response_model=PlotEventResponse,
)
async def update_plot_event(
    workspace_id: str,
    story_id: int,
    event_id: int,
    payload: PlotEventPatch,
) -> PlotEventResponse:
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.update_event(
        workspace_id, story_id, event_id, **_event_values(payload)
    ))
    return _event_response(value)


@router.delete(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plot_event(workspace_id: str, story_id: int, event_id: int) -> Response:
    _service_call(lambda: get_data_service_gateway().plot_scheduling.delete_event(
        workspace_id, story_id, event_id
    ))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/pools/{pool_id}/event-order",
    response_model=list[PlotEventResponse],
)
async def reorder_plot_events(
    workspace_id: str,
    story_id: int,
    pool_id: int,
    payload: ReorderPayload,
) -> list[PlotEventResponse]:
    values = _service_call(lambda: get_data_service_gateway().plot_scheduling.reorder_events(
        workspace_id, story_id, pool_id, payload.ids
    ))
    return [_event_response(value) for value in values]


@router.post(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/outlines",
    response_model=PlotOutlineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plot_outline(
    workspace_id: str,
    story_id: int,
    payload: PlotOutlineInput,
) -> PlotOutlineResponse:
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.create_outline(
        workspace_id, story_id, **payload.model_dump()
    ))
    return _outline_response(value)


@router.patch(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/outlines/{outline_id}",
    response_model=PlotOutlineResponse,
)
async def update_plot_outline(
    workspace_id: str,
    story_id: int,
    outline_id: int,
    payload: PlotOutlinePatch,
) -> PlotOutlineResponse:
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.update_outline(
        workspace_id,
        story_id,
        outline_id,
        **payload.model_dump(exclude_unset=True),
    ))
    return _outline_response(value)


@router.delete(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/outlines/{outline_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plot_outline(
    workspace_id: str,
    story_id: int,
    outline_id: int,
) -> Response:
    _service_call(lambda: get_data_service_gateway().plot_scheduling.delete_outline(
        workspace_id, story_id, outline_id
    ))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/outlines/{outline_id}/nodes",
    response_model=PlotNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plot_node(
    workspace_id: str,
    story_id: int,
    outline_id: int,
    payload: PlotNodeInput,
) -> PlotNodeResponse:
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.create_node(
        workspace_id, story_id, outline_id, **_node_values(payload)
    ))
    return _node_response(value)


@router.patch(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/outlines/{outline_id}/nodes/{node_id}",
    response_model=PlotNodeResponse,
)
async def update_plot_node(
    workspace_id: str,
    story_id: int,
    outline_id: int,
    node_id: int,
    payload: PlotNodePatch,
) -> PlotNodeResponse:
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.update_node(
        workspace_id,
        story_id,
        outline_id,
        node_id,
        **_node_values(payload),
    ))
    return _node_response(value)


@router.delete(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/outlines/{outline_id}/nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plot_node(
    workspace_id: str,
    story_id: int,
    outline_id: int,
    node_id: int,
) -> Response:
    _service_call(lambda: get_data_service_gateway().plot_scheduling.delete_node(
        workspace_id, story_id, outline_id, node_id
    ))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/workspaces/{workspace_id}/stories/{story_id}/plot-scheduling/outlines/{outline_id}/node-order",
    response_model=list[PlotNodeResponse],
)
async def reorder_plot_nodes(
    workspace_id: str,
    story_id: int,
    outline_id: int,
    payload: ReorderPayload,
) -> list[PlotNodeResponse]:
    values = _service_call(lambda: get_data_service_gateway().plot_scheduling.reorder_nodes(
        workspace_id, story_id, outline_id, payload.ids
    ))
    return [_node_response(value) for value in values]


@router.get(
    "/sessions/{session_id}/plot-scheduling",
    response_model=SessionPlotScheduleResponse,
)
async def get_session_plot_schedule(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=models.PLOT_DECISION_PAGE_SIZE_MAX),
    before_id: int | None = Query(default=None, alias="beforeId", gt=0),
) -> SessionPlotScheduleResponse:
    await resolve_session_or_404(session_id)
    service = get_data_service_gateway().plot_scheduling
    schedule, overrides = _service_call(lambda: service.get_session_schedule(session_id))
    decisions = _service_call(lambda: service.list_session_decisions(
        session_id,
        limit=limit + 1,
        before_id=before_id,
    ))
    has_more = len(decisions) > limit
    decisions = decisions[:limit]
    attrs = get_data_service_gateway().status.get_scene_attrs(session_id)
    scene_time: SceneTime | None = None
    scene_time_error = ""
    raw_time = str((attrs or {}).get("时间", "") or "").strip()
    if not raw_time:
        scene_time_error = "当前场景缺少非空“时间”字段"
    else:
        try:
            scene_time = SceneTime.parse(raw_time)
        except ValueError as exc:
            scene_time_error = str(exc)
    return SessionPlotScheduleResponse(
        sessionId=session_id,
        sceneTime=_time_response(scene_time),
        sceneTimeError=scene_time_error,
        schedule=_schedule_response(schedule),
        overrides=_overrides_response(overrides),
        decisions=[_decision_response(decision) for decision in decisions],
        nextBeforeId=(decisions[-1].id if has_more and decisions else None),
    )


@router.put(
    "/sessions/{session_id}/plot-scheduling/event-overrides/{event_id}",
    response_model=PlotOverridesResponse,
)
async def set_session_plot_event_override(
    session_id: str,
    event_id: int,
    payload: PlotOverridePayload,
) -> PlotOverridesResponse:
    await resolve_session_or_404(session_id)
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.set_session_event_disabled(
        session_id, event_id, payload.disabled
    ))
    return _overrides_response(value)


@router.put(
    "/sessions/{session_id}/plot-scheduling/node-overrides/{node_id}",
    response_model=PlotOverridesResponse,
)
async def set_session_plot_node_override(
    session_id: str,
    node_id: int,
    payload: PlotOverridePayload,
) -> PlotOverridesResponse:
    await resolve_session_or_404(session_id)
    value = _service_call(lambda: get_data_service_gateway().plot_scheduling.set_session_node_disabled(
        session_id, node_id, payload.disabled
    ))
    return _overrides_response(value)
