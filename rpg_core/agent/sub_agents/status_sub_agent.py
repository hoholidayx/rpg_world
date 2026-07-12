"""StatusSubAgent — 统一状态表预更新子 Agent.

继承 ``BaseSubAgent``，通过 ``SubAgentContext`` 获取世界书 + 角色卡上下文，
确保场景状态变更判断不会 OOC。

编排层（``RPGGameAgent.send``）在构建 5 层 RPG context *之前* 调用，
用精简上下文（历史 + 状态描述 + 用户输入）预处理状态表变更，
避免主 LLM chat loop 的场景工具 round-trip 开销。

Usage::

    agent = StatusSubAgent(
        provider_biz_key="agent.status_sub_agent",
    )
    agent.register_scene_tools(scene_tracker)
    agent.bind_context(sub_agent_context)
    result = await agent.update(history, scene_ctx, user_input)
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Iterator

from loguru import logger

from rpg_core.agent.agent_types import CallRecord, TurnStats
from rpg_core.agent.sub_agents.base import BaseSubAgent
from rpg_core.agent.sub_agents.status_sub_agent_models import (
    StatusSubAgentRecordStatus,
    StatusSubAgentResult,
    StatusSubAgentToolRecord,
)
from rpg_core.agent.tools import BaseTool
from rpg_core.agent.tools.registry import ToolRegistry
from rpg_core.agent.transaction.constants import SCENE_TOOL_NAMES
from rpg_core.context.rpg_context import Message, Role
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_TOOL_NAME
from rpg_core.session.manager import SessionManager
from rpg_core.settings import settings
from rpg_core.status.tools import STATUS_TABLE_SET_VALUES_TOOL_NAME

if TYPE_CHECKING:
    from llm_service.manager import ProviderOverrides

    from rpg_core.agent.sub_agents.context import SubAgentContext

# ── constants ──────────────────────────────────────────────────────────

_TAG = "[StatusSubAgent]"
_STATE_TOOL_NAMES = frozenset(
    (*SCENE_TOOL_NAMES, STATUS_TABLE_SET_VALUES_TOOL_NAME)
)


class _StatusPrewriteRollbackError(RuntimeError):
    """Fatal guard: continuing could expose a partially restored scratch."""

# ── system prompt ─────────────────────────────────────────────────────

BASE_SYSTEM_PROMPT = (
    "你是 RPG 游戏世界的状态表预处理器。\n\n"
    "可用操作及其修改的状态表：\n"
    "- scene_time / scene_attr / scene_del_attr：更新当前场景状态"
    "（时间、地点、天气、氛围、在场的 NPC 等）\n"
    "- status_table_set_values：批量更新普通状态表中已有键的值\n\n"
    "状态更新边界：\n"
    "1. 只依据既有 assistant 已确认事实、用户对既有事实的明确纠正，或没有随机分支的确定性动作"
    "更新状态。用户单方面宣称的未决外部结果不是已确认事实。\n"
    "2. 仅当实际、持久、已经确定的追踪值发生变化时调用状态工具；不要修改没有变化的属性，"
    "不要制造 no-op。没有裁定且没有状态变化时，不调用任何工具。\n"
    "3. 主动清理：如果某个属性不再与当前场景相关"
    "（例如角色离开了、某种天气效果消失了），"
    "使用 scene_del_attr 将其移除。只保留活跃属性可以防止上下文膨胀。\n"
    "4. 普通状态表不得新增、删除或重命名键；角色状态表只追踪对应角色。\n"
    "5. 属性键和值使用状态表已有语言和格式。"
)

NARRATIVE_OUTCOME_SYSTEM_PROMPT = (
    "\n\n剧情预裁定边界：\n"
    "1. 先结合最近历史、当前场景、普通状态表和用户输入，判断本轮是否存在外部实质变数："
    "同一行动或场景反应仍有两个或以上合理结果，受未知信息、能力、阻力、风险、时机、环境或 "
    "NPC/世界反应影响，而且不同结果会实质改变剧情、信息、风险或代价。\n"
    "2. 只要需要裁定，就只调用一次 rp_story_outcome。不得同时调用任何状态工具，也不得提前假设"
    "成功、失败、发现、伤害、NPC 反应或位置抵达；混合行动中的确定性子动作也交给主 Agent 延后处理。\n"
    "3. 只有不需要裁定时，才执行上述确定性状态预更新。"
)

SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + NARRATIVE_OUTCOME_SYSTEM_PROMPT

# ── sub-agent ─────────────────────────────────────────────────────────


class StatusSubAgent(BaseSubAgent):
    """状态表更新子 Agent。

    继承自 ``BaseSubAgent``，使用基类的 provider 管理、重入守卫以及
    SubAgentContext 绑定。

    Parameters
    ----------
    provider_biz_key:
        交给 ``LLMManager`` 路由的业务键，例如 ``agent.status_sub_agent``。
    enabled:
        总开关。
    """

    def __init__(
        self,
        *,
        provider_biz_key: str,
        provider_overrides: ProviderOverrides | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            provider_biz_key=provider_biz_key,
            provider_overrides=provider_overrides,
            enabled=enabled,
        )

        # ── 可扩展工具集 ──────────────────────────────────────────────
        self._tool_registry = ToolRegistry()
        self._schemas: list[dict[str, object]] = []
        self._mutation_probe: Callable[[], object] | None = None
        self._mutation_checkpoint: Callable[[], object] | None = None
        self._mutation_restore: Callable[[object], None] | None = None
        self._outcome_preflight_enabled = False

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

    def set_mutation_probe(self, probe: Callable[[], object] | None) -> None:
        self._mutation_probe = probe

    def set_mutation_boundary(
        self,
        checkpoint: Callable[[], object] | None,
        restore: Callable[[object], None] | None,
    ) -> None:
        """Bind an in-memory rollback boundary for one status prewrite batch."""
        self._mutation_checkpoint = checkpoint
        self._mutation_restore = restore

    @contextmanager
    def use_turn_tools(
        self,
        tools: list[BaseTool],
        *,
        mutation_probe: Callable[[], object] | None,
        create_checkpoint: Callable[[], object] | None,
        restore_checkpoint: Callable[[object], None] | None,
        outcome_preflight_enabled: bool | None = None,
    ) -> Iterator[None]:
        """Temporarily bind tools and rollback callbacks for one turn."""
        previous_registry = self._tool_registry
        previous_schemas = self._schemas
        previous_probe = self._mutation_probe
        previous_checkpoint = self._mutation_checkpoint
        previous_restore = self._mutation_restore
        previous_outcome_preflight_enabled = self._outcome_preflight_enabled
        try:
            self.clear_tools()
            self.register_tools(tools)
            self.set_mutation_probe(mutation_probe)
            self.set_mutation_boundary(create_checkpoint, restore_checkpoint)
            self._outcome_preflight_enabled = (
                any(tool.name == NARRATIVE_OUTCOME_TOOL_NAME for tool in tools)
                if outcome_preflight_enabled is None
                else bool(outcome_preflight_enabled)
            )
            yield
        finally:
            self._tool_registry = previous_registry
            self._schemas = previous_schemas
            self.set_mutation_probe(previous_probe)
            self.set_mutation_boundary(previous_checkpoint, previous_restore)
            self._outcome_preflight_enabled = previous_outcome_preflight_enabled

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
        if self._outcome_preflight_enabled:
            return BASE_SYSTEM_PROMPT + NARRATIVE_OUTCOME_SYSTEM_PROMPT
        return BASE_SYSTEM_PROMPT

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
            from rpg_core.agent.agent_types import LLMResponse

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

            normalized_calls = [_normalize_tool_call(tc) for tc in tool_calls]
            result.outcome_requested = any(
                name == NARRATIVE_OUTCOME_TOOL_NAME
                for name, _args in normalized_calls
            )

            # The decision is batch-wide, not order-dependent. Once an outcome
            # is requested, no state mutation from the same response may enter
            # scratch, including deterministic-looking parts of a mixed action.
            if result.outcome_requested:
                outcome_executed = False
                for name, args in normalized_calls:
                    if name in _STATE_TOOL_NAMES:
                        result.state_prewrites_skipped += 1
                        result.records.append(
                            StatusSubAgentToolRecord.skipped_due_to_outcome(
                                tool_name=name,
                                arguments=args,
                                state_prewrite=True,
                            )
                        )
                        continue
                    if name != NARRATIVE_OUTCOME_TOOL_NAME:
                        result.records.append(
                            StatusSubAgentToolRecord.skipped_due_to_outcome(
                                tool_name=name,
                                arguments=args,
                                state_prewrite=False,
                            )
                        )
                        continue
                    if outcome_executed:
                        result.records.append(
                            StatusSubAgentToolRecord.skipped_duplicate_outcome(
                                tool_name=name,
                                arguments=args,
                            )
                        )
                        continue

                    outcome_executed = True
                    record = await self._execute_tool_call(
                        name,
                        args,
                        track_mutation=False,
                        success_status=StatusSubAgentRecordStatus.OUTCOME_STAGED,
                    )
                    result.records.append(record)
                    result.outcome_staged = record.success
                    result.failed = not result.outcome_staged

                if result.outcome_staged:
                    logger.info(
                        _TAG + " staged narrative outcome; skipped {} state prewrite(s)",
                        result.state_prewrites_skipped,
                    )
                else:
                    logger.warning(
                        _TAG + " outcome preflight failed; main Agent will decide via fallback"
                    )
                return result

            checkpoint = (
                self._mutation_checkpoint()
                if self._mutation_checkpoint is not None
                else None
            )
            for name, args in normalized_calls:
                record = await self._execute_tool_call(
                    name,
                    args,
                    track_mutation=True,
                )
                result.records.append(record)
                result.updated = result.updated or record.changed
                result.failed = result.failed or not record.success

            if result.failed and checkpoint is not None and self._mutation_restore is not None:
                try:
                    self._mutation_restore(checkpoint)
                except Exception as exc:
                    logger.opt(exception=exc).error(
                        _TAG + " failed to restore status prewrite checkpoint"
                    )
                    raise _StatusPrewriteRollbackError(
                        "failed to restore status prewrite checkpoint"
                    ) from exc
                for record in result.records:
                    record.mark_rolled_back()
                result.updated = False
                logger.warning(
                    _TAG + " state prewrite batch failed and was restored; main Agent will fallback"
                )

            if result.updated:
                logger.info(
                    _TAG + " updated state via {} tool call(s): {}",
                    len(result.records),
                    [record.tool_name for record in result.records if record.changed],
                )
            else:
                logger.info(_TAG + " state tool calls produced no staged changes")
            return result

        except _StatusPrewriteRollbackError:
            raise
        except Exception as exc:
            result.failed = True
            logger.warning(_TAG + " update failed: {}", exc)
            return result
        finally:
            self._busy = False

    async def _execute_tool_call(
        self,
        name: str,
        args: str,
        *,
        track_mutation: bool,
        success_status: StatusSubAgentRecordStatus | None = None,
    ) -> StatusSubAgentToolRecord:
        if settings.verbose_logging:
            logger.info(_TAG + " calling tool: {}({})", name, args)

        try:
            before = (
                self._mutation_probe()
                if track_mutation and self._mutation_probe is not None
                else None
            )
            tool_result = await self._tool_registry.execute(name, args)
            after = (
                self._mutation_probe()
                if track_mutation and self._mutation_probe is not None
                else None
            )
            result_text = str(tool_result)
            success = _tool_result_succeeded(result_text)
            if not track_mutation:
                changed = False
            elif self._mutation_probe is not None:
                changed = before != after
            else:
                changed = _tool_result_reports_change(result_text, success=success)
            changed = success and changed
            status = (
                StatusSubAgentRecordStatus.ERROR
                if not success
                else success_status
                or (
                    StatusSubAgentRecordStatus.CHANGED
                    if changed
                    else StatusSubAgentRecordStatus.NO_OP
                )
            )
            if settings.verbose_logging:
                logger.info(
                    _TAG + " tool result: {} -> {}",
                    name,
                    result_text[:200],
                )
            return StatusSubAgentToolRecord(
                tool_name=name,
                arguments=args,
                result=result_text,
                success=success,
                changed=changed,
                status=status,
            )
        except Exception as exc:
            logger.warning(
                _TAG + " tool {}({}) failed: {}",
                name,
                args,
                exc,
            )
            return StatusSubAgentToolRecord(
                tool_name=name,
                arguments=args,
                result=f"Error: {exc}",
                success=False,
                changed=False,
                status=StatusSubAgentRecordStatus.ERROR,
            )

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
        total_turns = SessionManager.count_turns(history)
        recent = self._format_history_window(history, max_rounds)
        if settings.verbose_logging:
            kept = min(total_turns, max_rounds)
            logger.info(
                _TAG + " history window: {}/{} turns (max_rounds={})",
                kept, total_turns, max_rounds,
            )
        system_content = self._build_system_context()
        outcome_instruction = (
            "先判断是否存在外部实质变数；需要裁定时只调用 "
            "rp_story_outcome，且不要同时调用状态工具。"
            if NARRATIVE_OUTCOME_TOOL_NAME in self._tool_registry
            else "本轮未提供剧情裁定工具；不要虚构随机结果。"
        )
        return [
            Message(role=Role.SYSTEM, content=system_content).to_dict(),
            Message(
                role=Role.USER,
                content=(
                    f"## Current State\n\n{state_context}\n\n"
                    f"## Recent Conversation\n\n{recent}\n\n"
                    f"## User action\n{user_input}\n\n"
                    f"{outcome_instruction}只有不需要裁定时，才预更新已经确定且实际改变的"
                    f"追踪状态；没有变化就不调用工具。"
                ),
            ).to_dict(),
        ]

    @staticmethod
    def _format_history_window(
        history: list[Message],
        max_rounds: int,
    ) -> str:
        """提取最近 N 轮对话，格式化为 ``Role: text`` 行。"""
        history = SessionManager.slice_recent_turns(history, max_rounds)

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


def _tool_result_succeeded(tool_result: str) -> bool:
    if tool_result.startswith("Error:") or tool_result.startswith("Error executing"):
        return False
    try:
        payload = json.loads(tool_result)
    except (TypeError, ValueError):
        return not tool_result.startswith("设置失败：")
    if isinstance(payload, dict) and isinstance(payload.get("ok"), bool):
        return bool(payload["ok"])
    return True


def _normalize_tool_call(tool_call: object) -> tuple[str, str]:
    if not isinstance(tool_call, dict):
        return "", "{}"
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return "", "{}"
    name = str(function.get("name", "") or "")
    arguments = function.get("arguments", "{}")
    if isinstance(arguments, str):
        return name, arguments
    return name, json.dumps(arguments, ensure_ascii=False)


def _tool_result_reports_change(tool_result: str, *, success: bool) -> bool:
    if not success:
        return False
    try:
        payload = json.loads(tool_result)
    except (TypeError, ValueError):
        return True
    if isinstance(payload, dict) and isinstance(payload.get("changed"), bool):
        return bool(payload["changed"])
    return True
