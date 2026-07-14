"""CommandDispatcher — 斜杠命令分发器。

在 agent.send() 进入 LLM 之前拦截 / 开头的输入，由注册的命令处理器
或子 Agent 消费。未知斜杠命令也会返回错误，避免命令误入主 LLM 流程。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from rpg_data.services import SessionPlayerCharacterBindResult
    from rpg_core.agent.sub_agents.base import BaseSubAgent
    from rpg_core.context.inspector import LayerInfo
    from rpg_core.rp_modules.models import ModuleCommand
    from rpg_core.session import SessionManager


class AgentCommandTarget(Protocol):
    """Stable internal surface available to slash-command handlers."""

    @property
    def session_id(self) -> str: ...

    @property
    def session_manager(self) -> "SessionManager": ...

    def clear_history(self) -> None: ...
    async def reload_rpg_context(self) -> None: ...
    def reindex_memory(self) -> bool: ...
    def list_commands(self) -> list["CommandDef"]: ...
    async def get_context_json(self, user_input: str = "", **kwargs) -> str: ...
    async def get_context_markdown(self, user_input: str = "", **kwargs) -> str: ...
    async def switch_session(self, session_id: str) -> None: ...
    def render_role_bind_prompt(self, *, error: str = "") -> str: ...
    def bind_player_character_by_index(self, index: int): ...

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
    role_bind_result: "SessionPlayerCharacterBindResult | None" = None
    """角色绑定命令的内部类型化结果，不进入通用命令接口。"""


# 命令处理器签名：async (agent, args) -> str | CommandResult
HandlerFunc = Callable[[AgentCommandTarget, list[str]], Awaitable[str | CommandResult]]
CommandProvider = Callable[[], list["ModuleCommand"]]


# ── 内置命令处理器 ──────────────────────────────────────────────────────────
# 模块级 async 函数，通过 CommandDispatcher.register_default_builtins() 注册。
# 处理器签名：(agent: RPGGameAgent, args: list[str]) -> str


async def _cmd_clear(agent: AgentCommandTarget, args: list[str]) -> str:
    """清空当前会话的对话历史。"""
    agent.clear_history()
    return "对话历史已清空。"


async def _cmd_reload(agent: AgentCommandTarget, args: list[str]) -> str:
    """重新加载 RPG 数据（角色卡、世界书）。"""
    await agent.reload_rpg_context()
    return "RPG 数据已重新加载。"


async def _cmd_memory_reindex(agent: AgentCommandTarget, args: list[str]) -> str:
    """手动触发 memory 全量重建。"""
    if not agent.reindex_memory():
        return "memory 未启用或未初始化，无法重建索引。"
    return "memory 全量重建已触发。"


async def _cmd_help(agent: AgentCommandTarget, args: list[str]) -> str:
    """列出所有可用命令。"""
    if agent is None:
        return "命令帮助不可用。"
    return format_command_help(agent.list_commands())


async def _cmd_context(agent: AgentCommandTarget, args: list[str]) -> str:
    """查看当前上下文结构和 token 用量。"""
    if args == ["--json"]:
        return await agent.get_context_json()
    if args:
        return "[错误] 用法：/context [--json]"
    return await agent.get_context_markdown()


async def _cmd_sessions(agent: AgentCommandTarget, args: list[str]) -> str:
    """列出当前工作区所有会话。"""
    gateway, current_session = _current_catalog_session(agent)

    sessions = gateway.catalog.list_sessions(
        str(current_session.workspace_id),
        int(current_session.story_id),
    ) or []
    current = agent.session_id
    lines = [f"会话列表 ({len(sessions)}):", f"当前会话: {current}"]
    for session in sessions:
        sid = str(session.id)
        marker = " （当前）" if sid == current else ""
        lines.append(f"- {sid}{marker}")
    return "\n".join(lines)


async def _cmd_session_create(agent: AgentCommandTarget, args: list[str]) -> str:
    """创建新会话。"""
    title = " ".join(args).strip() or "New Session"
    gateway, current_session = _current_catalog_session(agent)
    created = gateway.catalog.create_session(
        str(current_session.workspace_id),
        int(current_session.story_id),
        title=title,
    )
    if created is None:
        return "[错误] 无法在当前故事下创建会话"
    sid = str(created.id)
    return f"[会话已创建: {sid}]"


async def _cmd_session_switch(agent: AgentCommandTarget, args: list[str]) -> str:
    """切换到指定会话。"""
    from rpg_core.session import SessionManager

    if not args:
        return "[错误] 需要提供 session_id: /session_switch <id>"
    sid = args[0]
    try:
        SessionManager.validate_session_id(sid)
    except ValueError as exc:
        return f"[错误] {exc}"
    gateway, current_session = _current_catalog_session(agent)
    target = gateway.catalog.get_session(sid)
    if (
        target is None
        or str(target.workspace_id) != str(current_session.workspace_id)
        or int(target.story_id) != int(current_session.story_id)
    ):
        return f"[会话不存在: {sid}]"
    await agent.switch_session(sid)
    return f"[已切换到会话: {sid}]"


async def _cmd_role_bind(agent: AgentCommandTarget, args: list[str]) -> str | CommandResult:
    """Bind or switch the player-controlled role for the current session."""
    if agent is None:
        return "角色绑定不可用。"
    if not args:
        return agent.render_role_bind_prompt()
    try:
        index = int(args[0])
    except ValueError:
        return agent.render_role_bind_prompt(error=f"无效角色序号: {args[0]}")
    try:
        result = agent.bind_player_character_by_index(index)
    except ValueError as exc:
        return agent.render_role_bind_prompt(error=str(exc))
    player = result.state.player
    if player is None:
        return agent.render_role_bind_prompt()
    confirmation = f"已绑定/切换扮演角色：{player.name}。"
    if result.first_message:
        reply = f"{confirmation}\n\n{result.first_message}"
    else:
        reply = f"{confirmation} 后续消息将使用该身份；已有历史不会被改写。"
    return CommandResult(
        reply=reply,
        handled=True,
        role_bind_result=result,
    )


def _current_catalog_session(agent: AgentCommandTarget):
    from rpg_data.services import get_data_service_gateway

    gateway = get_data_service_gateway()
    current_session = gateway.catalog.get_session(agent.session_id)
    if current_session is None:
        raise FileNotFoundError(f"Session not found in rpg_data: {agent.session_id}")
    return gateway, current_session


def format_command_help(commands: list[CommandDef]) -> str:
    """将命令定义渲染为可发送给聊天渠道的帮助文本。"""
    if not commands:
        return "当前没有可用命令。"

    lines = ["可用命令:"]
    for cmd in commands:
        lines.append(f"- {cmd.name}: {cmd.description}")
    return "\n".join(lines)


class CommandDispatcher:
    """命令分发器。

    维护内置命令和子 Agent 命令两道注册表。dispatch() 按优先级：
    1. 内置命令（help / clear / reload / context / sessions / session_create / session_switch / memory_reindex）
    2. 子 Agent 的 accept_command（如 MemorySubAgent 的 /compact）
    3. 未知斜杠命令 → handled=True，返回错误提示
    """

    def __init__(self, agent: AgentCommandTarget | None = None) -> None:
        self._agent = agent
        self._builtins: dict[str, tuple[CommandDef, HandlerFunc]] = {}
        self._sub_agents: list[BaseSubAgent] = []
        self._command_providers: list[CommandProvider] = []

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

    def replace_sub_agents(self, sub_agents: list[BaseSubAgent]) -> None:
        """Replace lifecycle-owned sub-agents during idempotent setup."""
        self._sub_agents = list(sub_agents)

    def register_command_provider(self, provider: CommandProvider) -> None:
        """Register commands resolved from current external state on every access."""
        self._command_providers.append(provider)

    def replace_command_providers(self, providers: list[CommandProvider]) -> None:
        """Replace lifecycle-owned dynamic command providers."""
        self._command_providers = list(providers)

    def register_default_builtins(self) -> None:
        """注册所有默认内置命令。

        包括 8 个标准管理命令：/help /clear /reload /context /sessions
        /session_create /session_switch /memory_reindex。
        子 Agent 命令（如 /compact /story_memory）由 agent 层另行注册。
        """
        self.register_builtin(
            "/help", "列出所有可用命令",
            "用法：/help。输出当前 agent 支持的全部斜杠命令。", _cmd_help,
        )
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
            "用法：/context [--json]。默认显示上下文概览；加 --json 输出完整渲染内容。", _cmd_context,
        )
        self.register_builtin(
            "/sessions", "列出当前工作区所有会话",
            "显示所有会话 ID，* 标记当前活跃会话。", _cmd_sessions,
        )
        self.register_builtin(
            "/session_create", "创建新会话",
            "用法：/session_create [title]。在当前故事下创建新的 rpg_data 会话，ID 由系统生成。", _cmd_session_create,
        )
        self.register_builtin(
            "/session_switch", "切换到指定会话",
            "用法：/session_switch <id>。切换后对话历史、上下文等全部指向新会话。", _cmd_session_switch,
        )
        self.register_builtin(
            "/memory_reindex", "手动触发 memory 全量重建",
            "用法：/memory_reindex。会重建 memory 的 FTS/向量索引，不会自动在启动时执行。", _cmd_memory_reindex,
        )
        self.register_builtin(
            "/role_bind", "绑定或切换玩家扮演角色",
            "用法：/role_bind <序号>。序号来自当前故事已挂载角色列表；绑定前普通消息不会进入 LLM。", _cmd_role_bind,
        )

    # ── 查询 ──────────────────────────────────────────────────────────

    def list_commands(self) -> list[CommandDef]:
        """返回所有可用的命令定义（用于前端渲染）。"""
        defs: list[CommandDef] = [cmd_def for cmd_def, _ in self._builtins.values()]
        for command in self._provided_commands():
            defs.append(CommandDef(
                name=command.name,
                description=command.description,
                detail=command.detail,
            ))
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
        """判断文本是否应按命令处理。

        只要首个非空字符是 ``/`` 就视为命令输入。未知命令也必须由
        ``dispatch()`` 消费并返回错误，不能落入主 LLM 推理流程。
        """
        return text.lstrip().startswith("/")

    # ── 执行 ──────────────────────────────────────────────────────────

    async def dispatch(self, text: str) -> CommandResult:
        """分发命令，返回执行结果。

        优先级：内置命令 > 子 Agent 命令。
        如果是未知斜杠命令，返回 ``CommandResult(handled=True)`` 和错误提示。
        """
        command_text = text.lstrip()
        if not command_text.startswith("/"):
            return CommandResult()

        parts = command_text.split()
        name = parts[0].lower()
        args = parts[1:]

        # 1) 内置命令
        if name in self._builtins:
            cmd_def, handler = self._builtins[name]
            try:
                result = await handler(self._agent, args)
                if isinstance(result, CommandResult):
                    return result
                return CommandResult(reply=result, handled=True)
            except Exception as e:
                return CommandResult(reply=f"命令 {name} 执行失败: {e}", handled=True)

        # 2) 动态命令（例如随 Story/Session RP Module 挂载变化的 Dice 命令）
        provided = {command.name: command for command in self._provided_commands()}
        if name in provided:
            try:
                reply = await provided[name].handler(self._agent, args)
                return CommandResult(reply=reply, handled=True)
            except Exception as e:
                return CommandResult(reply=f"命令 {name} 执行失败: {e}", handled=True)

        # 3) 子 Agent 命令
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

        return CommandResult(
            reply=f"未知命令: {name}\n输入 /help 查看可用命令。",
            handled=True,
        )

    def _provided_commands(self) -> list["ModuleCommand"]:
        commands: dict[str, "ModuleCommand"] = {}
        for provider in self._command_providers:
            for command in provider():
                commands[command.name] = command
        return list(commands.values())
