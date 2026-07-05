"""Tagged assistant text-output fixed-layer contributor."""

from __future__ import annotations

from rpg_core.context.fixed_layer.models import FixedLayerContribution, FixedLayerContributor, FixedLayerSection

TEXT_OUTPUT_FORMAT_NAME = "text_output_format"
TEXT_OUTPUT_FORMAT_SECTION_ID = "fixed_layer_text_output_format"
TEXT_OUTPUT_FORMAT_SOURCE = f"fixed_layer:{TEXT_OUTPUT_FORMAT_NAME}"

RP_OUTPUT_TAG_NARRATION = "rp-narration"
RP_OUTPUT_TAG_CHARACTER = "rp-character"
RP_OUTPUT_ATTR_CHARACTER_NAME = "name"


class TextOutputFormatFixedLayerContributor(FixedLayerContributor):
    """Tagged assistant text-output constraint contributor."""

    name = TEXT_OUTPUT_FORMAT_SOURCE

    def get_fixed_contribution(self) -> FixedLayerContribution:
        narration_open = f"<{RP_OUTPUT_TAG_NARRATION}>"
        narration_close = f"</{RP_OUTPUT_TAG_NARRATION}>"
        character_open = f'<{RP_OUTPUT_TAG_CHARACTER} {RP_OUTPUT_ATTR_CHARACTER_NAME}="角色名">'
        character_close = f"</{RP_OUTPUT_TAG_CHARACTER}>"
        return FixedLayerContribution(sections=[
            FixedLayerSection(
                id=TEXT_OUTPUT_FORMAT_SECTION_ID,
                title="文本输出格式",
                source=TEXT_OUTPUT_FORMAT_SOURCE,
                source_kind=TEXT_OUTPUT_FORMAT_SOURCE,
                priority=90,
                item_count=1,
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
        ])
