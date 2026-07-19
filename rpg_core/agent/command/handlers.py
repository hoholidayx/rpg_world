"""Built-in slash-command handlers."""

from __future__ import annotations

from rpg_data import models
from rpg_core.agent.command.models import AgentCommandTarget, CommandDef, CommandResult


async def cmd_clear(agent: AgentCommandTarget, args: list[str]) -> str:
    if args:
        return "[错误] 用法：/clear"
    result = await agent.reset_session()
    reply = (
        "当前会话的游玩数据已清空；Story 状态模板已重建，"
        "会话原生状态表已保留并清空值。"
    )
    if result.first_message:
        return f"{reply}\n\n{result.first_message}"
    return reply


async def cmd_reload(agent: AgentCommandTarget, args: list[str]) -> str:
    await agent.reload_rpg_context()
    return "RPG 数据已重新加载。"


async def cmd_memory_reindex(agent: AgentCommandTarget, args: list[str]) -> str:
    if not await agent.reindex_memory():
        return "memory 未启用或未初始化，无法重建索引。"
    return "memory 全量重建已触发。"


async def cmd_help(agent: AgentCommandTarget, args: list[str]) -> str:
    if agent is None:
        return "命令帮助不可用。"
    return format_command_help(agent.list_commands())


async def cmd_context(agent: AgentCommandTarget, args: list[str]) -> str:
    if args == ["--json"]:
        return await agent.get_context_json()
    if args:
        return "[错误] 用法：/context [--json]"
    return await agent.get_context_markdown()


async def cmd_sessions(agent: AgentCommandTarget, args: list[str]) -> str:
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


async def cmd_session_create(agent: AgentCommandTarget, args: list[str]) -> str:
    title = " ".join(args).strip() or "New Session"
    gateway, current_session = _current_catalog_session(agent)
    created = gateway.catalog.create_session(
        str(current_session.workspace_id),
        int(current_session.story_id),
        title=title,
    )
    if created is None:
        return "[错误] 无法在当前故事下创建会话"
    return f"[会话已创建: {created.id}]"


async def cmd_session_switch(
    agent: AgentCommandTarget,
    args: list[str],
) -> str | CommandResult:
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
        or target.lifecycle != models.SESSION_LIFECYCLE_READY
        or str(target.workspace_id) != str(current_session.workspace_id)
        or int(target.story_id) != int(current_session.story_id)
    ):
        return f"[会话不存在: {sid}]"
    return CommandResult(
        reply=f"[已切换到会话: {sid}]",
        handled=True,
        active_session=sid,
    )


async def cmd_role_bind(
    agent: AgentCommandTarget,
    args: list[str],
) -> str | CommandResult:
    if agent is None:
        return "角色绑定不可用。"
    if not args:
        return agent.render_role_bind_prompt()
    if len(args) > 2:
        return "[错误] 用法：/role_bind <角色序号> [开局序号]"
    try:
        index = int(args[0])
    except ValueError:
        return agent.render_role_bind_prompt(error=f"无效角色序号: {args[0]}")
    opening_index: int | None = None
    story_opening_id: int | None = None
    if len(args) == 2:
        try:
            if args[1].startswith("opening_id="):
                story_opening_id = int(args[1].removeprefix("opening_id="))
                if story_opening_id <= 0:
                    raise ValueError
            else:
                opening_index = int(args[1])
        except ValueError:
            return agent.render_role_bind_prompt(error=f"无效开局序号: {args[1]}")
    try:
        result = (
            agent.bind_player_character_by_index(
                index,
                story_opening_id=story_opening_id,
            )
            if story_opening_id is not None
            else agent.bind_player_character_by_index(index, opening_index)
        )
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


def format_command_help(commands: list[CommandDef]) -> str:
    if not commands:
        return "当前没有可用命令。"
    lines = ["可用命令:"]
    for command in commands:
        lines.append(f"- {command.name}: {command.description}")
    return "\n".join(lines)


def _current_catalog_session(agent: AgentCommandTarget):
    from rpg_data.services import get_data_service_gateway

    gateway = get_data_service_gateway()
    current_session = gateway.catalog.get_session(agent.session_id)
    if current_session is None:
        raise FileNotFoundError(f"Session not found in rpg_data: {agent.session_id}")
    return gateway, current_session
