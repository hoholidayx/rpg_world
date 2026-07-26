"""StatusSubAgent — 统一状态表预更新子 Agent.

生产 turn 使用共享、模块中立的裁定快照；直接/bootstrap 调用仍可通过
``SubAgentContext`` 获取窄世界书与角色卡上下文。

编排层（``RPGGameAgent.send``）在构建结构化主 Context *之前* 调用，
用共享事实前缀 + 历史 + 状态描述 + 用户输入预处理状态表变更，
避免主 LLM chat loop 的场景工具 round-trip 开销。

The production entrypoint is :meth:`StatusSubAgent.run_preflight`, which runs
the fixed Outcome → Route → isolated target-update pipeline.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterator, TypeAlias

from loguru import logger

from llm_client.types import LLMResponse, LLMUsage
from rpg_data.model.status import (
    STATUS_ROW_UPDATE_RULE_KEY,
)
from rpg_core.agent.adjudication import (
    AdjudicationContextSnapshot,
    run_adjudication_tool_loop,
)
from rpg_core.agent.telemetry import CallRecord, TurnStats
from rpg_core.agent.sub_agents.base import BaseSubAgent
from rpg_core.agent.sub_agents.status.models import (
    OutcomeDecision,
    StatusBootstrapResult,
    StatusRouteResult,
    StatusRouteTarget,
    StatusSubAgentRecordStatus,
    StatusSubAgentResult,
    StatusSubAgentStage,
    StatusSubAgentToolRecord,
)
from rpg_core.agent.sub_agents.status.parsing import (
    normalize_tool_call as _normalize_tool_call,
    tool_result_reports_change as _tool_result_reports_change,
    tool_result_succeeded as _tool_result_succeeded,
)
from rpg_core.agent.sub_agents.status.prompts import (
    OUTCOME_ONLY_SYSTEM_PROMPT,
    ROUTED_STATE_UPDATE_SYSTEM_PROMPT,
    STATUS_ROUTER_SCHEMA,
    STATUS_ROUTER_TOOL_NAME,
)
from rpg_core.agent.tools.history import HistoryToolSet
from rpg_core.agent.tools.state import StateToolSet
from rpg_core.context.fingerprint import (
    build_request_fingerprint,
    request_fingerprint_log_values,
)
from rpg_core.context.models import Message, Role
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_TOOL_NAME
from rpg_core.scene import SCENE_TOOL_NAMES
from rpg_core.session.manager import SessionManager
from rpg_core.settings import settings
from rpg_core.status.tools import STATUS_TABLE_SET_VALUES_TOOL_NAME
from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry

if TYPE_CHECKING:
    from rpg_core.agent.sub_agents.context import SubAgentContext
    from rpg_core.agent.turn.models import TurnPlayerCharacterSnapshot


# ── constants ──────────────────────────────────────────────────────────

_TAG = "[StatusSubAgent]"
_LLMChatResult: TypeAlias = LLMResponse | dict[str, object]


@dataclass(frozen=True)
class _RoutedStatusUpdateBatch:
    """One code-scoped scene or single-table update call."""

    source: str
    selected_context: str
    schema_names: frozenset[str]
    allowed_status_keys: dict[int, frozenset[str]] | None
    is_scene: bool = False


class _StatusPrewriteRollbackError(RuntimeError):
    """Fatal guard: continuing could expose a partially restored scratch."""

# ── sub-agent ─────────────────────────────────────────────────────────


class StatusSubAgent(BaseSubAgent):
    """状态表更新子 Agent。

    继承自 ``BaseSubAgent``，使用基类的 provider 管理、重入守卫以及
    SubAgentContext 绑定。

    Parameters
    ----------
    provider_biz_key:
        交给 ``LLMClientManager`` 路由的业务键，例如 ``agent.status_sub_agent``。
    enabled:
        总开关。
    """

    def __init__(
        self,
        *,
        provider_biz_key: str,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            provider_biz_key=provider_biz_key,
            enabled=enabled,
        )

        # ── 可扩展工具集 ──────────────────────────────────────────────
        self._tool_registry = ToolRegistry()
        self._schemas: list[dict[str, object]] = []
        self._state_tool_set = StateToolSet()
        self._mutation_probe: Callable[[], object] | None = None
        self._mutation_checkpoint: Callable[[], object] | None = None
        self._mutation_restore: Callable[[object], None] | None = None
        self._active_status_allowed_keys: dict[int, frozenset[str]] | None = None
        self._active_scene_allowed = True

    # ── 工具注册（可多次调用追加） ─────────────────────────────────────

    def register_tools(self, tools: list[BaseTool]) -> None:
        """注册状态表操作工具。可多次调用追加。"""
        self._tool_registry.register_all(tools)
        self._schemas = self._tool_registry.get_openai_schemas()
        self._state_tool_set = StateToolSet.from_tools(self._tool_registry)
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
        """Bind an in-memory rollback boundary for one status update target."""
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
    ) -> Iterator[None]:
        """Temporarily bind tools and rollback callbacks for one turn."""
        previous_registry = self._tool_registry
        previous_schemas = self._schemas
        previous_state_tool_set = self._state_tool_set
        previous_probe = self._mutation_probe
        previous_checkpoint = self._mutation_checkpoint
        previous_restore = self._mutation_restore
        try:
            self.clear_tools()
            self.register_tools(tools)
            self.set_mutation_probe(mutation_probe)
            self.set_mutation_boundary(create_checkpoint, restore_checkpoint)
            yield
        finally:
            self._tool_registry = previous_registry
            self._schemas = previous_schemas
            self._state_tool_set = previous_state_tool_set
            self.set_mutation_probe(previous_probe)
            self.set_mutation_boundary(previous_checkpoint, previous_restore)

    # ── Context 绑定（覆盖基类） ─────────────────────────────────────

    def bind_context(self, context: SubAgentContext) -> None:
        """绑定 SubAgentContext，同时刷新所有工具提供者的工具。"""
        self.clear_tools()
        self.register_tools(self._collect_provider_tools())
        super().bind_context(context)

    # ── 核心方法 ─────────────────────────────────────────────────────

    @staticmethod
    def _log_verbose(message: str, *args: object) -> None:
        if settings.verbose_logging:
            logger.info(_TAG + " " + message, *args)

    async def run_preflight(
        self,
        *,
        history: list[Message],
        state_context: str,
        scene_context: str,
        context_tables: list[dict[str, object]],
        user_input: str,
        max_history_rounds: int | None = None,
        max_history_tool_rounds: int | None = None,
        turn_stats: TurnStats | None = None,
        player_character: "TurnPlayerCharacterSnapshot | None" = None,
        adjudication_context: AdjudicationContextSnapshot | None = None,
        history_tools: HistoryToolSet | None = None,
    ) -> StatusSubAgentResult:
        """Run the fixed outcome -> route -> selected-update pipeline."""
        if max_history_rounds is None:
            max_history_rounds = settings.status_history_rounds
        if max_history_tool_rounds is None:
            max_history_tool_rounds = (
                settings.adjudication_max_history_tool_rounds
            )
        adjudication_context = (
            adjudication_context or AdjudicationContextSnapshot()
        )
        if self._busy:
            logger.debug(_TAG + " preflight skipped: reason=reentrancy_guard")
            return StatusSubAgentResult()
        if not self._enabled:
            self._log_verbose("preflight skipped: reason=disabled")
            return StatusSubAgentResult()
        if not self._schemas:
            self._log_verbose("preflight skipped: reason=no_tools")
            return StatusSubAgentResult()

        self._busy = True
        result = StatusSubAgentResult()
        self._log_verbose(
            "preflight started: user_input={!r}, history_messages={}, tables={}, "
            "state_tools={}, outcome_tool_available={}",
            user_input[:200],
            len(history),
            len(context_tables),
            sorted(self._state_tool_set.names),
            bool(self._schemas_for_names({NARRATIVE_OUTCOME_TOOL_NAME})),
        )
        try:
            outcome = await self._decide_outcome(
                history=history,
                state_context=state_context,
                user_input=user_input,
                max_history_rounds=max_history_rounds,
                result=result,
                turn_stats=turn_stats,
                player_character=player_character,
                adjudication_context=adjudication_context,
                history_tools=history_tools,
                max_history_tool_rounds=max_history_tool_rounds,
            )
            result.outcome_decision = outcome
            if outcome is not OutcomeDecision.NOT_REQUIRED:
                result.failed = outcome is OutcomeDecision.FALLBACK
                self._log_verbose(
                    "state orchestration skipped: reason=outcome_{}",
                    outcome.value,
                )
                return result

            state_schema_names = {
                str(schema.get("function", {}).get("name", ""))
                for schema in self._schemas
                if isinstance(schema.get("function"), dict)
            } & set(self._state_tool_set.names)
            if not state_schema_names:
                self._log_verbose(
                    "state orchestration skipped: reason=no_state_write_tools"
                )
                return result

            route = await self._route_status(
                history=history,
                state_context=state_context,
                context_tables=context_tables,
                user_input=user_input,
                max_history_rounds=max_history_rounds,
                turn_stats=turn_stats,
                player_character=player_character,
                adjudication_context=adjudication_context,
                history_tools=history_tools,
                max_history_tool_rounds=max_history_tool_rounds,
            )
            result.route = route
            result.call_stats.extend(route.call_stats)
            if route.failed:
                result.failed = True
                self._log_verbose(
                    "state updates skipped: reason=router_failed"
                )
                return result

            await self._update_routed_state(
                route=route,
                context_tables=context_tables,
                scene_context=scene_context,
                history=history,
                user_input=user_input,
                max_history_rounds=max_history_rounds,
                result=result,
                turn_stats=turn_stats,
                player_character=player_character,
                adjudication_context=adjudication_context,
                history_tools=history_tools,
                max_history_tool_rounds=max_history_tool_rounds,
            )
            return result
        except _StatusPrewriteRollbackError as exc:
            result.failed = True
            logger.opt(exception=exc).error(
                _TAG + " preflight aborted: reason=mutation_boundary_failed"
            )
            raise
        except Exception as exc:
            result.failed = True
            logger.warning(_TAG + " fixed preflight failed: {}", exc)
            return result
        finally:
            route = result.route
            self._log_verbose(
                "preflight completed: outcome={}, route_failed={}, scene_selected={}, "
                "table_targets={}, records={}, changed_records={}, updated={}, failed={}",
                result.outcome_decision.value,
                route.failed if route is not None else False,
                route.scene if route is not None else False,
                len(route.targets) if route is not None else 0,
                len(result.records),
                sum(record.changed for record in result.records),
                result.updated,
                result.failed,
            )
            self._active_status_allowed_keys = None
            self._active_scene_allowed = True
            self._busy = False

    async def bootstrap_state(
        self,
        *,
        history: list[Message],
        scene_context: str,
        context_tables: list[dict[str, object]],
        max_history_rounds: int | None = None,
        turn_stats: TurnStats | None = None,
        player_character: "TurnPlayerCharacterSnapshot | None" = None,
    ) -> StatusBootstrapResult:
        """Rebuild all writable state targets from committed branch history.

        This path deliberately skips Outcome and routing.  The caller must bind
        scratch-backed state tools and commit only after ``failed`` is false.
        Any target failure restores the whole scratch checkpoint.
        """
        rounds = (
            settings.status_history_rounds
            if max_history_rounds is None
            else int(max_history_rounds)
        )
        if rounds <= 0:
            raise ValueError("max_history_rounds must be positive")
        processed_turns = len(SessionManager.iter_turn_groups(history))
        result = StatusBootstrapResult(processed_turns=processed_turns)
        if self._busy:
            result.failed = True
            return result

        batches: list[_RoutedStatusUpdateBatch] = []
        scene_tool_names = frozenset(
            name for name in self._state_tool_set.names if name in SCENE_TOOL_NAMES
        )
        if scene_tool_names:
            batches.append(_RoutedStatusUpdateBatch(
                source="status_bootstrap:scene",
                selected_context=scene_context,
                schema_names=scene_tool_names,
                allowed_status_keys=None,
                is_scene=True,
            ))
        for table in context_tables:
            table_id = int(table.get("id", 0))
            document = table.get("document")
            rows = document.get("rows", []) if isinstance(document, dict) else []
            allowed: list[str] = []
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                key = str(row.get("key") or "")
                if not key:
                    continue
                allowed.append(key)
            if table_id <= 0 or not allowed:
                continue
            allowed_keys = frozenset(allowed)
            batches.append(_RoutedStatusUpdateBatch(
                source=f"status_bootstrap:table:{table_id}",
                selected_context=self._render_selected_table(table, allowed_keys),
                schema_names=frozenset({STATUS_TABLE_SET_VALUES_TOOL_NAME}),
                allowed_status_keys={table_id: allowed_keys},
            ))
        writable_batches = [
            batch
            for batch in batches
            if self._schemas_for_names(set(batch.schema_names))
        ]
        if not writable_batches or processed_turns == 0:
            return result
        if not self._enabled:
            result.failed = True
            logger.warning(
                _TAG
                + " bootstrap required but status sub-agent is disabled: "
                "processed_turns={} writable_targets={}",
                processed_turns,
                len(writable_batches),
            )
            return result

        self._busy = True
        checkpoint: object | None = None
        try:
            try:
                checkpoint = (
                    self._mutation_checkpoint()
                    if self._mutation_checkpoint is not None
                    else None
                )
            except Exception as exc:
                raise _StatusPrewriteRollbackError(
                    "failed to create status bootstrap checkpoint"
                ) from exc
            recent = self._format_history_window(history, rounds)
            for batch in writable_batches:
                self._active_scene_allowed = batch.is_scene
                self._active_status_allowed_keys = batch.allowed_status_keys
                schemas = self._schemas_for_names(set(batch.schema_names))
                if not schemas:
                    continue
                messages = [
                    Message(
                        role=Role.SYSTEM,
                        content=self._build_system_context(
                            "你是 RPG 派生会话状态初始化器。只根据给出的已提交历史，"
                            "归纳当前目标在分支边界时的最终值。不得执行剧情裁定或猜测随机结果；"
                            "只能修改工具 schema 允许的已有字段；不确定时不要调用工具。",
                            player_character=player_character,
                        ),
                    ).to_dict(),
                    Message(
                        role=Role.USER,
                        content=(
                            f"## Committed Branch History\n{recent}\n\n"
                            f"## State Target\n{batch.selected_context}\n\n"
                            "根据完整历史窗口归纳该目标的边界状态。没有明确依据时保持原值。"
                        ),
                    ).to_dict(),
                ]
                llm_result, call_record = await self._chat_with_stats(
                    messages,
                    schemas,
                    source=batch.source,
                )
                self._append_call_record(result.call_stats, turn_stats, call_record)
                for name, args in (
                    _normalize_tool_call(call)
                    for call in self._tool_calls(llm_result)
                ):
                    if name not in batch.schema_names:
                        raise PermissionError(
                            "bootstrap tool is outside the current target scope"
                        )
                    record = await self._execute_tool_call(
                        name,
                        args,
                        track_mutation=True,
                    )
                    record.stage = StatusSubAgentStage.BOOTSTRAP
                    result.records.append(record)
                    if not record.success:
                        raise RuntimeError(
                            f"bootstrap tool failed: {name}: {record.result}"
                        )
            result.updated = any(record.changed for record in result.records)
            return result
        except _StatusPrewriteRollbackError:
            raise
        except Exception as exc:
            result.failed = True
            try:
                if self._mutation_restore is None or self._mutation_checkpoint is None:
                    if any(record.changed for record in result.records):
                        raise _StatusPrewriteRollbackError(
                            "status bootstrap mutation boundary is unavailable"
                        )
                else:
                    self._mutation_restore(checkpoint)
                    for record in result.records:
                        record.mark_rolled_back()
            except Exception as restore_exc:
                raise _StatusPrewriteRollbackError(
                    "failed to restore status bootstrap checkpoint"
                ) from restore_exc
            logger.opt(exception=exc).warning(_TAG + " bootstrap failed")
            result.updated = False
            return result
        finally:
            self._active_status_allowed_keys = None
            self._active_scene_allowed = True
            self._busy = False

    async def _decide_outcome(
        self,
        *,
        history: list[Message],
        state_context: str,
        user_input: str,
        max_history_rounds: int,
        result: StatusSubAgentResult,
        turn_stats: TurnStats | None,
        player_character: "TurnPlayerCharacterSnapshot | None",
        adjudication_context: AdjudicationContextSnapshot,
        history_tools: HistoryToolSet | None,
        max_history_tool_rounds: int,
    ) -> OutcomeDecision:
        outcome_schema = self._schemas_for_names({NARRATIVE_OUTCOME_TOOL_NAME})
        if not outcome_schema:
            self._log_verbose(
                "stage skipped: stage=outcome reason=outcome_tool_unavailable"
            )
            return OutcomeDecision.NOT_REQUIRED
        self._log_verbose(
            "stage started: stage=outcome history_messages={} state_chars={} "
            "user_input={!r}",
            len(history),
            len(state_context),
            user_input[:200],
        )
        recent = self._format_history_window(history, max_history_rounds)
        messages = self._adjudication_stage_messages(
            adjudication_context=adjudication_context,
            pipeline_prompt=OUTCOME_ONLY_SYSTEM_PROMPT,
            user_content=(
                f"## Current State\n\n{state_context}\n\n"
                f"## Recent Conversation\n\n{recent}\n\n"
                f"## User action\n{user_input}\n\n"
                "若存在两个或以上会实质改变剧情的合理结果，调用一次 "
                "rp_story_outcome；否则不要调用工具。"
            ),
            player_character=player_character,
        )
        llm_result, call_records = await self._run_adjudication_stage(
            messages,
            outcome_schema,
            source="status_outcome_preflight",
            history_tools=history_tools,
            max_history_tool_rounds=max_history_tool_rounds,
            turn_stats=turn_stats,
        )
        result.call_stats.extend(call_records)
        calls = [_normalize_tool_call(call) for call in self._tool_calls(llm_result)]
        if not calls:
            self._log_verbose(
                "stage completed: stage=outcome decision={} tool_calls=0",
                OutcomeDecision.NOT_REQUIRED.value,
            )
            return OutcomeDecision.NOT_REQUIRED
        if any(name != NARRATIVE_OUTCOME_TOOL_NAME for name, _args in calls):
            logger.warning(
                _TAG
                + " outcome stage returned invalid tools: tools={} decision={}",
                [name for name, _args in calls],
                OutcomeDecision.FALLBACK.value,
            )
            result.outcome_requested = True
            return OutcomeDecision.FALLBACK

        result.outcome_requested = True
        first_name, first_args = calls[0]
        record = await self._execute_tool_call(
            first_name,
            first_args,
            track_mutation=False,
            success_status=StatusSubAgentRecordStatus.OUTCOME_STAGED,
        )
        record.stage = StatusSubAgentStage.OUTCOME
        result.records.append(record)
        for name, args in calls[1:]:
            duplicate = StatusSubAgentToolRecord.skipped_duplicate_outcome(
                tool_name=name,
                arguments=args,
            )
            result.records.append(duplicate)
        result.outcome_staged = record.success
        decision = (
            OutcomeDecision.STAGED
            if record.success
            else OutcomeDecision.FALLBACK
        )
        self._log_verbose(
            "stage completed: stage=outcome decision={} tool_calls={} "
            "outcome_staged={} duplicate_calls={}",
            decision.value,
            len(calls),
            result.outcome_staged,
            max(len(calls) - 1, 0),
        )
        return decision

    async def _route_status(
        self,
        *,
        history: list[Message],
        state_context: str,
        context_tables: list[dict[str, object]],
        user_input: str,
        max_history_rounds: int,
        turn_stats: TurnStats | None,
        player_character: "TurnPlayerCharacterSnapshot | None",
        adjudication_context: AdjudicationContextSnapshot,
        history_tools: HistoryToolSet | None,
        max_history_tool_rounds: int,
    ) -> StatusRouteResult:
        route = StatusRouteResult()
        catalog, policy_index = self._status_catalog(context_tables)
        recent = self._format_history_window(history, max_history_rounds)
        scene_writable = any(
            name in SCENE_TOOL_NAMES for name in self._state_tool_set.names
        )
        self._log_verbose(
            "stage started: stage=router catalog_tables={} scene_writable={} "
            "history_messages={} user_input={!r}",
            len(catalog),
            scene_writable,
            len(history),
            user_input[:200],
        )
        route_schema = deepcopy(STATUS_ROUTER_SCHEMA)
        if not scene_writable:
            parameters = route_schema["function"]["parameters"]  # type: ignore[index]
            scene_schema = parameters["properties"]["scene"]  # type: ignore[index]
            scene_schema["const"] = False  # type: ignore[index]
            scene_schema["description"] = "本轮没有 scene 写入工具，必须为 false。"  # type: ignore[index]
        scene_constraint = (
            ""
            if scene_writable
            else "本轮没有 scene 写入工具，scene 必须为 false；"
        )
        messages = self._adjudication_stage_messages(
            adjudication_context=adjudication_context,
            pipeline_prompt=(
                "你是状态更新路由器。只选择本轮确实涉及的状态目标，不修改状态。"
                "字段的值只在事实明确且实际变化时选择；表 description 中的共同"
                "规则始终适用，若字段带 update_rule，还必须确认该字段专属规则"
                "已经满足。"
            ),
            user_content=(
                f"## Status Catalog\n{json.dumps(catalog, ensure_ascii=False)}\n\n"
                f"## Current State\n{state_context}\n\n"
                f"## Recent Conversation\n{recent}\n\n"
                f"## User action\n{user_input}\n\n"
                f"{scene_constraint}有目标时调用 select_status_targets；完全无关时不要调用。"
            ),
            player_character=player_character,
        )
        llm_result, call_records = await self._run_adjudication_stage(
            messages,
            [route_schema],
            source="status_router",
            history_tools=history_tools,
            max_history_tool_rounds=max_history_tool_rounds,
            turn_stats=turn_stats,
        )
        route.call_stats.extend(call_records)
        calls = [_normalize_tool_call(call) for call in self._tool_calls(llm_result)]
        if not calls:
            self._log_verbose(
                "stage completed: stage=router scene_selected=False "
                "table_targets=[] reason=no_targets"
            )
            return route
        if len(calls) != 1 or calls[0][0] != STATUS_ROUTER_TOOL_NAME:
            route.failed = True
            logger.warning(
                _TAG + " invalid status route tools: tools={}",
                [name for name, _args in calls],
            )
            self._log_verbose(
                "stage completed: stage=router scene_selected=False "
                "table_targets=[] failed=True"
            )
            return route
        try:
            payload = json.loads(calls[0][1])
            if not isinstance(payload, dict):
                raise TypeError("route arguments must be an object")
            raw_scene = payload.get("scene", False)
            if not isinstance(raw_scene, bool):
                raise TypeError("route scene must be a boolean")
            route.scene = raw_scene and scene_writable
            raw_targets = payload.get("tables", [])
            if not isinstance(raw_targets, list):
                raise TypeError("route tables must be an array")
            seen_tables: set[int] = set()
            for raw_target in raw_targets:
                if not isinstance(raw_target, dict):
                    continue
                table_id = int(raw_target.get("table_id", 0))
                if table_id <= 0 or table_id in seen_tables or table_id not in policy_index:
                    continue
                seen_tables.add(table_id)
                keys = self._validated_route_keys(
                    raw_target.get("keys"),
                    policy_index[table_id],
                )
                if keys:
                    route.targets.append(StatusRouteTarget(
                        table_id=table_id,
                        keys=keys,
                        reason=str(raw_target.get("reason") or "")[:500],
                    ))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning(_TAG + " invalid status route: {}", exc)
            route.failed = True
        self._log_verbose(
            "stage completed: stage=router scene_selected={} table_targets={} failed={}",
            route.scene,
            [
                {
                    "table_id": target.table_id,
                    "keys": list(target.keys),
                    "reason": target.reason,
                }
                for target in route.targets
            ],
            route.failed,
        )
        return route

    async def _update_routed_state(
        self,
        *,
        route: StatusRouteResult,
        context_tables: list[dict[str, object]],
        scene_context: str,
        history: list[Message],
        user_input: str,
        max_history_rounds: int,
        result: StatusSubAgentResult,
        turn_stats: TurnStats | None,
        player_character: "TurnPlayerCharacterSnapshot | None",
        adjudication_context: AdjudicationContextSnapshot,
        history_tools: HistoryToolSet | None,
        max_history_tool_rounds: int,
    ) -> None:
        tables_by_id = {int(table.get("id", 0)): table for table in context_tables}
        recent = self._format_history_window(history, max_history_rounds)
        batches: list[_RoutedStatusUpdateBatch] = []
        scene_tool_names = frozenset(
            name for name in self._state_tool_set.names if name in SCENE_TOOL_NAMES
        )
        if route.scene and scene_tool_names:
            batches.append(_RoutedStatusUpdateBatch(
                source="status_update:scene",
                selected_context=scene_context,
                schema_names=scene_tool_names,
                allowed_status_keys=None,
                is_scene=True,
            ))
        for target in route.targets:
            table = tables_by_id.get(target.table_id)
            if table is None:
                self._log_verbose(
                    "update target skipped: source=status_update:table:{} "
                    "reason=table_not_found",
                    target.table_id,
                )
                continue
            allowed = frozenset(target.keys)
            if not allowed:
                self._log_verbose(
                    "update target skipped: source=status_update:table:{} "
                    "reason=no_allowed_keys",
                    target.table_id,
                )
                continue
            batches.append(_RoutedStatusUpdateBatch(
                source=f"status_update:table:{target.table_id}",
                selected_context=self._render_selected_table(table, allowed),
                schema_names=frozenset({STATUS_TABLE_SET_VALUES_TOOL_NAME}),
                allowed_status_keys={target.table_id: allowed},
            ))

        self._log_verbose(
            "stage started: stage=state_updates planned_targets={}",
            [batch.source for batch in batches],
        )
        for batch in batches:
            self._active_scene_allowed = batch.is_scene
            self._active_status_allowed_keys = batch.allowed_status_keys
            schemas = self._schemas_for_names(set(batch.schema_names))
            if not schemas:
                self._log_verbose(
                    "update target skipped: source={} reason=no_matching_schema "
                    "requested_tools={}",
                    batch.source,
                    sorted(batch.schema_names),
                )
                continue
            self._log_verbose(
                "update target started: source={} scene={} tools={} allowed_status_keys={}",
                batch.source,
                batch.is_scene,
                sorted(batch.schema_names),
                (
                    {
                        table_id: sorted(keys)
                        for table_id, keys in batch.allowed_status_keys.items()
                    }
                    if batch.allowed_status_keys is not None
                    else None
                ),
            )
            try:
                checkpoint = (
                    self._mutation_checkpoint()
                    if self._mutation_checkpoint is not None
                    else None
                )
            except Exception as exc:
                raise _StatusPrewriteRollbackError(
                    "failed to create status update target checkpoint"
                ) from exc
            record_start = len(result.records)
            try:
                messages = self._adjudication_stage_messages(
                    adjudication_context=adjudication_context,
                    pipeline_prompt=ROUTED_STATE_UPDATE_SYSTEM_PROMPT,
                    user_content=(
                        f"## Recent Conversation\n{recent}\n\n"
                        f"## User Action\n{user_input}\n\n"
                        f"## Selected State Target\n{batch.selected_context}\n\n"
                        "只更新这里列出的、已经确定且实际变化的值；没有变化不要调用工具。"
                    ),
                    player_character=player_character,
                )
                llm_result, call_records = await self._run_adjudication_stage(
                    messages,
                    schemas,
                    source=batch.source,
                    history_tools=history_tools,
                    max_history_tool_rounds=max_history_tool_rounds,
                    turn_stats=turn_stats,
                )
                result.call_stats.extend(call_records)
                batch_failed = False
                normalized_calls = [
                    _normalize_tool_call(call) for call in self._tool_calls(llm_result)
                ]
                self._log_verbose(
                    "update target decision: source={} tool_calls={}",
                    batch.source,
                    [name for name, _args in normalized_calls],
                )
                for name, args in normalized_calls:
                    if name not in batch.schema_names:
                        result.records.append(StatusSubAgentToolRecord(
                            tool_name=name,
                            arguments=args,
                            result="Error: tool is outside the current fixed stage",
                            success=False,
                            changed=False,
                            status=StatusSubAgentRecordStatus.ERROR,
                            stage=StatusSubAgentStage.IMMEDIATE,
                        ))
                        batch_failed = True
                        break
                    record = await self._execute_tool_call(
                        name,
                        args,
                        track_mutation=True,
                    )
                    record.stage = StatusSubAgentStage.IMMEDIATE
                    result.records.append(record)
                    if not record.success:
                        batch_failed = True
                        break
                if batch_failed:
                    result.failed = True
                    self._restore_failed_update_target(
                        checkpoint,
                        result.records[record_start:],
                    )
                    logger.warning(
                        _TAG
                        + " status update target failed and was restored: {} statuses={}",
                        batch.source,
                        [
                            record.status.value
                            for record in result.records[record_start:]
                        ],
                    )
                else:
                    self._log_verbose(
                        "update target completed: source={} tool_calls={} statuses={} "
                        "changed_records={}",
                        batch.source,
                        len(normalized_calls),
                        [
                            record.status.value
                            for record in result.records[record_start:]
                        ],
                        sum(
                            record.changed
                            for record in result.records[record_start:]
                        ),
                    )
            except _StatusPrewriteRollbackError:
                raise
            except Exception as exc:
                result.failed = True
                self._restore_failed_update_target(
                    checkpoint,
                    result.records[record_start:],
                )
                logger.warning(
                    _TAG
                    + " status update target failed and was restored: {}: {} statuses={}",
                    batch.source,
                    exc,
                    [
                        record.status.value
                        for record in result.records[record_start:]
                    ],
                )

        result.updated = any(
            record.changed
            for record in result.records
            if record.stage is not StatusSubAgentStage.OUTCOME
        )
        self._log_verbose(
            "stage completed: stage=state_updates planned_targets={} records={} "
            "changed_records={} updated={} failed={}",
            len(batches),
            len([
                record
                for record in result.records
                if record.stage is not StatusSubAgentStage.OUTCOME
            ]),
            sum(
                record.changed
                for record in result.records
                if record.stage is not StatusSubAgentStage.OUTCOME
            ),
            result.updated,
            result.failed,
        )

    def _restore_failed_update_target(
        self,
        checkpoint: object | None,
        records: list[StatusSubAgentToolRecord],
    ) -> None:
        """Restore only the failed scene or single-table update target."""
        changed = any(record.changed for record in records)
        if self._mutation_restore is None or self._mutation_checkpoint is None:
            if changed:
                raise _StatusPrewriteRollbackError(
                    "status prewrite mutation boundary is unavailable"
                )
            return
        try:
            self._mutation_restore(checkpoint)
        except Exception as exc:
            raise _StatusPrewriteRollbackError(
                "failed to restore status update target checkpoint"
            ) from exc
        for record in records:
            record.mark_rolled_back()

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
            self._validate_active_scope(name, args)
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

    def _adjudication_stage_messages(
        self,
        *,
        adjudication_context: AdjudicationContextSnapshot,
        pipeline_prompt: str,
        user_content: str,
        player_character: "TurnPlayerCharacterSnapshot | None",
    ) -> list[Message]:
        if adjudication_context.active:
            messages = adjudication_context.to_messages()
            messages.append(Message(Role.SYSTEM, pipeline_prompt))
        else:
            # Direct unit/bootstrap-style callers may omit a turn plan. Keep
            # their narrow lore/character projection without affecting the
            # production turn path, which always supplies the shared snapshot.
            messages = [
                Message(
                    Role.SYSTEM,
                    self._build_system_context(
                        pipeline_prompt,
                        player_character=player_character,
                    ),
                )
            ]
        messages.append(Message(Role.USER, user_content))
        return messages

    async def _run_adjudication_stage(
        self,
        messages: list[Message],
        schemas: list[dict[str, object]],
        *,
        source: str,
        history_tools: HistoryToolSet | None,
        max_history_tool_rounds: int,
        turn_stats: TurnStats | None,
    ) -> tuple[_LLMChatResult, tuple[CallRecord, ...]]:
        schema_names = [
            str(schema.get("function", {}).get("name", ""))
            for schema in schemas
            if isinstance(schema.get("function"), dict)
        ]
        self._log_verbose(
            "LLM call started: source={} messages={} tools={}",
            source,
            len(messages),
            schema_names,
        )
        loop_result = await run_adjudication_tool_loop(
            provider=await self._get_provider(),
            messages=messages,
            terminal_schemas=schemas,
            source=source,
            history_tools=history_tools,
            max_history_tool_rounds=max_history_tool_rounds,
            turn_stats=turn_stats,
        )
        for record in loop_result.call_records:
            self._log_cache_usage(source, record.usage)
        self._log_verbose(
            "LLM call completed: source={} provider_calls={} history_rounds={} "
            "tool_calls={}",
            source,
            len(loop_result.call_records),
            loop_result.history_rounds,
            self._tool_names_for_log(loop_result.response),
        )
        return loop_result.response, loop_result.call_records

    async def _chat_with_stats(
        self,
        messages: list[dict],
        schemas: list[dict[str, object]],
        *,
        source: str,
    ) -> tuple[_LLMChatResult, CallRecord | None]:
        import time

        schema_names = [
            str(schema.get("function", {}).get("name", ""))
            for schema in schemas
            if isinstance(schema.get("function"), dict)
        ]
        self._log_verbose(
            "LLM call started: source={} messages={} tools={}",
            source,
            len(messages),
            schema_names,
        )
        if settings.verbose_logging:
            fingerprint = build_request_fingerprint(
                messages,
                schemas,
            )
            self._log_verbose(
                "LLM request fingerprint: source={} contextHash={} contextChars={} "
                "systemHash={} systemChars={} toolsHash={} toolsChars={} "
                "messages={} roles={} tools={} messageShape={}",
                source,
                *request_fingerprint_log_values(fingerprint),
            )
        t0 = time.monotonic()
        try:
            provider = await self._get_provider()
            llm_result = await provider.chat(messages, tools=schemas)
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            logger.opt(exception=exc).warning(
                _TAG + " LLM call failed: source={} duration_ms={:.1f}",
                source,
                duration_ms,
            )
            raise
        duration_ms = (time.monotonic() - t0) * 1000
        if isinstance(llm_result, dict):
            self._log_verbose(
                "LLM call completed: source={} duration_ms={:.1f} model={} "
                "finish_reason={} tool_calls={} usage={}",
                source,
                duration_ms,
                str(llm_result.get("model") or "-"),
                str(llm_result.get("finish_reason") or "-"),
                self._tool_names_for_log(llm_result),
                "(unavailable)",
            )
            return llm_result, None
        if not isinstance(llm_result, LLMResponse):
            logger.warning(
                _TAG + " LLM call returned invalid response: source={} type={}",
                source,
                type(llm_result).__name__,
            )
            raise TypeError(
                "LLM provider chat() must return LLMResponse or a mapping test double"
        )
        model = llm_result.model or provider.get_default_model()
        self._log_cache_usage(source, llm_result.usage)
        self._log_verbose(
            "LLM call completed: source={} duration_ms={:.1f} model={} "
            "finish_reason={} tool_calls={} usage={}",
            source,
            duration_ms,
            model,
            llm_result.finish_reason or "-",
            self._tool_names_for_log(llm_result),
            str(llm_result.usage) if llm_result.usage is not None else "(no usage)",
        )
        return llm_result, CallRecord(
            source=source,
            model=model,
            usage=llm_result.usage,
            duration_ms=duration_ms,
            reasoning_content=llm_result.reasoning_content,
        )

    def _log_cache_usage(self, source: str, usage: LLMUsage | None) -> None:
        if not settings.verbose_logging:
            return
        if usage is None:
            logger.info(
                _TAG + " LLM cache usage: source={} hit=- miss=- rate=-",
                source,
            )
            return

        hit = max(0, int(usage.cached_tokens or 0))
        miss = max(0, int(usage.prompt_cache_miss_tokens or 0))
        prompt_tokens = max(0, int(usage.prompt_tokens or 0))
        if miss == 0 and prompt_tokens > hit:
            miss = prompt_tokens - hit
        cache_tokens = hit + miss
        rate = hit / cache_tokens * 100 if cache_tokens else 0.0
        logger.info(
            _TAG + " LLM cache usage: source={} hit={} miss={} rate={:.1f}%",
            source,
            hit,
            miss,
            rate,
        )

    @staticmethod
    def _append_call_record(
        records: list[CallRecord],
        turn_stats: TurnStats | None,
        record: CallRecord | None,
    ) -> None:
        if record is None:
            return
        records.append(record)
        if turn_stats is not None:
            turn_stats.add_call(record)

    @staticmethod
    def _tool_calls(llm_result: _LLMChatResult) -> list[object]:
        if isinstance(llm_result, LLMResponse):
            raw = llm_result.tool_calls
        else:
            raw = llm_result.get("tool_calls")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise TypeError("LLM tool_calls must be an array or null")
        return list(raw)

    @staticmethod
    def _tool_names_for_log(llm_result: _LLMChatResult) -> list[str]:
        raw = (
            llm_result.tool_calls
            if isinstance(llm_result, LLMResponse)
            else llm_result.get("tool_calls")
        )
        if raw is None:
            return []
        if not isinstance(raw, list):
            return ["<invalid_tool_calls>"]
        return [
            name or "<invalid_tool_call>"
            for name, _args in (_normalize_tool_call(call) for call in raw)
        ]

    def _schemas_for_names(self, names: set[str]) -> list[dict[str, object]]:
        return [
            schema
            for schema in self._schemas
            if isinstance(schema.get("function"), dict)
            and str(schema["function"].get("name", "")) in names  # type: ignore[index]
        ]

    @staticmethod
    def _status_catalog(
        context_tables: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], dict[int, frozenset[str]]]:
        catalog: list[dict[str, object]] = []
        index: dict[int, frozenset[str]] = {}
        for table in context_tables:
            table_id = int(table.get("id", 0))
            document = table.get("document")
            if table_id <= 0 or not isinstance(document, dict):
                continue
            raw_rows = document.get("rows")
            if not isinstance(raw_rows, list):
                continue
            fields: list[dict[str, object]] = []
            keys: set[str] = set()
            for raw_row in raw_rows:
                if not isinstance(raw_row, dict):
                    continue
                key = str(raw_row.get("key") or "")
                if not key:
                    continue
                rule = str(raw_row.get(STATUS_ROW_UPDATE_RULE_KEY) or "")
                keys.add(key)
                fields.append({
                    "key": key,
                    "value": str(raw_row.get("value") or ""),
                    "update_rule": rule,
                })
            index[table_id] = frozenset(keys)
            catalog.append({
                "table_id": table_id,
                "name": str(table.get("name") or ""),
                "description": str(table.get("description") or ""),
                "fields": fields,
            })
        return catalog, index

    @staticmethod
    def _validated_route_keys(
        raw_keys: object,
        existing_keys: frozenset[str],
    ) -> tuple[str, ...]:
        if not isinstance(raw_keys, list):
            return ()
        result: list[str] = []
        seen: set[str] = set()
        for raw_key in raw_keys:
            key = str(raw_key or "")
            if not key or key in seen or key not in existing_keys:
                continue
            seen.add(key)
            result.append(key)
        return tuple(result)

    @staticmethod
    def _render_selected_table(
        table: dict[str, object],
        allowed_keys: frozenset[str],
    ) -> str:
        document = table.get("document")
        rows = document.get("rows", []) if isinstance(document, dict) else []
        selected_rows = [
            row
            for row in rows
            if isinstance(row, dict)
            and str(row.get("key") or "") in allowed_keys
        ]
        return json.dumps(
            {
                "table_id": int(table.get("id", 0)),
                "name": str(table.get("name") or ""),
                "description": str(table.get("description") or ""),
                "rows": selected_rows,
            },
            ensure_ascii=False,
        )

    def _validate_active_scope(self, name: str, args: str) -> None:
        if name in SCENE_TOOL_NAMES and not self._active_scene_allowed:
            raise PermissionError("scene tools are outside the routed update scope")
        if name != STATUS_TABLE_SET_VALUES_TOOL_NAME:
            return
        if self._active_status_allowed_keys is None:
            return
        try:
            payload = json.loads(args)
            table_id = int(payload.get("table_id", 0))
            updates = payload.get("updates", [])
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid scoped status tool arguments") from exc
        allowed = self._active_status_allowed_keys.get(table_id, frozenset())
        if not isinstance(updates, list) or not updates:
            raise PermissionError("status update is outside the routed update scope")
        keys = {
            str(item.get("key", ""))
            for item in updates
            if isinstance(item, dict)
        }
        if not keys or not keys.issubset(allowed):
            raise PermissionError("status update is outside the routed update scope")

    def clear_tools(self) -> None:
        """清空已注册的工具集（重新注册前调用避免重复）。"""
        self._tool_registry = ToolRegistry()
        self._schemas = []
        self._state_tool_set = StateToolSet()

    # ── internal helpers ──────────────────────────────────────────────

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
            lines.append(f"{label}: {content}")

        return "\n\n".join(lines) if lines else "(no recent conversation)"
