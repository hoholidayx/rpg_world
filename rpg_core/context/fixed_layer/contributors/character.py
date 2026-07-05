"""Character-card fixed-layer contributor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from commons.types import JsonObject
from rpg_core.context.fixed_layer.models import (
    FIXED_LAYER_CHARACTER_SECTION_ID,
    FIXED_LAYER_SOURCE_CHARACTER,
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)
from rpg_core.context.rendering import render_jinja_template

if TYPE_CHECKING:
    from rpg_core.character.manager import CharacterManager


def render_character_section_body(characters: list[JsonObject]) -> str:
    """Render character body content without outer fixed-layer wrapper."""
    if not characters:
        return ""
    return render_jinja_template(
        "modules/character_card.jinja",
        characters=characters,
    )


def build_character_section(characters: list[JsonObject]) -> FixedLayerSection | None:
    """Build the character-card fixed-layer section from mounted characters."""
    content = render_character_section_body(characters)
    if not content.strip():
        return None
    return FixedLayerSection(
        id=FIXED_LAYER_CHARACTER_SECTION_ID,
        title="角色卡",
        content=content,
        priority=30,
        source=FIXED_LAYER_SOURCE_CHARACTER,
        source_kind=FIXED_LAYER_SOURCE_CHARACTER,
        item_count=len(characters),
    )


class CharacterFixedLayerContributor(FixedLayerContributor):
    """Load character cards and project them into fixed-layer data + section."""

    name = FIXED_LAYER_SOURCE_CHARACTER

    def __init__(
        self,
        character_mgr: "CharacterManager | None",
        *,
        enabled: bool = True,
    ) -> None:
        self._character_mgr = character_mgr
        self._enabled = enabled

    def get_fixed_contribution(self) -> FixedLayerContribution:
        if not self._enabled or self._character_mgr is None:
            return FixedLayerContribution()
        characters = list(self._character_mgr.list_enabled_characters())
        section = build_character_section(characters)
        if section is None:
            return FixedLayerContribution()
        return FixedLayerContribution(
            sections=[section],
            characters=characters,
        )
