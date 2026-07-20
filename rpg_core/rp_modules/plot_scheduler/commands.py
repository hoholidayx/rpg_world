"""Typed commands for Plot Scheduler definition management."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from commons.scene_time import SceneTime
from rpg_data import models as data_models


class PlotPatchUnset(Enum):
    """Sentinel used to distinguish an omitted patch field from an explicit null."""

    VALUE = auto()


PLOT_PATCH_UNSET = PlotPatchUnset.VALUE


@dataclass(frozen=True)
class CreatePlotPoolCommand:
    workspace_id: str
    story_id: int
    name: str
    description: str = ""
    selection_mode: str = data_models.PLOT_POOL_RANDOM
    priority: int = 0
    enabled: bool = True


@dataclass(frozen=True)
class UpdatePlotPoolCommand:
    workspace_id: str
    story_id: int
    pool_id: int
    name: str | PlotPatchUnset = PLOT_PATCH_UNSET
    description: str | PlotPatchUnset = PLOT_PATCH_UNSET
    selection_mode: str | PlotPatchUnset = PLOT_PATCH_UNSET
    priority: int | PlotPatchUnset = PLOT_PATCH_UNSET
    enabled: bool | PlotPatchUnset = PLOT_PATCH_UNSET


@dataclass(frozen=True)
class CreatePlotEventCommand:
    workspace_id: str
    story_id: int
    pool_id: int
    title: str
    directive: str
    description: str = ""
    suitability_hint: str = ""
    dispatch_mode: str = data_models.PLOT_DISPATCH_SOFT
    scheduled_time: SceneTime | None = None
    position: int | None = None
    enabled: bool = True
    allow_repeat: bool = False
    repeat_cooldown_minutes: int = 0


@dataclass(frozen=True)
class UpdatePlotEventCommand:
    workspace_id: str
    story_id: int
    event_id: int
    pool_id: int | PlotPatchUnset = PLOT_PATCH_UNSET
    title: str | PlotPatchUnset = PLOT_PATCH_UNSET
    directive: str | PlotPatchUnset = PLOT_PATCH_UNSET
    description: str | PlotPatchUnset = PLOT_PATCH_UNSET
    suitability_hint: str | PlotPatchUnset = PLOT_PATCH_UNSET
    dispatch_mode: str | PlotPatchUnset = PLOT_PATCH_UNSET
    scheduled_time: SceneTime | None | PlotPatchUnset = PLOT_PATCH_UNSET
    position: int | PlotPatchUnset = PLOT_PATCH_UNSET
    enabled: bool | PlotPatchUnset = PLOT_PATCH_UNSET
    allow_repeat: bool | PlotPatchUnset = PLOT_PATCH_UNSET
    repeat_cooldown_minutes: int | PlotPatchUnset = PLOT_PATCH_UNSET


@dataclass(frozen=True)
class CreatePlotOutlineCommand:
    workspace_id: str
    story_id: int
    name: str
    description: str = ""
    priority: int = 0
    enabled: bool = True


@dataclass(frozen=True)
class UpdatePlotOutlineCommand:
    workspace_id: str
    story_id: int
    outline_id: int
    name: str | PlotPatchUnset = PLOT_PATCH_UNSET
    description: str | PlotPatchUnset = PLOT_PATCH_UNSET
    priority: int | PlotPatchUnset = PLOT_PATCH_UNSET
    enabled: bool | PlotPatchUnset = PLOT_PATCH_UNSET


@dataclass(frozen=True)
class CreatePlotNodeCommand:
    workspace_id: str
    story_id: int
    outline_id: int
    event_id: int
    scheduled_time: SceneTime
    dispatch_mode: str = data_models.PLOT_DISPATCH_SOFT
    position: int | None = None
    enabled: bool = True


@dataclass(frozen=True)
class UpdatePlotNodeCommand:
    workspace_id: str
    story_id: int
    outline_id: int
    node_id: int
    event_id: int | PlotPatchUnset = PLOT_PATCH_UNSET
    scheduled_time: SceneTime | PlotPatchUnset = PLOT_PATCH_UNSET
    dispatch_mode: str | PlotPatchUnset = PLOT_PATCH_UNSET
    position: int | PlotPatchUnset = PLOT_PATCH_UNSET
    enabled: bool | PlotPatchUnset = PLOT_PATCH_UNSET


__all__ = [
    "CreatePlotEventCommand",
    "CreatePlotNodeCommand",
    "CreatePlotOutlineCommand",
    "CreatePlotPoolCommand",
    "PLOT_PATCH_UNSET",
    "PlotPatchUnset",
    "UpdatePlotEventCommand",
    "UpdatePlotNodeCommand",
    "UpdatePlotOutlineCommand",
    "UpdatePlotPoolCommand",
]
