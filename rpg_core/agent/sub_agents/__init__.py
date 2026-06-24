"""Sub-agents dedicated package — 子 Agent 专用包。

基于 ``BaseSubAgent`` 抽象基类，提供统一的基础设施（provider 管理、重入防护、SubAgentContext 绑定），
消除 ``StatusSubAgent`` 与 ``MemorySubAgent`` 之间的重复代码。

所有子 Agent 都可以通过 ``SubAgentContext`` 获取世界书 + 角色卡上下文，避免 OOC 判断。
"""

from rpg_core.agent.sub_agents.base import BaseSubAgent
from rpg_core.agent.sub_agents.context import SubAgentContext
from rpg_core.agent.sub_agents.memory_sub_agent import (
    MemoryAgentResult,
    MemorySubAgent,
)
from rpg_core.agent.sub_agents.status_sub_agent import StatusSubAgent

__all__ = [
    "BaseSubAgent",
    "SubAgentContext",
    "MemoryAgentResult",
    "MemorySubAgent",
    "StatusSubAgent",
]
