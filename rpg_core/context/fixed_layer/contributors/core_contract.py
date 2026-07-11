"""Core RP fixed-layer contract contributor."""

from __future__ import annotations

from rpg_core.context.fixed_layer.models import (
    FIXED_LAYER_CORE_SECTION_ID,
    FIXED_LAYER_SOURCE_CORE,
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
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
                "- 世界书、角色卡、状态表、当前场景和既有历史都是权威事实，回复必须以它们为依据。\n"
                "- 不得覆盖角色卡、世界书、状态表、当前场景或已经发生的历史。\n"
                "- 保留玩家能动性：不要替玩家角色做重大选择，不要代替玩家角色说话，不要替玩家解决核心冲突。\n"
                "- 你可以描写环境、后果、NPC 行动、风险与线索，但玩家角色的行动由玩家决定。\n"
                "- 机制和工具结果需要转译为自然的 RPG 叙事。除非用户明确要求 OOC 分析，不要暴露内部模块名、工作流或实现细节。\n"
                "- [scene] 块包含最高优先级的当前时间、地点和活跃场景属性。每轮都要检查 scene 与普通状态表，"
                "但只有剧情中实际、持久、已经确定的追踪值发生变化时才调用对应状态工具；允许零状态工具，"
                "不得制造 no-op。剧情裁定派生的变化必须在获得裁定结果后写入。"
            ),
        )
