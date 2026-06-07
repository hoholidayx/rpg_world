"""CommandDispatcher — 斜杠命令分发器。

在 agent.send() 进入 LLM 之前拦截 / 开头的输入，由注册的命令处理器
或子 Agent 消费，避免命令误入主 LLM 流程。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.agent import RPGGameAgent
    from rpg_world.rpg_core.agent.sub_agents.base import BaseSubAgent

# 命令处理器签名：async (agent, args) -> str
HandlerFunc = Callable[["RPGGameAgent", list[str]], Awaitable[str]]


# ── 内置命令处理器 ──────────────────────────────────────────────────────────
# 模块级 async 函数，通过 CommandDispatcher.register_default_builtins() 注册。
# 处理器签名：(agent: RPGGameAgent, args: list[str]) -> str


async def _cmd_clear(agent: RPGGameAgent, args: list[str]) -> str:
    """清空当前会话的对话历史。"""
    agent.clear_history()
    return "对话历史已清空。"


async def _cmd_reload(agent: RPGGameAgent, args: list[str]) -> str:
    """重新加载 RPG 数据（角色卡、世界书）。"""
    await agent.reload_rpg_context()
    return "RPG 数据已重新加载。"


async def _cmd_context(agent: RPGGameAgent, args: list[str]) -> str:
    """查看当前上下文结构和 token 用量。"""
    return await agent.get_context_markdown()


async def _cmd_sessions(agent: RPGGameAgent, args: list[str]) -> str:
    """列出所有会话。"""
    from rpg_world.rpg_core.settings import settings

    sessions = settings.list_sessions()
    current = agent._session_id
    lines = [f"会话列表 ({len(sessions)}):"]
    for s in sessions:
        marker = "  *" if s == current else ""
        lines.append(f"  - {s}{marker}")
    return "\n".join(lines)


async def _cmd_session_create(agent: RPGGameAgent, args: list[str]) -> str:
    """创建新会话。"""
    from rpg_world.rpg_core.settings import settings

    if not args:
        return "[错误] 需要提供 session-id: /session-create <id>"
    sid = args[0]
    try:
        settings.create_session(sid)
        return f"[会话已创建: {sid}]"
    except FileExistsError:
        return f"[会话已存在: {sid}]"


async def _cmd_session_switch(agent: RPGGameAgent, args: list[str]) -> str:
    """切换到指定会话。"""
    from rpg_world.rpg_core.settings import settings

    if not args:
        return "[错误] 需要提供 session-id: /session-switch <id>"
    sid = args[0]
    if sid not in settings.list_sessions():
        return f"[会话不存在: {sid}]"
    await agent.switch_session(sid)
    return f"[已切换到会话: {sid}]"


# ── 数据类 ──────────────────────────────────────────────────────────────


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
    stats: dict[str, object] | None = None
    """可选的统计信息。"""
    handled: bool = False
    """是否被某个处理器消费。"""


class CommandDispatcher:
    """命令分发器。

    维护内置命令和子 Agent 命令两道注册表。dispatch() 按优先级：
    1. 内置命令（clear / reload / context / sessions / session-create / session-switch）
    2. 子 Agent 的 accept_command（如 MemorySubAgent 的 /compact）
    3. 未命中 → handed=False，调用方走 LLM 兜底
    """

    def __init__(self, agent: RPGGameAgent | None = None) -> None:
        self._agent = agent
        self._builtins: dict[str, tuple[CommandDef, HandlerFunc]] = {}
        self._sub_agents: list[BaseSubAgent] = []

    # ── 注册 ──────────────────────────────────────────────────────────

    def register_builtin(
        self,
        name: str,
        description: str,
        detail: str,
        handler: HandlerFunc,
    ) -> None:
        """注册一个内置命令及其处理器。"""
        self._builtins[name] = (
            CommandDef(name=name, description=description, detail=detail),
            handler,
        )

    def register_sub_agent(self, sub_agent: BaseSubAgent) -> None:
        """注册子 Agent，dispatch 时会查询其 accept_command()。"""
        self._sub_agents.append(sub_agent)

    def register_default_builtins(self) -> None:
        """注册所有默认内置命令。

        包括 6 个标准管理命令：/clear /reload /context /sessions
        /session-create /session-switch。
        子 Agent 命令（如 /compact /story_memory）由 agent 层另行注册。
        """
        self.register_builtin(
            "/clear", "清空当前会话的对话历史",
            "重置对话上下文，清除所有已发送的消息记录。", _cmd_clear,
        )
        self.register_builtin(
            "/reload", "重新加载 RPG 数据（角色卡、世界书）",
            "从磁盘重新读取角色卡和世界书文件变更。", _cmd_reload,
        )
        self.register_builtin(
            "/context", "查看当前上下文结构和 token 用量",
            "显示 5 层 RPG 上下文的每层信息。", _cmd_context,
        )
        self.register_builtin(
            "/sessions", "列出当前工作区所有会话",
            "显示所有会话 ID，* 标记当前活跃会话。", _cmd_sessions,
        )
        self.register_builtin(
            "/session-create", "创建新会话",
            "用法：/session-create <id>。在新会话目录下初始化数据文件。", _cmd_session_create,
        )
        self.register_builtin(
            "/session-switch", "切换到指定会话",
            "用法：/session-switch <id>。切换后对话历史、上下文等全部指向新会话。", _cmd_session_switch,
        )

    # ── 查询 ──────────────────────────────────────────────────────────

    def list_commands(self) -> list[CommandDef]:
        """返回所有可用的命令定义（用于前端渲染）。"""
        defs: list[CommandDef] = [cmd_def for cmd_def, _ in self._builtins.values()]
        for sa in self._sub_agents:
            result = sa.get_command_def()
            if result is None:
                continue
            if isinstance(result, list):
                defs.extend(result)
            else:
                defs.append(result)
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
