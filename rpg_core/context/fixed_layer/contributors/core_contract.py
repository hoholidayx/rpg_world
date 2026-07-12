"""Core RP fixed-layer contract contributor."""

from __future__ import annotations

from rpg_core.context.fixed_layer.models import (
    FIXED_LAYER_CORE_SECTION_ID,
    FIXED_LAYER_SOURCE_CORE,
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)


STATE_SYNC_BEFORE_NARRATION_RULE = (
    "先在内部确定本轮叙事后果和最终追踪值。凡实际、持久、已经确定的变化，"
    "必须在输出任何 RP 正文前调用对应状态工具；工具调用轮不得夹带 RP 正文，"
    "等待工具返回后再输出与已同步状态一致的最终正文。最终正文不得再新增本应写入 "
    "scene 或普通状态表、但尚未同步的确定事实；若准备新增，必须先回到工具调用轮完成同步。"
    "只有核验后确认无变化时才允许零状态工具；不得制造 no-op，裁定派生变化只能在获得裁定结果后写入。"
)


class CoreRPContractContributor(FixedLayerContributor):
    """核心 RP 契约 contributor。"""

    name = FIXED_LAYER_SOURCE_CORE

    def __init__(self, world_name: str = "Nanobot Realm") -> None:
        self._world_name = world_name

    def get_fixed_contribution(self) -> FixedLayerContribution:
        return FixedLayerContribution(sections=[self._core_rp_contract()])

    def _core_rp_contract(self) -> FixedLayerSection:
        return FixedLayerSection(
            id=FIXED_LAYER_CORE_SECTION_ID,
            title="核心 RP 契约",
            priority=0,
            source=FIXED_LAYER_SOURCE_CORE,
            source_kind=FIXED_LAYER_SOURCE_CORE,
            item_count=1,
            content=(
                f"你是「{self._world_name}」这个沉浸式 RPG 世界的游戏主持者。\n"
                "- 默认保持角色内叙事，使用具体、连贯、可感知的描写推进当前场景。\n"
                "- 世界书、角色卡和已经发生的历史是权威事实，回复必须以它们为依据，不得无依据改写。\n"
                "- [player_character] 标签块是当前 session 的玩家身份唯一真源；若其它上下文与其冲突，"
                "必须以该绑定为准。\n"
                "- [scene] 标签块和普通状态表是本轮回复前的权威运行时快照；不得无依据覆盖，"
                "但本轮剧情已经确定的变化必须同步。\n"
                "- 保留玩家能动性：不要替玩家角色做重大选择，不要代替玩家角色说话，不要替玩家解决核心冲突。\n"
                "- 你可以描写环境、后果、NPC 行动、风险与线索，但玩家角色的行动由玩家决定。\n"
                "- 机制和工具结果需要转译为自然的 RPG 叙事。除非用户明确要求 OOC 分析，不要暴露内部模块名、工作流或实现细节。\n"
                f"- {STATE_SYNC_BEFORE_NARRATION_RULE}\n"
                "- 状态同步是内部职责。普通 RP 中不得询问玩家是否需要标记、记录或更新状态，"
                "不得在正文中提及状态表、状态工具或内部维护流程。"
            ),
        )
