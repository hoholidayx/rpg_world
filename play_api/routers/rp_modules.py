"""Generic built-in RP Module catalog, Story mounts and Session overrides."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from commons.types import JsonObject, JsonValue
from play_api.composition import rp_module_service
from play_api.routers._locator import resolve_session_or_404
from rpg_core.rp_modules.constants import RP_MODULE_NARRATIVE_OUTCOME_NAME
from rpg_core.rp_modules.application import RPModuleApplicationService
from rpg_core.rp_modules.models import RPModuleSelection, RPModuleSelectionSnapshot
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_DEFINITIONS

router = APIRouter(tags=["play-rp-modules"])


class PlayRPModuleCatalogItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    module_name: str = Field(alias="moduleName")
    display_name: str = Field(alias="displayName")
    description: str
    sort_order: int = Field(alias="sortOrder")
    config_version: int = Field(alias="configVersion")
    default_story_enabled: bool = Field(alias="defaultStoryEnabled")
    configurable_fields: list[str] = Field(alias="configurableFields")
    outcome_definitions: list[dict[str, str]] | None = Field(
        default=None,
        alias="outcomeDefinitions",
    )


class PlayRPModuleCatalog(BaseModel):
    modules: list[PlayRPModuleCatalogItem]


class PlayRPModuleConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    module_name: str = Field(alias="moduleName")
    display_name: str = Field(alias="displayName")
    description: str
    sort_order: int = Field(alias="sortOrder")
    global_enabled: bool = Field(alias="globalEnabled")
    system_enabled: bool = Field(alias="systemEnabled")
    story_mounted: bool = Field(alias="storyMounted")
    story_enabled: bool = Field(alias="storyEnabled")
    session_enabled_override: bool | None = Field(alias="sessionEnabledOverride")
    effective_enabled: bool = Field(alias="effectiveEnabled")
    system_config: JsonObject = Field(alias="systemConfig")
    story_config: JsonObject = Field(alias="storyConfig")
    session_config: JsonObject = Field(alias="sessionConfig")
    effective_config: JsonObject = Field(alias="effectiveConfig")
    config_sources: dict[str, str] = Field(alias="configSources")
    outcome_definitions: list[dict[str, str]] | None = Field(
        default=None,
        alias="outcomeDefinitions",
    )


class PlayRPModuleList(BaseModel):
    modules: list[PlayRPModuleConfig]


class PlayStoryRPModulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    config: JsonObject | None = None


class PlaySessionRPModulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    config: JsonObject | None = None


def _service() -> RPModuleApplicationService:
    return rp_module_service()


def _selection_response(
    snapshot: RPModuleSelectionSnapshot,
    selected: RPModuleSelection,
) -> PlayRPModuleConfig:
    return PlayRPModuleConfig(
        moduleName=selected.name,
        displayName=selected.display_name,
        description=selected.description,
        sortOrder=selected.sort_order,
        globalEnabled=snapshot.global_enabled,
        systemEnabled=selected.system_enabled,
        storyMounted=selected.story_mounted,
        storyEnabled=selected.story_enabled,
        sessionEnabledOverride=selected.session_enabled_override,
        effectiveEnabled=selected.effective_enabled,
        systemConfig=_json_config(selected.system_config),
        storyConfig=_json_config(selected.story_config),
        sessionConfig=_json_config(selected.session_config),
        effectiveConfig=_json_config(selected.effective_config),
        configSources=dict(selected.config_sources),
        outcomeDefinitions=(
            [definition.to_public_dict() for definition in NARRATIVE_OUTCOME_DEFINITIONS]
            if selected.name == RP_MODULE_NARRATIVE_OUTCOME_NAME
            else None
        ),
    )


def _json_config(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _json_config(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_config(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"RP module config contains a non-JSON value: {type(value).__name__}")


def _list_response(snapshot: RPModuleSelectionSnapshot) -> PlayRPModuleList:
    return PlayRPModuleList(
        modules=[_selection_response(snapshot, selected) for selected in snapshot.modules]
    )


@router.get("/rp-modules/catalog", response_model=PlayRPModuleCatalog)
async def get_rp_module_catalog() -> PlayRPModuleCatalog:
    service = _service()
    definitions = {item.name: item for item in service.definitions()}
    rows = service.list_catalog()
    return PlayRPModuleCatalog(modules=[
        PlayRPModuleCatalogItem(
            moduleName=row.module_name,
            displayName=row.display_name,
            description=row.description,
            sortOrder=row.sort_order,
            configVersion=row.config_version,
            defaultStoryEnabled=row.default_story_enabled,
            configurableFields=list(definitions[row.module_name].configurable_fields),
            outcomeDefinitions=(
                [definition.to_public_dict() for definition in NARRATIVE_OUTCOME_DEFINITIONS]
                if row.module_name == RP_MODULE_NARRATIVE_OUTCOME_NAME
                else None
            ),
        )
        for row in rows
        if row.module_name in definitions
    ])


@router.get(
    "/workspaces/{workspace_id}/stories/{story_id}/rp-modules",
    response_model=PlayRPModuleList,
)
async def get_story_rp_modules(workspace_id: str, story_id: int) -> PlayRPModuleList:
    snapshot = _service().resolve_story_snapshot(workspace_id, story_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _list_response(snapshot)


@router.patch(
    "/workspaces/{workspace_id}/stories/{story_id}/rp-modules/{module_name}",
    response_model=PlayRPModuleConfig,
)
async def patch_story_rp_module(
    workspace_id: str,
    story_id: int,
    module_name: str,
    payload: PlayStoryRPModulePatch,
) -> PlayRPModuleConfig:
    service = _service()
    definition = service.definition(module_name)
    if definition is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    name = definition.name
    try:
        snapshot = service.patch_story_module(
            workspace_id,
            story_id,
            name,
            enabled=payload.enabled,
            config=payload.config,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    selected = snapshot.get(name) if snapshot is not None else None
    if snapshot is None or selected is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    return _selection_response(snapshot, selected)


@router.get(
    "/sessions/{session_id}/rp-modules",
    response_model=PlayRPModuleList,
)
async def get_session_rp_modules(session_id: str) -> PlayRPModuleList:
    await resolve_session_or_404(session_id)
    return _list_response(_service().resolve_snapshot(session_id))


@router.patch(
    "/sessions/{session_id}/rp-modules/{module_name}",
    response_model=PlayRPModuleConfig,
)
async def patch_session_rp_module(
    session_id: str,
    module_name: str,
    payload: PlaySessionRPModulePatch,
) -> PlayRPModuleConfig:
    await resolve_session_or_404(session_id)
    service = _service()
    definition = service.definition(module_name)
    if definition is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    name = definition.name
    try:
        snapshot = service.patch_session_override(
            session_id,
            name,
            enabled=payload.enabled,
            replace_enabled="enabled" in payload.model_fields_set,
            config=payload.config,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    selected = snapshot.get(name)
    if selected is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    return _selection_response(snapshot, selected)


@router.delete(
    "/sessions/{session_id}/rp-modules/{module_name}",
    response_model=PlayRPModuleConfig,
)
async def delete_session_rp_module_override(
    session_id: str,
    module_name: str,
) -> PlayRPModuleConfig:
    await resolve_session_or_404(session_id)
    service = _service()
    definition = service.definition(module_name)
    if definition is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    name = definition.name
    snapshot = service.clear_session_override(
        session_id,
        name,
    )
    selected = snapshot.get(name)
    if selected is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    return _selection_response(snapshot, selected)
