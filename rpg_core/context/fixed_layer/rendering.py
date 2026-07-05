"""Shared fixed-layer rendering helpers."""

from __future__ import annotations

from rpg_core.context.fixed_layer.models import FixedLayerSection
from rpg_core.context.rendering import render_jinja_template


def render_fixed_layer_sections(sections: list[FixedLayerSection]) -> str:
    """Render wrapped fixed-layer sections through the shared wrapper template."""
    if not sections:
        return ""
    return render_jinja_template(
        "modules/fixed_layer_sections.jinja",
        sections=sections,
    )
