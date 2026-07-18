"""Generic built-in RP Module catalog, Story mounts and Session overrides."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from play_api.routers._locator import resolve_session_or_404
from rpg_core.rp_modules.constants import RP_MODULE_NARRATIVE_OUTCOME_NAME
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.rp_modules.models import RPModuleSelection, RPModuleSelectionSnapshot
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_DEFINITIONS
from rpg_core.settings import settings
from rpg_data.services import get_data_service_gateway

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
    system_config: dict[str, Any] = Field(alias="systemConfig")
    story_config: dict[str, Any] = Field(alias="storyConfig")
    session_config: dict[str, Any] = Field(alias="sessionConfig")
    effective_config: dict[str, Any] = Field(alias="effectiveConfig")
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
    config: dict[str, Any] | None = None


class PlaySessionRPModulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    config: dict[str, Any] | None = None


def _registry() -> RPModuleRegistry:
    return RPModuleRegistry(settings=settings.rp_module_settings)


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


def _json_config(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _json_config(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_config(item) for item in value]
    return value


def _list_response(snapshot: RPModuleSelectionSnapshot) -> PlayRPModuleList:
    return PlayRPModuleList(
        modules=[_selection_response(snapshot, selected) for selected in snapshot.modules]
    )


@router.get("/rp-modules/catalog", response_model=PlayRPModuleCatalog)
async def get_rp_module_catalog() -> PlayRPModuleCatalog:
    registry = _registry()
    definitions = {item.name: item for item in registry.definitions()}
    rows = get_data_service_gateway().rp_modules.list_catalog()
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
    snapshot = _registry().resolve_story_snapshot(workspace_id, story_id)
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
    registry = _registry()
    if registry.definition(module_name) is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    service = get_data_service_gateway().rp_modules
    current = service.get_story_module(workspace_id, story_id, module_name)
    if current is None:
        if service.list_story_modules(workspace_id, story_id) is None:
            raise HTTPException(status_code=404, detail="story not found in workspace")
        current_enabled = True
        current_config: dict[str, object] = {}
    else:
        current_enabled = current.enabled
        current_config = dict(current.config)
    try:
        config = registry.validate_config_patch(
            module_name,
            payload.config if payload.config is not None else current_config,
        )
        service.set_story_module(
            workspace_id,
            story_id,
            module_name,
            enabled=current_enabled if payload.enabled is None else payload.enabled,
            config=config,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    snapshot = registry.resolve_story_snapshot(workspace_id, story_id)
    selected = snapshot.get(module_name) if snapshot is not None else None
    if snapshot is None or selected is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    return _selection_response(snapshot, selected)


@router.get(
    "/sessions/{session_id}/rp-modules",
    response_model=PlayRPModuleList,
)
async def get_session_rp_modules(session_id: str) -> PlayRPModuleList:
    await resolve_session_or_404(session_id)
    return _list_response(_registry().resolve_snapshot(session_id))


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
    registry = _registry()
    if registry.definition(module_name) is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    service = get_data_service_gateway().rp_modules
    current = service.get_session_override(session_id, module_name)
    current_config = dict(current.config) if current is not None else {}
    enabled = current.enabled if current is not None else None
    if "enabled" in payload.model_fields_set:
        enabled = payload.enabled
    try:
        config = registry.validate_config_patch(
            module_name,
            payload.config if payload.config is not None else current_config,
        )
        service.set_session_override(
            session_id,
            module_name,
            enabled=enabled,
            config=config,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    snapshot = registry.resolve_snapshot(session_id)
    selected = snapshot.get(module_name)
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
    if _registry().definition(module_name) is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    get_data_service_gateway().rp_modules.clear_session_override(
        session_id,
        module_name,
    )
    snapshot = _registry().resolve_snapshot(session_id)
    selected = snapshot.get(module_name)
    if selected is None:
        raise HTTPException(status_code=404, detail="RP module not found")
    return _selection_response(snapshot, selected)
