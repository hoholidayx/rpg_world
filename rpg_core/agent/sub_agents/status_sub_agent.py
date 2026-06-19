"""StatusSubAgent — 统一状态表预更新子 Agent.

继承 ``BaseSubAgent``，通过 ``SubAgentContext`` 获取世界书 + 角色卡上下文，
确保场景状态变更判断不会 OOC。

编排层（``RPGGameAgent.send``）在构建 5 层 RPG context *之前* 调用，
用精简上下文（历史 + 状态描述 + 用户输入）预处理状态表变更，
避免主 LLM chat loop 的场景工具 round-trip 开销。

Usage::

    agent = StatusSubAgent(
        provider=main_provider,          # shared 模式复用主 LLM
        provider_config=provider_config, # 或显式 openai/llama 配置
    )
    agent.register_scene_tools(scene_tracker)
    agent.bind_context(sub_agent_context)
    result = await agent.update(history, scene_ctx, user_input)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from rpg_world.rpg_core.agent.agent_types import CallRecord, TurnStats
from rpg_world.rpg_core.agent.base_provider import LLMProvider
from rpg_world.rpg_core.agent.sub_agents.base import BaseSubAgent, SubAgentProviderConfig
from rpg_world.rpg_core.agent.tools import BaseTool
from rpg_world.rpg_core.agent.tools.registry import ToolRegistry
from rpg_world.rpg_core.context.rpg_context import Message, Role
from rpg_world.rpg_core.session.turns import count_turns, slice_recent_turns
from rpg_world.rpg_core.settings import settings

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.sub_agents.context import SubAgentContext

# ── constants ──────────────────────────────────────────────────────────

_TAG = "[StatusSubAgent]"

# ── system prompt ─────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "你是 RPG 游戏世界的状态表更新器。\n\n"
    "可用操作及其修改的状态表：\n"
    "- scene_time / scene_attr / scene_del_attr：更新当前场景状态"
    "（时间、地点、天气、氛围、在场的 NPC 等）\n\n"
    "规则：\n"
    "1. 仅当用户的行为明确或隐式改变了某项状态时，才调用对应的工具。\n"
    "2. 不要修改没有发生变化的属性。\n"
    "3. 如果没有任何变化，不要调用任何工具。\n"
    "4. 主动清理：如果某个属性不再与当前场景相关"
    "（例如角色离开了、某种天气效果消失了），"
    "使用 scene_del_attr 将其移除。只保留活跃属性可以防止上下文膨胀。\n"
    "5. 属性键和值使用中文。"
)

# ── result type ───────────────────────────────────────────────────────


@dataclass
class StatusSubAgentResult:
    """StatusSubAgent 一次 ``update()`` 的执行结果。"""

    updated: bool = False
    """是否有状态表被修改。"""
    records: list[dict[str, object]] = field(default_factory=list)
    """工具调用记录，每项含 ``tool_name`` / ``arguments`` / ``result``。"""
    call_stats: list[CallRecord] = field(default_factory=list)
    """此更新涉及的 LLM 调用记录（usage / timing）。"""


# ── sub-agent ─────────────────────────────────────────────────────────


class StatusSubAgent(BaseSubAgent):
    """状态表更新子 Agent。

    继承自 ``BaseSubAgent``，使用基类的 provider 管理、重入守卫以及
    SubAgentContext 绑定。

    Parameters
    ----------
    provider:
        共享主 Agent 的 LLM provider，仅 shared 模式传入。
    provider_config:
        解析后的 provider 配置，显式选择 shared/openai/llama。
    enabled:
        总开关。
    """

    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        provider_config: SubAgentProviderConfig | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            provider=provider,
            provider_config=provider_config,
            model=model,
            api_key=api_key,
            base_url=base_url,
            enabled=enabled,
        )

        # ── 可扩展工具集 ──────────────────────────────────────────────
        self._tool_registry = ToolRegistry()
        self._schemas: list[dict[str, object]] = []

    # ── 工具注册（可多次调用追加） ─────────────────────────────────────

    def register_tools(self, tools: list[BaseTool]) -> None:
        """注册状态表操作工具。可多次调用追加。"""
        self._tool_registry.register_all(tools)
        self._schemas = self._tool_registry.get_openai_schemas()
        logger.info(
            _TAG + " registered {} tool(s): {}",
            len(tools),
            [t.name for t in tools],
        )

    # ── Context 绑定（覆盖基类） ─────────────────────────────────────

    def bind_context(self, context: SubAgentContext) -> None:
        """绑定 SubAgentContext，同时刷新所有工具提供者的工具。"""
        super().bind_context(context)
        self.clear_tools()
        self.register_tools(self._collect_provider_tools())

    # ── 核心方法 ─────────────────────────────────────────────────────

    @property
    def system_prompt(self) -> str:
        """返回状态表预更新子 Agent 的系统提示。"""
        return SYSTEM_PROMPT

    async def update(
        self,
        history: list[Message],
        state_context: str,
        user_input: str,
        max_history_rounds: int = 5,
        turn_stats: TurnStats | None = None,
    ) -> StatusSubAgentResult:
        """根据用户输入预更新状态表。

        Parameters
        ----------
        history:
            完整对话历史（内部按 *max_history_rounds* 窗口化）。
        state_context:
            当前状态描述（如 ``[scene]`` 块）。
        user_input:
            用户原始输入（最新一条）。
        max_history_rounds:
            传递给 LLM 的最大用户轮次数。
        turn_stats:
            可选的外部聚合器——传入后 LLM 调用数据也会归入其中。

        Returns
        -------
        ``StatusSubAgentResult``，包含是否更新以及工具调用记录。
        """
        if self._busy:
            logger.debug(_TAG + " skipped (re-entrancy guard)")
            return StatusSubAgentResult()

        if not self._enabled or not self._schemas:
            return StatusSubAgentResult()

        self._busy = True
        result = StatusSubAgentResult()
        try:
            if settings.verbose_logging:
                logger.info(
                    _TAG + " analyzing {!r} (history={} msgs, schemes={})",
                    user_input,
                    len(history),
                    [s["function"]["name"] for s in self._schemas],
                )

            messages = self._build_messages(
                history, state_context, user_input, max_history_rounds
            )

            # ── LLM call with timing ────────────────────────────────
            import time

            t0 = time.monotonic()
            llm_result = await self._get_provider().chat(messages, tools=self._schemas)
            duration_ms = (time.monotonic() - t0) * 1000

            # 捕获 CallRecord
            from rpg_world.rpg_core.agent.agent_types import LLMResponse

            if isinstance(llm_result, LLMResponse):
                call_rec = CallRecord(
                    source="status_sub_agent",
                    model=llm_result.model or self._get_provider().get_default_model(),
                    usage=llm_result.usage,
                    duration_ms=duration_ms,
                    reasoning_content=llm_result.reasoning_content,
                )
                result.call_stats.append(call_rec)
                if turn_stats is not None:
                    turn_stats.add_call(call_rec)

            tool_calls = llm_result.get("tool_calls") if isinstance(llm_result, dict) else llm_result.tool_calls
            if not tool_calls:
                if settings.verbose_logging:
                    logger.info(_TAG + " no state changes needed")
                return result

            if settings.verbose_logging:
                logger.info(
                    _TAG + " LLM returned {} tool call(s)",
                    len(tool_calls),
                )

            for tc in tool_calls:
                name = tc["function"]["name"]
                args = tc["function"]["arguments"]
                if settings.verbose_logging:
                    logger.info(_TAG + " calling tool: {}({})", name, args)

                try:
                    tool_result = await self._tool_registry.execute(name, args)
                    result.records.append({
                        "tool_name": name,
                        "arguments": args,
                        "result": str(tool_result),
                    })
                    if settings.verbose_logging:
                        logger.info(
                            _TAG + " tool result: {} -> {}",
                            name,
                            str(tool_result)[:200],
                        )
                except Exception as exc:
                    logger.warning(
                        _TAG + " tool {}({}) failed: {}",
                        name, args, exc,
                    )
                    result.records.append({
                        "tool_name": name,
                        "arguments": args,
                        "result": f"Error: {exc}",
                    })

            result.updated = True
            logger.info(
                _TAG + " updated state via {} tool call(s): {}",
                len(result.records),
                [r["tool_name"] for r in result.records],
            )
            return result

        except Exception as exc:
            logger.warning(_TAG + " update failed: {}", exc)
            return result
        finally:
            self._busy = False

    def clear_tools(self) -> None:
        """清空已注册的工具集（重新注册前调用避免重复）。"""
        self._tool_registry = ToolRegistry()
        self._schemas = []

    # ── internal helpers ──────────────────────────────────────────────

    def _build_messages(
        self,
        history: list[Message],
        state_context: str,
        user_input: str,
        max_rounds: int,
    ) -> list[dict]:
        """组装子 Agent 消息：系统上下文（含世界书/角色卡） + 历史窗口 + 场景 + 用户输入。"""
        total_turns = count_turns(history)
        recent = self._format_history_window(history, max_rounds)
        if settings.verbose_logging:
            kept = min(total_turns, max_rounds)
            logger.info(
                _TAG + " history window: {}/{} turns (max_rounds={})",
                kept, total_turns, max_rounds,
            )
        system_content = self._build_system_context()
        return [
            Message(role=Role.SYSTEM, content=system_content).to_dict(),
            Message(
                role=Role.USER,
                content=(
                    f"## Current State\n\n{state_context}\n\n"
                    f"## Recent Conversation\n\n{recent}\n\n"
                    f"## User action\n{user_input}\n\n"
                    f"Update the state tables if the user's action changes "
                    f"any tracked state. If nothing changes, call no tools."
                ),
            ).to_dict(),
        ]

    @staticmethod
    def _format_history_window(
        history: list[Message],
        max_rounds: int,
    ) -> str:
        """提取最近 N 轮对话，格式化为 ``Role: text`` 行。"""
        history = slice_recent_turns(history, max_rounds)

        lines: list[str] = []
        for msg in history:
            role = msg.role
            content = (msg.content or "").strip()
            if not content or msg.is_system():
                continue
            label = {Role.USER.value: "User", Role.ASSISTANT.value: "Assistant"}.get(
                role, role.capitalize()
            )
            lines.append(f"{label}: {content[:500]}")

        return "\n\n".join(lines) if lines else "(no recent conversation)"
