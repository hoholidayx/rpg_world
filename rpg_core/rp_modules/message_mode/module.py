"""Late runtime directives for Neutral, IC, OOC, and GM turns."""

from __future__ import annotations

from rpg_core.context import RPModuleRuntimeSection
from rpg_core.rp_modules.base import RPModule
from rpg_core.rp_modules.constants import (
    RP_MODULE_MESSAGE_MODE_NAME,
    RP_MODULE_MESSAGE_MODE_SOURCE,
    RP_MODULE_MESSAGE_MODE_TURN_SECTION_ID,
)
from rpg_core.rp_modules.models import ModuleContextRequest
from rpg_core.session.modes import TurnMode


class MessageModeModule(RPModule):
    """Render mode-specific policy after Hot History without changing Fixed."""

    name = RP_MODULE_MESSAGE_MODE_NAME

    def get_runtime_sections(
        self,
        request: ModuleContextRequest,
    ) -> list[RPModuleRuntimeSection]:
        mode = TurnMode(request.message_mode)
        if mode is TurnMode.NEUTRAL:
            return []
        if mode is TurnMode.IC:
            content = (
                "本轮是 IC（角色内）输入。将用户输入视为当前玩家角色已经明确表达的"
                "台词、行动或意图；不得补写玩家未声明的台词、主动行动、心理活动或关键选择。"
            )
        elif mode is TurnMode.OOC:
            content = (
                "本轮是 OOC（场外讨论）。直接讨论剧情、设定或玩法；不得推进故事时间线，"
                "不得作剧情裁定，不得新增或修改 Scene、角色、状态或记忆事实，"
                "无需使用 RP 正文标签。"
            )
        else:
            content = self._gm_content(request)
        return [
            RPModuleRuntimeSection(
                id=RP_MODULE_MESSAGE_MODE_TURN_SECTION_ID,
                title=f"Message Mode：{mode.value.upper()}",
                content=content,
                priority=10_000,
                source=RP_MODULE_MESSAGE_MODE_SOURCE,
            )
        ]

    @staticmethod
    def _gm_content(request: ModuleContextRequest) -> str:
        player_name = request.player_character_name.strip() or "当前玩家角色"
        lines = [
            "本轮是 GM（主持/导演）命令。用户可以命令世界与 NPC，并将当前玩家角色"
            f"「{player_name}」在本 turn 内交由你托管。",
            f"- 为完成本轮 GM 指令，可以替 {player_name} 生成台词、动作、决定和心理活动。",
            "- 托管仅限当前 turn，且不得扩展与本轮 GM 指令无关的玩家决定。",
        ]
        if request.player_portrayal_details:
            lines.append("- 本轮可额外应用以下玩家角色演绎设定：")
            for detail in request.player_portrayal_details:
                lines.append(f"  - {detail.name}: {detail.content}")
        return "\n".join(lines)
