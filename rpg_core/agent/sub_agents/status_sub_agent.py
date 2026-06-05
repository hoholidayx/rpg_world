"""StatusSubAgent — 统一状态表预更新子 Agent.

继承 ``BaseSubAgent``，通过 ``SubAgentContext`` 获取世界书 + 角色卡上下文，
确保场景状态变更判断不会 OOC。

编排层（``RPGGameAgent.send``）在构建 5 层 RPG context *之前* 调用，
用精简上下文（历史 + 状态描述 + 用户输入）预处理状态表变更，
避免主 LLM chat loop 的场景工具 round-trip 开销。

Usage::

    agent = StatusSubAgent(
        provider=main_provider,          # 共享主 LLM
        # provider=None, model="gpt-4o-mini",  # 或独立 LLM
    )
    agent.register_scene_tools(scene_tracker)
    agent.bind_context(sub_agent_context)
    result = await agent.update(history, scene_ctx, user_input)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from rpg_world.rpg_core.agent.base_provider import LLMProvider
from rpg_world.rpg_core.agent.sub_agents.base import BaseSubAgent, ToolProvider
from rpg_world.rpg_core.agent.tools.base import BaseTool
from rpg_world.rpg_core.agent.tools.registry import ToolRegistry
from rpg_world.rpg_core.agent.agent_types import CallRecord, TurnStats
from rpg_world.rpg_core.settings import settings

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.sub_agents.context import SubAgentContext

# ── constants ──────────────────────────────────────────────────────────

_TAG = "[StatusSubAgent]"

# ── system prompt ─────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a state table updater for an RPG game world.\n\n"
    "Available operations and the state tables they modify:\n"
    "- scene_time / scene_attr / scene_del_attr: Update the current scene state "
    "(time, location, weather, atmosphere, NPCs present, etc.)\n\n"
    "Rules:\n"
    "1. Call a tool only when the user's action explicitly or implicitly "
    "changes that state.\n"
    "2. Do NOT change attributes that remain the same.\n"
    "3. If nothing changes, call no tools.\n"
    "4. Proactively clean up: if an attribute is no longer relevant to the "
    "current scene (e.g. a character left, a weather effect passed), "
    "use scene_del_attr to remove it. Keeping only active attributes "
    "prevents context bloat.\n"
    "5. Use Chinese for attribute keys and values."
)

# ── result type ───────────────────────────────────────────────────────


@dataclass
class StatusSubAgentResult:
    """StatusSubAgent 一次 ``update()`` 的执行结果。"""

    updated: bool = False
    """是否有状态表被修改。"""
    records: list[dict[str, Any]] = field(default_factory=list)
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
        共享主 Agent 的 LLM provider。传 ``None`` 时使用 *model* / *api_key* / *base_url* 自建。
    model:
        独立 LLM 模型名（仅 *provider* 为 None 时生效）。
    api_key:
        独立 LLM API key。
    base_url:
        独立 LLM base URL。
    enabled:
        总开关。
    """

    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            enabled=enabled,
        )

        # ── 可扩展工具集 ──────────────────────────────────────────────
        self._tool_registry = ToolRegistry()
        self._schemas: list[dict[str, Any]] = []

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

    async def update(
        self,
        history: list[dict],
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
        history: list[dict],
        state_context: str,
        user_input: str,
        max_rounds: int,
    ) -> list[dict]:
        """组装子 Agent 消息：系统上下文（含世界书/角色卡） + 历史窗口 + 场景 + 用户输入。"""
        total_user_rounds = sum(1 for m in history if m.get("role") == "user")
        recent = self._format_history_window(history, max_rounds)
        if settings.verbose_logging:
            kept = min(total_user_rounds, max_rounds)
            logger.info(
                _TAG + " history window: {}/{} user rounds (max_rounds={})",
                kept, total_user_rounds, max_rounds,
            )
        system_content = self._build_system_context(SYSTEM_PROMPT)
        return [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": (
                    f"## Current State\n\n{state_context}\n\n"
                    f"## Recent Conversation\n\n{recent}\n\n"
                    f"## User action\n{user_input}\n\n"
                    f"Update the state tables if the user's action changes "
                    f"any tracked state. If nothing changes, call no tools."
                ),
            },
        ]

    @staticmethod
    def _format_history_window(
        history: list[dict],
        max_rounds: int,
    ) -> str:
        """提取最近 N 轮对话，格式化为 ``Role: text`` 行。"""
        user_indices = [
            i for i, m in enumerate(history) if m.get("role") == "user"
        ]
        if len(user_indices) > max_rounds:
            history = history[user_indices[-max_rounds]:]

        lines: list[str] = []
        for msg in history:
            role = msg.get("role", "")
            content = (msg.get("content") or "").strip()
            if not content or role == "system":
                continue
            label = {"user": "User", "assistant": "Assistant"}.get(
                role, role.capitalize()
            )
            lines.append(f"{label}: {content[:500]}")

        return "\n\n".join(lines) if lines else "(no recent conversation)"
