"""Slash-command registration and dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.agent.command.handlers import (
    cmd_clear,
    cmd_context,
    cmd_help,
    cmd_memory_reindex,
    cmd_reload,
    cmd_role_bind,
    cmd_session_create,
    cmd_session_switch,
    cmd_sessions,
)
from rpg_core.agent.command.models import (
    AgentCommandTarget,
    CommandDef,
    CommandProvider,
    CommandResult,
    HandlerFunc,
)

if TYPE_CHECKING:
    from rpg_core.agent.sub_agents.base import BaseSubAgent
    from rpg_core.rp_modules.models import ModuleCommand


class CommandDispatcher:
    """Dispatch built-in, dynamic-module, and SubAgent commands in order."""

    def __init__(self, agent: AgentCommandTarget | None = None) -> None:
        self._agent = agent
        self._builtins: dict[str, tuple[CommandDef, HandlerFunc]] = {}
        self._sub_agents: list[BaseSubAgent] = []
        self._command_providers: list[CommandProvider] = []

    def register_builtin(
        self,
        name: str,
        description: str,
        detail: str,
        handler: HandlerFunc,
    ) -> None:
        self._builtins[name] = (
            CommandDef(name=name, description=description, detail=detail),
            handler,
        )

    def register_sub_agent(self, sub_agent: BaseSubAgent) -> None:
        self._sub_agents.append(sub_agent)

    def replace_sub_agents(self, sub_agents: list[BaseSubAgent]) -> None:
        self._sub_agents = list(sub_agents)

    def register_command_provider(self, provider: CommandProvider) -> None:
        self._command_providers.append(provider)

    def replace_command_providers(self, providers: list[CommandProvider]) -> None:
        self._command_providers = list(providers)

    def register_default_builtins(self) -> None:
        self.register_builtin(
            "/help",
            "列出所有可用命令",
            "用法：/help。输出当前 agent 支持的全部斜杠命令。",
            cmd_help,
        )
        self.register_builtin(
            "/clear",
            "完全重置当前会话的游玩数据",
            "清除主历史、摘要、记忆、向量索引和运行文件，重建 Story 状态副本，保留并清空会话原生表；有效角色绑定会重新收到开场。",
            cmd_clear,
        )
        self.register_builtin(
            "/reload",
            "重新加载 RPG 数据（角色卡、世界书）",
            "从磁盘重新读取角色卡和世界书文件变更。",
            cmd_reload,
        )
        self.register_builtin(
            "/context",
            "查看当前上下文结构和 token 用量",
            "用法：/context [--json]。默认显示上下文概览；加 --json 输出完整渲染内容。",
            cmd_context,
        )
        self.register_builtin(
            "/sessions",
            "列出当前工作区所有会话",
            "显示所有会话 ID，* 标记当前活跃会话。",
            cmd_sessions,
        )
        self.register_builtin(
            "/session_create",
            "创建新会话",
            "用法：/session_create [title]。在当前故事下创建新的 rpg_data 会话，ID 由系统生成。",
            cmd_session_create,
        )
        self.register_builtin(
            "/session_switch",
            "切换到指定会话",
            "用法：/session_switch <id>。校验目标后由当前渠道把后续请求切换到该会话。",
            cmd_session_switch,
        )
        self.register_builtin(
            "/memory_reindex",
            "手动触发 memory 全量重建",
            "用法：/memory_reindex。会重建 memory 的 FTS/向量索引，不会自动在启动时执行。",
            cmd_memory_reindex,
        )
        self.register_builtin(
            "/role_bind",
            "绑定或切换玩家扮演角色",
            "用法：/role_bind <角色序号> [开局序号]。未指定开局时使用 Story 的第一条；绑定前普通消息不会进入 LLM。",
            cmd_role_bind,
        )

    def list_commands(self) -> list[CommandDef]:
        definitions = [definition for definition, _ in self._builtins.values()]
        for command in self._provided_commands():
            definitions.append(
                CommandDef(
                    name=command.name,
                    description=command.description,
                    detail=command.detail,
                )
            )
        for sub_agent in self._sub_agents:
            result = sub_agent.get_command_def()
            if result is None:
                continue
            if isinstance(result, list):
                definitions.extend(result)
            else:
                definitions.append(result)
        return definitions

    def is_command(self, text: str) -> bool:
        return text.lstrip().startswith("/")

    async def dispatch(self, text: str) -> CommandResult:
        command_text = text.lstrip()
        if not command_text.startswith("/"):
            return CommandResult()

        parts = command_text.split()
        name = parts[0].lower()
        args = parts[1:]

        if name in self._builtins:
            _, handler = self._builtins[name]
            try:
                result = await handler(self._agent, args)
                if isinstance(result, CommandResult):
                    return result
                return CommandResult(reply=result, handled=True)
            except Exception as exc:
                return CommandResult(reply=f"命令 {name} 执行失败: {exc}", handled=True)

        provided = {command.name: command for command in self._provided_commands()}
        if name in provided:
            try:
                reply = await provided[name].handler(self._agent, args)
                return CommandResult(reply=reply, handled=True)
            except Exception as exc:
                return CommandResult(reply=f"命令 {name} 执行失败: {exc}", handled=True)

        for sub_agent in self._sub_agents:
            if sub_agent.accept_command(name):
                try:
                    result = await sub_agent.execute_command(name, args, self._agent)
                    if result is not None:
                        return CommandResult(
                            reply=result.get("reply", ""),
                            stats=result.get("stats"),
                            handled=True,
                        )
                except Exception as exc:
                    return CommandResult(
                        reply=f"子 Agent 执行 {name} 失败: {exc}",
                        handled=True,
                    )

        return CommandResult(
            reply=f"未知命令: {name}\n输入 /help 查看可用命令。",
            handled=True,
        )

    def _provided_commands(self) -> list[ModuleCommand]:
        commands: dict[str, ModuleCommand] = {}
        for provider in self._command_providers:
            for command in provider():
                commands[command.name] = command
        return list(commands.values())
