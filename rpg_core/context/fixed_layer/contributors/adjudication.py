"""Module-neutral authority contract for Outcome, Status, and Plot judges."""

from __future__ import annotations

from rpg_core.context.fixed_layer.models import (
    FIXED_LAYER_SOURCE_CORE,
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)

ADJUDICATION_AUTHORITY_SECTION_ID = "adjudication_authority"
ADJUDICATION_AUTHORITY_SOURCE = "adjudication"


class AdjudicationAuthorityFixedLayerContributor(FixedLayerContributor):
    """Supply only factual authority and decision-boundary rules."""

    name = ADJUDICATION_AUTHORITY_SOURCE

    def get_fixed_contribution(self) -> FixedLayerContribution:
        return FixedLayerContribution(
            sections=[
                FixedLayerSection(
                    id=ADJUDICATION_AUTHORITY_SECTION_ID,
                    title="裁定事实与权限边界",
                    priority=0,
                    source=ADJUDICATION_AUTHORITY_SOURCE,
                    source_kind=FIXED_LAYER_SOURCE_CORE,
                    item_count=1,
                    content=(
                        "你是 RPG 引擎中的事实裁定组件，只完成当前阶段明确要求的判断，"
                        "不续写剧情、不生成 RP 正文，也不执行未提供的能力。\n"
                        "- [player_character] 是当前 Session 玩家身份的唯一真源；"
                        "不得把 NPC 当作玩家，也不得用旧内容覆盖该绑定。\n"
                        "- 当前阶段随后提供的 Scene 与状态表是最新运行时事实。"
                        "已提交会话历史是已经发生之事的真源；较新的已提交事实可取代较旧记忆。\n"
                        "- Story Prompt、世界书与角色卡定义故事和角色的权威边界。"
                        "常驻记忆与剧情记忆均为 Evidence 仍有效的事实投影；"
                        "若与较新的已提交历史或当前状态冲突，以较新真源为准。\n"
                        "- 当前用户输入通常表达本轮行动、意图或明确纠正，"
                        "不得把尚有外部变数的预期结果直接视为已经发生。\n"
                        "- 若缺失的历史事实可能实质改变判断，应先使用 history_search "
                        "定位，再用 history_read 阅读完整 turn；不得凭空补足。\n"
                        "- 只遵循当前阶段的窄工具契约。不得推断或引入任何未在当前"
                        "阶段提供的玩法模块、叙事、格式或状态同步指令。"
                    ),
                )
            ]
        )
