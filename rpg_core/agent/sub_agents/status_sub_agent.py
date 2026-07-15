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
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterator, TypeAlias

from loguru import logger

from rpg_data.models import (
    STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY,
    STATUS_ROW_UPDATE_FREQUENCY_KEY,
    STATUS_ROW_UPDATE_RULE_KEY,
    STATUS_UPDATE_FREQUENCY_DEFERRED,
    STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
    STATUS_UPDATE_FREQUENCY_REALTIME,
)
from rpg_core.agent.agent_types import CallRecord, LLMResponse, LLMUsage, TurnStats
from rpg_core.agent.sub_agents.base import BaseSubAgent
from rpg_core.agent.sub_agents.status_sub_agent_models import (
    DeferredStatusResult,
    OutcomeDecision,
    StatusRouteResult,
    StatusRouteTarget,
    StatusSubAgentRecordStatus,
    StatusSubAgentResult,
    StatusSubAgentStage,
    StatusSubAgentToolRecord,
)
from rpg_core.agent.tools import BaseTool
from rpg_core.agent.tools.registry import ToolRegistry
from rpg_core.agent.tools.state import STATE_TOOL_NAMES, StateToolSet
from rpg_core.context.rpg_context import Message, Role
from rpg_core.context.fingerprint import (
    build_request_fingerprint,
    request_fingerprint_log_values,
)
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_TOOL_NAME
from rpg_core.scene import (
    SCENE_DELETE_ATTR_TOOL_NAME,
    SCENE_TOOL_NAMES,
)
from rpg_core.session.manager import SessionManager
from rpg_core.settings import settings
from rpg_core.status.tools import STATUS_TABLE_SET_VALUES_TOOL_NAME

if TYPE_CHECKING:

    from rpg_core.agent.sub_agents.context import SubAgentContext
    from rpg_core.agent.turn.models import TurnPlayerCharacterSnapshot
    from rpg_core.status.manager import StatusManager

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

# ── system prompt ─────────────────────────────────────────────────────

def _build_state_system_prompt(state_tools: StateToolSet) -> str:
    scene_names = tuple(name for name in state_tools.names if name in SCENE_TOOL_NAMES)
    operation_lines: list[str] = []
    if scene_names:
        operation_lines.append(
            f"- {' / '.join(scene_names)}：更新当前场景状态"
            "（时间、地点、天气、氛围、在场的 NPC 等）"
        )
    if state_tools.supports(STATUS_TABLE_SET_VALUES_TOOL_NAME):
        operation_lines.append(
            "- status_table_set_values：批量更新普通状态表中已有键的值"
        )
    if not operation_lines:
        operation_lines.append("- 本轮没有状态写入工具；当前场景和普通状态表均为只读")

    if state_tools.supports(SCENE_DELETE_ATTR_TOOL_NAME):
        scene_boundary = (
            "3. 主动清理：如果某个属性不再与当前场景相关"
            "（例如角色离开了、某种天气效果消失了），"
            "使用 scene_del_attr 将其移除。只保留活跃属性可以防止上下文膨胀。"
        )
    elif scene_names:
        scene_boundary = (
            "3. scene 与普通状态表一样，只能修改已有 key 的 value，不能新增、删除或重命名 key。"
            "若某个现有属性暂时不适用，将该现有 key 的 value 更新为空字符串或当前适用值。"
        )
    else:
        scene_boundary = "3. 本轮未提供 scene 写入工具，当前 scene 仅供读取。"

    normal_boundary = (
        "4. 普通状态表不得新增、删除或重命名键；角色状态表只追踪对应角色。"
        if state_tools.supports(STATUS_TABLE_SET_VALUES_TOOL_NAME)
        else "4. 本轮未提供普通状态表写入工具，普通状态表仅供读取。"
    )
    return (
        "你是 RPG 游戏世界的状态表预处理器。\n\n"
        "可用操作及其修改的状态表：\n"
        + "\n".join(operation_lines)
        + "\n\n状态更新边界：\n"
        "1. 只依据既有 assistant 已确认事实、用户对既有事实的明确纠正，或没有随机分支的确定性动作"
        "更新状态。用户单方面宣称的未决外部结果不是已确认事实。\n"
        "2. 仅当实际、持久、已经确定的追踪值发生变化时调用状态工具；不要修改没有变化的属性，"
        "不要制造 no-op。没有裁定且没有状态变化时，不调用任何工具。\n"
        f"{scene_boundary}\n"
        f"{normal_boundary}\n"
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

OUTCOME_ONLY_SYSTEM_PROMPT = (
    "你是 RPG 剧情裁定门禁。只判断当前玩家行动是否存在外部实质变数。\n"
    "需要裁定时只调用一次 rp_story_outcome；不需要时不调用任何工具。\n"
    "不得更新状态、不得虚构结果。"
)

ROUTED_STATE_UPDATE_SYSTEM_PROMPT = (
    "你是 RPG 游戏世界的单目标状态更新器。当前请求只包含一个已经路由的状态目标。\n\n"
    "执行契约：\n"
    "1. 只能使用本请求实际提供的工具；未提供的工具视为不存在，不得请求或假设其它 "
    "scene 或状态工具。\n"
    "2. 只依据既有 assistant 已确认事实、用户对既有事实的明确纠正，或没有随机分支的"
    "确定性动作更新状态；不得把未决外部结果当作事实。\n"
    "3. 仅当实际、持久、已经确定的追踪值发生变化时调用工具；不要制造 no-op，"
    "没有变化时不调用任何工具。\n"
    "4. 严格遵守当前工具 schema 的目标、字段和参数约束。只有实际提供的 schema 明确允许时"
    "才能改变 key 结构，否则只能修改已有 key 的 value。\n"
    "5. key 和 value 使用目标状态已有的语言与格式。"
)

STATUS_ROUTER_TOOL_NAME = "select_status_targets"
STATUS_ROUTER_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": STATUS_ROUTER_TOOL_NAME,
        "description": "选择本轮确实涉及的场景和普通状态表字段；没有涉及项时不要调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "scene": {"type": "boolean"},
                "tables": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "table_id": {"type": "integer"},
                            "realtime_keys": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "event_keys": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["table_id", "realtime_keys", "event_keys", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["scene", "tables"],
            "additionalProperties": False,
        },
    },
}

DEFERRED_STATUS_TOOL_NAME = "set_deferred_values"
DEFERRED_STATUS_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": DEFERRED_STATUS_TOOL_NAME,
        "description": "归纳并更新本批允许的 deferred 状态字段。没有变化时不要调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["key", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["updates"],
            "additionalProperties": False,
        },
    },
}

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
        self._outcome_preflight_enabled = False
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
        outcome_preflight_enabled: bool | None = None,
    ) -> Iterator[None]:
        """Temporarily bind tools and rollback callbacks for one turn."""
        previous_registry = self._tool_registry
        previous_schemas = self._schemas
        previous_state_tool_set = self._state_tool_set
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
            self._state_tool_set = previous_state_tool_set
            self.set_mutation_probe(previous_probe)
            self.set_mutation_boundary(previous_checkpoint, previous_restore)
            self._outcome_preflight_enabled = previous_outcome_preflight_enabled

    # ── Context 绑定（覆盖基类） ─────────────────────────────────────

    def bind_context(self, context: SubAgentContext) -> None:
        """绑定 SubAgentContext，同时刷新所有工具提供者的工具。"""
        self.clear_tools()
        self.register_tools(self._collect_provider_tools())
        super().bind_context(context)

    # ── 核心方法 ─────────────────────────────────────────────────────

    @property
    def system_prompt(self) -> str:
        """返回状态表预更新子 Agent 的系统提示。"""
        base_prompt = _build_state_system_prompt(self._state_tool_set)
        if self._outcome_preflight_enabled:
            return base_prompt + NARRATIVE_OUTCOME_SYSTEM_PROMPT
        return base_prompt

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
        max_history_rounds: int = 5,
        turn_stats: TurnStats | None = None,
        player_character: "TurnPlayerCharacterSnapshot | None" = None,
    ) -> StatusSubAgentResult:
        """Run the fixed outcome -> route -> selected-update pipeline."""
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

    async def reconcile_deferred(
        self,
        *,
        session_manager: SessionManager,
        status_manager: "StatusManager",
    ) -> DeferredStatusResult:
        """Reconcile due deferred fields from committed history only."""
        if self._busy:
            logger.debug(
                _TAG + " deferred reconciliation skipped: reason=reentrancy_guard"
            )
            return DeferredStatusResult()
        if not self._enabled:
            self._log_verbose(
                "deferred reconciliation skipped: reason=disabled"
            )
            return DeferredStatusResult()

        history = session_manager.history
        groups = SessionManager.iter_turn_groups(history)
        if not groups:
            self._log_verbose(
                "deferred reconciliation skipped: reason=no_committed_turns"
            )
            return DeferredStatusResult()
        latest_turn_id = SessionManager.latest_turn_id(history)
        status_manager.clamp_deferred_progress(latest_turn_id)
        progress = {
            (item.session_status_table_id, item.field_key):
                item.last_processed_turn_id
            for item in status_manager.list_deferred_progress()
        }
        default_interval = settings.status_deferred_default_interval_turns
        batches: list[tuple[int, int, tuple[str, ...], list[Message]]] = []
        for table in status_manager.list_context_tables():
            table_id = int(table.get("id", 0))
            document = table.get("document")
            rows = document.get("rows", []) if isinstance(document, dict) else []
            due_by_boundary: dict[int, list[str]] = {}
            history_by_boundary: dict[int, list[Message]] = {}
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                if str(
                    row.get(STATUS_ROW_UPDATE_FREQUENCY_KEY)
                    or STATUS_UPDATE_FREQUENCY_REALTIME
                ) != STATUS_UPDATE_FREQUENCY_DEFERRED:
                    continue
                key = str(row.get("key") or "")
                if not key:
                    continue
                interval = row.get(STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY)
                interval = (
                    int(interval)
                    if isinstance(interval, int) and not isinstance(interval, bool)
                    else default_interval
                )
                marker = progress.get((table_id, key), 0)
                eligible = [
                    group
                    for group in groups
                    if max((message.turn_id for message in group), default=0) > marker
                ]
                if len(eligible) < interval:
                    continue
                selected_groups = eligible[:interval]
                boundary = max(
                    message.turn_id
                    for group in selected_groups
                    for message in group
                )
                due_by_boundary.setdefault(boundary, []).append(key)
                history_by_boundary[boundary] = [
                    message
                    for group in selected_groups
                    for message in group
                ]
            for boundary, keys in due_by_boundary.items():
                batches.append((
                    table_id,
                    boundary,
                    tuple(keys),
                    history_by_boundary[boundary],
                ))

        if not batches:
            self._log_verbose(
                "deferred reconciliation skipped: reason=no_due_fields "
                "latest_turn_id={}",
                latest_turn_id,
            )
            return DeferredStatusResult()

        self._busy = True
        batch_count = field_count = changed_count = 0
        self._log_verbose(
            "deferred reconciliation started: latest_turn_id={} batches={}",
            latest_turn_id,
            [
                {
                    "table_id": table_id,
                    "boundary": boundary,
                    "keys": list(allowed_keys),
                }
                for table_id, boundary, allowed_keys, _history in batches
            ],
        )
        try:
            for table_id, boundary, allowed_keys, batch_history in batches:
                self._log_verbose(
                    "deferred batch started: table_id={} boundary={} keys={} "
                    "history_messages={}",
                    table_id,
                    boundary,
                    list(allowed_keys),
                    len(batch_history),
                )
                try:
                    changed = await self._reconcile_deferred_batch(
                        table_id=table_id,
                        boundary=boundary,
                        allowed_keys=allowed_keys,
                        batch_history=batch_history,
                        default_interval=default_interval,
                        status_manager=status_manager,
                    )
                except Exception as exc:
                    logger.opt(exception=exc).warning(
                        _TAG
                        + " deferred batch failed: table_id={}, boundary={}, keys={}",
                        table_id,
                        boundary,
                        allowed_keys,
                    )
                    continue
                batch_count += 1
                field_count += len(allowed_keys)
                changed_count += changed
                self._log_verbose(
                    "deferred batch completed: table_id={} boundary={} keys={} "
                    "changed_fields={}",
                    table_id,
                    boundary,
                    list(allowed_keys),
                    changed,
                )
        finally:
            self._busy = False
        deferred_result = DeferredStatusResult(
            batches=batch_count,
            fields=field_count,
            changed=changed_count,
        )
        self._log_verbose(
            "deferred reconciliation completed: batches={} fields={} changed={}",
            deferred_result.batches,
            deferred_result.fields,
            deferred_result.changed,
        )
        return deferred_result

    async def _reconcile_deferred_batch(
        self,
        *,
        table_id: int,
        boundary: int,
        allowed_keys: tuple[str, ...],
        batch_history: list[Message],
        default_interval: int,
        status_manager: "StatusManager",
    ) -> int:
        base_document = status_manager.get_table_document_by_id(table_id)
        selected_rows = [
            {
                "key": row.key,
                "value": row.value,
                "interval_turns": row.deferred_interval_turns or default_interval,
            }
            for row in base_document.rows
            if row.key in allowed_keys
        ]
        recent = self._format_history_window(
            batch_history,
            max(len(SessionManager.iter_turn_groups(batch_history)), 1),
        )
        messages = [
            Message(
                role=Role.SYSTEM,
                content=self._build_system_context(
                    "你是 RPG 慢状态归纳器。只根据已提交历史归纳允许的 deferred 字段。"
                    "只有长期、明确且持久的变化才更新；不确定或无变化时不调用工具。"
                ),
            ).to_dict(),
            Message(
                role=Role.USER,
                content=(
                    f"## Allowed Deferred Fields\n"
                    f"{json.dumps(selected_rows, ensure_ascii=False)}\n\n"
                    f"## Committed Turns\n{recent}"
                ),
            ).to_dict(),
        ]
        llm_result, _call_record = await self._chat_with_stats(
            messages,
            [DEFERRED_STATUS_SCHEMA],
            source="status_deferred",
        )
        calls = [
            _normalize_tool_call(call)
            for call in self._tool_calls(llm_result)
        ]
        updates: list[tuple[str, str]] = []
        if calls:
            if len(calls) != 1 or calls[0][0] != DEFERRED_STATUS_TOOL_NAME:
                raise ValueError("deferred status returned an invalid tool call")
            payload = json.loads(calls[0][1])
            if not isinstance(payload, dict):
                raise ValueError("deferred status arguments must be an object")
            raw_updates = payload.get("updates", [])
            if not isinstance(raw_updates, list):
                raise ValueError("deferred updates must be an array")
            seen: set[str] = set()
            for item in raw_updates:
                if not isinstance(item, dict):
                    raise ValueError("deferred update must be an object")
                key = str(item.get("key") or "")
                value = item.get("value")
                if key not in allowed_keys or key in seen or not isinstance(value, str):
                    raise PermissionError(
                        "deferred update is outside the allowed field scope"
                    )
                seen.add(key)
                updates.append((key, value))
        updated_document = (
            base_document.with_existing_values(updates)
            if updates
            else base_document
        )
        status_manager.commit_deferred_update(
            table_id,
            updated_document,
            processed_keys=allowed_keys,
            last_processed_turn_id=boundary,
            base_document=base_document,
        )
        return sum(
            row is not None and row.value != value
            for key, value in updates
            if (row := base_document.row_for_key(key)) is not None
        )

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
        messages = [
            Message(
                role=Role.SYSTEM,
                content=self._build_system_context(
                    OUTCOME_ONLY_SYSTEM_PROMPT,
                    player_character=player_character,
                ),
            ).to_dict(),
            Message(
                role=Role.USER,
                content=(
                    f"## Current State\n\n{state_context}\n\n"
                    f"## Recent Conversation\n\n{recent}\n\n"
                    f"## User action\n{user_input}\n\n"
                    "若存在两个或以上会实质改变剧情的合理结果，调用一次 "
                    "rp_story_outcome；否则不要调用工具。"
                ),
            ).to_dict(),
        ]
        llm_result, call_record = await self._chat_with_stats(
            messages,
            outcome_schema,
            source="status_outcome_preflight",
        )
        self._append_call_record(result.call_stats, turn_stats, call_record)
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
        messages = [
            Message(
                role=Role.SYSTEM,
                content=self._build_system_context(
                    "你是状态更新路由器。只选择本轮确实涉及的状态目标，不修改状态。"
                    "realtime 字段在相关时选择；event_driven 只有显式规则已被确认事件命中时选择；"
                    "deferred/manual 永远不要选择。",
                    player_character=player_character,
                ),
            ).to_dict(),
            Message(
                role=Role.USER,
                content=(
                    f"## Status Catalog\n{json.dumps(catalog, ensure_ascii=False)}\n\n"
                    f"## Current State\n{state_context}\n\n"
                    f"## Recent Conversation\n{recent}\n\n"
                    f"## User action\n{user_input}\n\n"
                    f"{scene_constraint}有目标时调用 select_status_targets；完全无关时不要调用。"
                ),
            ).to_dict(),
        ]
        llm_result, call_record = await self._chat_with_stats(
            messages,
            [route_schema],
            source="status_router",
        )
        self._append_call_record(route.call_stats, turn_stats, call_record)
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
                policies = policy_index[table_id]
                realtime = self._validated_route_keys(
                    raw_target.get("realtime_keys"),
                    policies,
                    frequency=STATUS_UPDATE_FREQUENCY_REALTIME,
                )
                event = self._validated_route_keys(
                    raw_target.get("event_keys"),
                    policies,
                    frequency=STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
                )
                if realtime or event:
                    route.targets.append(StatusRouteTarget(
                        table_id=table_id,
                        realtime_keys=realtime,
                        event_keys=event,
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
                    "realtime_keys": list(target.realtime_keys),
                    "event_keys": list(target.event_keys),
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
            allowed = frozenset((*target.realtime_keys, *target.event_keys))
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
            checkpoint = (
                self._mutation_checkpoint()
                if self._mutation_checkpoint is not None
                else None
            )
            record_start = len(result.records)
            try:
                messages = [
                    Message(
                        role=Role.SYSTEM,
                        content=self._build_system_context(
                            ROUTED_STATE_UPDATE_SYSTEM_PROMPT,
                            player_character=player_character,
                        ),
                    ).to_dict(),
                    Message(
                        role=Role.USER,
                        content=(
                            f"## Recent Conversation\n{recent}\n\n"
                            f"## User Action\n{user_input}\n\n"
                            f"## Selected State Target\n{batch.selected_context}\n\n"
                            "只更新这里列出的、已经确定且实际变化的值；没有变化不要调用工具。"
                        ),
                    ).to_dict(),
                ]
                llm_result, call_record = await self._chat_with_stats(
                    messages,
                    schemas,
                    source=batch.source,
                )
                self._append_call_record(result.call_stats, turn_stats, call_record)
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
                            stage=StatusSubAgentStage.REALTIME,
                        ))
                        batch_failed = True
                        break
                    record = await self._execute_tool_call(
                        name,
                        args,
                        track_mutation=True,
                    )
                    record.stage = (
                        StatusSubAgentStage.EVENT_DRIVEN
                        if name == STATUS_TABLE_SET_VALUES_TOOL_NAME
                        and self._arguments_touch_event_key(args, route)
                        else StatusSubAgentStage.REALTIME
                    )
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

    async def update(
        self,
        history: list[Message],
        state_context: str,
        user_input: str,
        max_history_rounds: int = 5,
        turn_stats: TurnStats | None = None,
        player_character: "TurnPlayerCharacterSnapshot | None" = None,
    ) -> StatusSubAgentResult:
        """根据用户输入预更新状态表。

        Parameters
        ----------
        history:
            完整对话历史（内部按 *max_history_rounds* 窗口化）。
        state_context:
            当前状态描述（如 ``[scene]`` 标签块）。
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
            logger.debug(_TAG + " legacy update skipped: reason=reentrancy_guard")
            return StatusSubAgentResult()

        if not self._enabled:
            self._log_verbose("legacy update skipped: reason=disabled")
            return StatusSubAgentResult()
        if not self._schemas:
            self._log_verbose("legacy update skipped: reason=no_tools")
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
                history,
                state_context,
                user_input,
                max_history_rounds,
                player_character=player_character,
            )

            llm_result, call_record = await self._chat_with_stats(
                messages,
                self._schemas,
                source="status_sub_agent",
            )
            self._append_call_record(result.call_stats, turn_stats, call_record)

            tool_calls = self._tool_calls(llm_result)
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
                    if name in STATE_TOOL_NAMES:
                        result.state_prewrites_skipped += 1
                        skipped = StatusSubAgentToolRecord.skipped_due_to_outcome(
                            tool_name=name,
                            arguments=args,
                            state_prewrite=True,
                        )
                        result.records.append(skipped)
                        continue
                    if name != NARRATIVE_OUTCOME_TOOL_NAME:
                        skipped = StatusSubAgentToolRecord.skipped_due_to_outcome(
                            tool_name=name,
                            arguments=args,
                            state_prewrite=False,
                        )
                        result.records.append(skipped)
                        continue
                    if outcome_executed:
                        duplicate = StatusSubAgentToolRecord.skipped_duplicate_outcome(
                            tool_name=name,
                            arguments=args,
                        )
                        result.records.append(duplicate)
                        continue

                    outcome_executed = True
                    record = await self._execute_tool_call(
                        name,
                        args,
                        track_mutation=False,
                        success_status=StatusSubAgentRecordStatus.OUTCOME_STAGED,
                    )
                    record.stage = StatusSubAgentStage.OUTCOME
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

            if result.failed:
                self._restore_failed_update_target(checkpoint, result.records)
                result.updated = any(record.changed for record in result.records)
                logger.warning(
                    _TAG + " state update target failed and was restored"
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
            self._log_verbose(
                "legacy update completed: outcome_requested={} outcome_staged={} "
                "records={} changed_records={} updated={} failed={}",
                result.outcome_requested,
                result.outcome_staged,
                len(result.records),
                sum(record.changed for record in result.records),
                result.updated,
                result.failed,
            )
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
            provider = self._get_provider()
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
    ) -> tuple[list[dict[str, object]], dict[int, dict[str, tuple[str, str]]]]:
        catalog: list[dict[str, object]] = []
        index: dict[int, dict[str, tuple[str, str]]] = {}
        for table in context_tables:
            table_id = int(table.get("id", 0))
            document = table.get("document")
            if table_id <= 0 or not isinstance(document, dict):
                continue
            raw_rows = document.get("rows")
            if not isinstance(raw_rows, list):
                continue
            fields: list[dict[str, object]] = []
            policies: dict[str, tuple[str, str]] = {}
            for raw_row in raw_rows:
                if not isinstance(raw_row, dict):
                    continue
                key = str(raw_row.get("key") or "")
                if not key:
                    continue
                frequency = str(
                    raw_row.get(STATUS_ROW_UPDATE_FREQUENCY_KEY)
                    or STATUS_UPDATE_FREQUENCY_REALTIME
                )
                rule = str(raw_row.get(STATUS_ROW_UPDATE_RULE_KEY) or "")
                policies[key] = (frequency, rule)
                fields.append({
                    "key": key,
                    "value": str(raw_row.get("value") or ""),
                    "frequency": frequency,
                    "event_rule": rule,
                })
            index[table_id] = policies
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
        policies: dict[str, tuple[str, str]],
        *,
        frequency: str,
    ) -> tuple[str, ...]:
        if not isinstance(raw_keys, list):
            return ()
        result: list[str] = []
        seen: set[str] = set()
        for raw_key in raw_keys:
            key = str(raw_key or "")
            policy = policies.get(key)
            if not key or key in seen or policy is None or policy[0] != frequency:
                continue
            if (
                frequency == STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN
                and not policy[1].strip()
            ):
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

    @staticmethod
    def _arguments_touch_event_key(
        args: str,
        route: StatusRouteResult,
    ) -> bool:
        event_keys = {
            (target.table_id, key)
            for target in route.targets
            for key in target.event_keys
        }
        try:
            payload = json.loads(args)
            table_id = int(payload.get("table_id", 0))
            updates = payload.get("updates", [])
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            return False
        return any(
            isinstance(item, dict)
            and (table_id, str(item.get("key", ""))) in event_keys
            for item in updates
        )

    def clear_tools(self) -> None:
        """清空已注册的工具集（重新注册前调用避免重复）。"""
        self._tool_registry = ToolRegistry()
        self._schemas = []
        self._state_tool_set = StateToolSet()

    # ── internal helpers ──────────────────────────────────────────────

    def _build_messages(
        self,
        history: list[Message],
        state_context: str,
        user_input: str,
        max_rounds: int,
        *,
        player_character: "TurnPlayerCharacterSnapshot | None" = None,
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
        system_content = self._build_system_context(
            self.system_prompt,
            player_character=player_character,
        )
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
