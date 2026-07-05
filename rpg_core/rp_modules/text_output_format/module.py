"""Assistant text output format RP module."""

from __future__ import annotations

from rpg_core.context import FixedLayerSection
from rpg_core.rp_modules.base import RPModule
from rpg_core.rp_modules.constants import (
    RP_MODULE_TEXT_OUTPUT_FORMAT_NAME,
    RP_MODULE_TEXT_OUTPUT_FORMAT_SECTION_ID,
    RP_MODULE_TEXT_OUTPUT_FORMAT_SOURCE,
    RP_OUTPUT_ATTR_CHARACTER_NAME,
    RP_OUTPUT_FORMAT_XML_TAGS,
    RP_OUTPUT_TAG_CHARACTER,
    RP_OUTPUT_TAG_NARRATION,
)
from rpg_core.rp_modules.models import ModuleStatus
from rpg_core.settings import TextOutputFormatModuleSettings


class TextOutputFormatModule(RPModule):
    """Prompt-only module that constrains assistant RP text into tagged blocks."""

    name = RP_MODULE_TEXT_OUTPUT_FORMAT_NAME

    def __init__(self, settings: TextOutputFormatModuleSettings | None = None) -> None:
        self.settings = settings or TextOutputFormatModuleSettings()

    def get_fixed_sections(self) -> list[FixedLayerSection]:
        narration_open = f"<{RP_OUTPUT_TAG_NARRATION}>"
        narration_close = f"</{RP_OUTPUT_TAG_NARRATION}>"
        character_open = f'<{RP_OUTPUT_TAG_CHARACTER} {RP_OUTPUT_ATTR_CHARACTER_NAME}="角色名">'
        character_close = f"</{RP_OUTPUT_TAG_CHARACTER}>"
        return [
            FixedLayerSection(
                id=RP_MODULE_TEXT_OUTPUT_FORMAT_SECTION_ID,
                title="文本输出格式",
                source=RP_MODULE_TEXT_OUTPUT_FORMAT_SOURCE,
                priority=90,
                content=(
                    "- RP 正文必须由 XML 风格标签块组成，标签必须闭合，不得嵌套，不得放入代码块。\n"
                    f"- 旁白、环境、行动后果、GM 描写使用 {narration_open}...{narration_close}。\n"
                    f"- NPC 或非玩家角色的台词、短动作使用 {character_open}...{character_close}；"
                    "name 必须填写可识别角色名。\n"
                    f"- 无法确认说话者、群体行动或非台词叙述时，使用 {narration_open}...{narration_close}。\n"
                    "- 标签外不要输出 RP 正文；不要替玩家角色说话、行动或描写内心。\n"
                    "- 命令回复、角色绑定错误、纯 OOC 或调试类非叙事回复允许不使用标签。"
                ),
            )
        ]

    def status(self) -> ModuleStatus:
        return ModuleStatus(
            name=self.name,
            enabled=self.settings.enabled,
            fixed_section_ids=tuple(section.id for section in self.get_fixed_sections()),
            config_summary={"format": RP_OUTPUT_FORMAT_XML_TAGS},
        )
