"""CommandDispatcher — 斜杠命令分发器。

在 agent.send() 进入 LLM 之前拦截 / 开头的输入，由注册的命令处理器
或子 Agent 消费，避免命令误入主 LLM 流程。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.agent import RPGGameAgent
    from rpg_world.rpg_core.agent.sub_agents.base import BaseSubAgent


@dataclass
class CommandDef:
    """命令定义——展示用。"""

    name: str
    """命令名，如 ``/compact``。"""
    description: str
    """一句话说明。"""
    detail: str
    """详细用法说明。"""


@dataclass
class CommandResult:
    """命令执行结果。"""

    reply: str = ""
    """文本回复。"""
    stats: dict[str, Any] | None = None
    """可选的统计信息。"""
    handled: bool = False
    """是否被某个处理器消费。"""


class CommandDispatcher:
    """命令分发器。

    维护内置命令和子 Agent 命令两道注册表。dispatch() 按优先级：
    1. 内置命令（clear / reload / context）
    2. 子 Agent 的 accept_command（如 MemorySubAgent 的 /compact）
    3. 未命中 → handed=False，调用方走 LLM 兜底
    """

    def __init__(self, agent: RPGGameAgent | None = None) -> None:
        self._agent = agent
        self._builtins: dict[str, tuple[CommandDef, Any]] = {}
        self._sub_agents: list[BaseSubAgent] = []

    # ── 注册 ──────────────────────────────────────────────────────────

    def register_builtin(
        self,
        name: str,
        description: str,
        detail: str,
        handler: Any,
    ) -> None:
        """注册一个内置命令及其处理器。"""
        self._builtins[name] = (
            CommandDef(name=name, description=description, detail=detail),
            handler,
        )

    def register_sub_agent(self, sub_agent: BaseSubAgent) -> None:
        """注册子 Agent，dispatch 时会查询其 accept_command()。"""
        self._sub_agents.append(sub_agent)

    # ── 查询 ──────────────────────────────────────────────────────────

    def list_commands(self) -> list[CommandDef]:
        """返回所有可用的命令定义（用于前端渲染）。"""
        defs = [cmd_def for cmd_def, _ in self._builtins.values()]
        for sa in self._sub_agents:
            cmd = sa.get_command_def()
            if cmd is not None:
                defs.append(cmd)
        return defs

    def is_command(self, text: str) -> bool:
        """判断文本是否可能是已知命令。"""
        if not text.startswith("/"):
            return False
        name = text.split()[0].lower()
        if name in self._builtins:
            return True
        for sa in self._sub_agents:
            if sa.accept_command(name):
                return True
        return False

    # ── 执行 ──────────────────────────────────────────────────────────

    async def dispatch(self, text: str) -> CommandResult:
        """分发命令，返回执行结果。

        优先级：内置命令 > 子 Agent 命令。
        如果都不处理，返回 ``CommandResult(handled=False)``。
        """
        if not text.startswith("/"):
            return CommandResult()

        parts = text.split()
        name = parts[0].lower()
        args = parts[1:]

        # 1) 内置命令
        if name in self._builtins:
            cmd_def, handler = self._builtins[name]
            try:
                reply = await handler(self._agent, args)
                return CommandResult(reply=reply, handled=True)
            except Exception as e:
                return CommandResult(reply=f"命令 {name} 执行失败: {e}", handled=True)

        # 2) 子 Agent 命令
        for sa in self._sub_agents:
            if sa.accept_command(name):
                try:
                    result = await sa.execute_command(name, args, self._agent)
                    if result is not None:
                        return CommandResult(
                            reply=result.get("reply", ""),
                            stats=result.get("stats"),
                            handled=True,
                        )
                except Exception as e:
                    return CommandResult(
                        reply=f"子 Agent 执行 {name} 失败: {e}", handled=True,
                    )

        return CommandResult()
