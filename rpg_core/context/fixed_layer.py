"""Fixed layer composition for the main RPG agent.

固定层包含低频变化的稳定指令，应该位于上下文前部以提升 prefix cache 命中：
核心 RP 契约、世界身份、静态 RP module 契约。动态场景/运行时状态应放在后续
上下文层或 user prefix，不放这里。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FixedLayerSection:
    """渲染到固定层的一段稳定内容。"""

    id: str
    title: str
    content: str
    priority: int = 100
    source: str = "core"


class FixedLayerComposer:
    """组合主 RPG Agent 的固定层稳定指令。"""

    def __init__(
        self,
        world_name: str = "Nanobot Realm",
        module_sections: list[FixedLayerSection] | None = None,
    ) -> None:
        self._world_name = world_name
        self._module_sections = list(module_sections or [])

    @property
    def sections(self) -> list[FixedLayerSection]:
        """返回全部稳定固定层片段，不在此处渲染。"""
        sections = [self._core_rp_contract(), *self._module_sections]
        sections = sorted(sections, key=lambda s: (s.priority, s.id))
        return [section for section in sections if section.content.strip()]

    def with_module_sections(self, sections: list[FixedLayerSection]) -> "FixedLayerComposer":
        """返回一个追加静态 RP module 片段的新 composer。"""
        return FixedLayerComposer(
            world_name=self._world_name,
            module_sections=[*self._module_sections, *sections],
        )

    def _core_rp_contract(self) -> FixedLayerSection:
        return FixedLayerSection(
            id="core_rp_contract",
            title="核心 RP 契约",
            priority=0,
            content=(
                f"你是「{self._world_name}」这个沉浸式 RPG 世界的游戏主持者。\n"
                "- 默认保持角色内叙事，使用具体、连贯、可感知的描写推进当前场景。\n"
                "- 世界书、角色卡、状态表、当前场景和既有历史都是权威事实，回复必须以它们为依据。\n"
                "- 不得覆盖角色卡、世界书、状态表、当前场景或已经发生的历史。\n"
                "- 保留玩家能动性：不要替玩家角色做重大选择，不要代替玩家角色说话，不要替玩家解决核心冲突。\n"
                "- 你可以描写环境、后果、NPC 行动、风险与线索，但玩家角色的行动由玩家决定。\n"
                "- 机制和工具结果需要转译为自然的 RPG 叙事。除非用户明确要求 OOC 分析，不要暴露内部模块名、工作流或实现细节。\n"
                "- 必须保持场景状态同步。[scene] 块包含最高优先级的当前时间、地点和活跃场景属性；当场景发生变化时，使用 scene_time、scene_attr 或 scene_del_attr 更新。"
            ),
        )
