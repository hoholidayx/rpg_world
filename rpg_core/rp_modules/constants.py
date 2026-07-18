"""Constants shared by RP Module settings and implementations."""

from __future__ import annotations

RP_MODULE_SOURCE_PREFIX = "rp_module"

RP_MODULE_DICE_NAME = "dice"
RP_MODULE_DICE_SECTION_ID = "rp_module_dice"
RP_MODULE_DICE_TURN_SECTION_ID = "rp_module_dice_turn_directive"
RP_MODULE_DICE_SOURCE = f"{RP_MODULE_SOURCE_PREFIX}:{RP_MODULE_DICE_NAME}"

RP_MODULE_NARRATIVE_OUTCOME_NAME = "narrative_outcome"
RP_MODULE_NARRATIVE_OUTCOME_SECTION_ID = "rp_module_narrative_outcome"
RP_MODULE_NARRATIVE_OUTCOME_TURN_SECTION_ID = "rp_module_narrative_outcome_turn_directive"
RP_MODULE_NARRATIVE_OUTCOME_SOURCE = (
    f"{RP_MODULE_SOURCE_PREFIX}:{RP_MODULE_NARRATIVE_OUTCOME_NAME}"
)
