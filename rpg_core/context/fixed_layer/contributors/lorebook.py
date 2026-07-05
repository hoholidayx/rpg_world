"""Lorebook fixed-layer contributor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from commons.types import JsonObject
from rpg_core.context.fixed_layer.models import (
    FIXED_LAYER_LOREBOOK_SECTION_ID,
    FIXED_LAYER_SOURCE_LOREBOOK,
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)
from rpg_core.context.rendering import render_jinja_template

if TYPE_CHECKING:
    from rpg_core.lorebook.manager import LorebookManager


def render_lorebook_section_body(lorebook_entries: list[JsonObject]) -> str:
    """Render lorebook body content without outer fixed-layer wrapper."""
    if not lorebook_entries:
        return ""
    return render_jinja_template(
        "modules/lorebook.jinja",
        lorebook_entries=lorebook_entries,
    )


def build_lorebook_section(lorebook_entries: list[JsonObject]) -> FixedLayerSection | None:
    """Build the lorebook fixed-layer section from mounted entries."""
    content = render_lorebook_section_body(lorebook_entries)
    if not content.strip():
        return None
    return FixedLayerSection(
        id=FIXED_LAYER_LOREBOOK_SECTION_ID,
        title="世界书",
        content=content,
        priority=20,
        source=FIXED_LAYER_SOURCE_LOREBOOK,
        source_kind=FIXED_LAYER_SOURCE_LOREBOOK,
        item_count=len(lorebook_entries),
    )


class LorebookFixedLayerContributor(FixedLayerContributor):
    """Load lorebook entries and project them into fixed-layer data + section."""

    name = FIXED_LAYER_SOURCE_LOREBOOK

    def __init__(
        self,
        lorebook_mgr: "LorebookManager | None",
        *,
        enabled: bool = True,
    ) -> None:
        self._lorebook_mgr = lorebook_mgr
        self._enabled = enabled

    def get_fixed_contribution(self) -> FixedLayerContribution:
        if not self._enabled or self._lorebook_mgr is None:
            return FixedLayerContribution()
        lorebook_entries = list(self._lorebook_mgr.list_enabled_entries())
        section = build_lorebook_section(lorebook_entries)
        if section is None:
            return FixedLayerContribution()
        return FixedLayerContribution(
            sections=[section],
            lorebook_entries=lorebook_entries,
        )
