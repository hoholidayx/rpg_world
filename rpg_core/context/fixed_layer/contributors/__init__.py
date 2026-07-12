"""Concrete fixed-layer contributors."""

from rpg_core.context.fixed_layer.contributors.character import (
    CharacterFixedLayerContributor,
    build_character_section,
    render_character_section_body,
)
from rpg_core.context.fixed_layer.contributors.core_contract import CoreRPContractContributor
from rpg_core.context.fixed_layer.contributors.lorebook import (
    LorebookFixedLayerContributor,
    build_lorebook_section,
    render_lorebook_section_body,
)
from rpg_core.context.fixed_layer.contributors.story_prompt import (
    STORY_PROMPT_SECTION_ID,
    STORY_PROMPT_SOURCE,
    StoryPromptFixedLayerContributor,
)
from rpg_core.context.fixed_layer.contributors.static_sections import StaticFixedLayerContributor
from rpg_core.context.fixed_layer.contributors.text_output_format import (
    RP_OUTPUT_ATTR_CHARACTER_NAME,
    RP_OUTPUT_TAG_CHARACTER,
    RP_OUTPUT_TAG_NARRATION,
    TEXT_OUTPUT_FORMAT_NAME,
    TEXT_OUTPUT_FORMAT_SECTION_ID,
    TEXT_OUTPUT_FORMAT_SOURCE,
    TextOutputFormatFixedLayerContributor,
)
from rpg_core.context.fixed_layer.contributors.turn_execution import (
    TurnExecutionFixedLayerContributor,
)

__all__ = [
    "CharacterFixedLayerContributor",
    "CoreRPContractContributor",
    "LorebookFixedLayerContributor",
    "RP_OUTPUT_ATTR_CHARACTER_NAME",
    "RP_OUTPUT_TAG_CHARACTER",
    "RP_OUTPUT_TAG_NARRATION",
    "STORY_PROMPT_SECTION_ID",
    "STORY_PROMPT_SOURCE",
    "StaticFixedLayerContributor",
    "StoryPromptFixedLayerContributor",
    "TEXT_OUTPUT_FORMAT_NAME",
    "TEXT_OUTPUT_FORMAT_SECTION_ID",
    "TEXT_OUTPUT_FORMAT_SOURCE",
    "TextOutputFormatFixedLayerContributor",
    "TurnExecutionFixedLayerContributor",
    "build_character_section",
    "build_lorebook_section",
    "render_character_section_body",
    "render_lorebook_section_body",
]
