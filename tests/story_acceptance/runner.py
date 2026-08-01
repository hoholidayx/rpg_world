"""Reusable temporary-runtime executor for real-LLM Story Pack acceptance."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from commons.scene_time import SceneTime
from llm_client.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_STATUS_SUB_AGENT_BIZ_KEY,
)
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.agent.protocol import StreamEventKind
from rpg_core.agent.turn.runner import AgentReply
from rpg_core.rp_modules.plot_scheduler import (
    PlotScheduleManagementService,
    PlotScheduleSelector,
    PlotScheduleSnapshot,
)
from rpg_core.rp_modules.plot_scheduler.diagnostics import (
    evaluate_event_bindings,
)
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.role import SessionRoleService
from rpg_data import models as data_models
from rpg_mcp.composition import build_runtime_application
from rpg_mcp.runtime import (
    RESOURCE_CHARACTER,
    RESOURCE_OPENING,
    RESOURCE_PLOT_EVENT,
    RESOURCE_PLOT_POOL,
    RESOURCE_STATUS_TABLE,
)
from tests.story_acceptance.loader import LoadedStoryPack
from tests.story_acceptance.errors import is_infrastructure_error
from tests.story_acceptance.models import (
    AcceptanceStatus,
    ContextExpectation,
    PlotExpectation,
    StatusExpectation,
    StoryAcceptanceFlow,
    StoryAcceptanceProfile,
    StoryAcceptanceStep,
)
from tests.story_acceptance.reporting import (
    AcceptanceReport,
    AcceptanceRunWriter,
)
from tests.support.live_agent import (
    RecordedLiveCall,
    main_tool_invocations,
    provider_tool_names,
)


_ENGINE_PLOT_OPEN = "[engine_plot_directive]"
_ENGINE_PLOT_CLOSE = "[/engine_plot_directive]"
_STATUS_SET_TOOL = "status_table_set_values"
_STATUS_EDIT_TOOL = "status_table_edit_fields"
_STATUS_ROUTE_TOOL = "select_status_targets"
_SCENE_TOOLS = frozenset({"scene_time", "scene_attr"})
_WORLD_WRITE_TOOLS = frozenset({
    _STATUS_SET_TOOL,
    _STATUS_EDIT_TOOL,
    *_SCENE_TOOLS,
    "rp_story_outcome",
})
_PLOT_CONTROL_TOOLS = frozenset({"plot_sandbox_read", "plot_event_mark_next"})


@dataclass(frozen=True)
class ImportedStory:
    workspace_id: str
    story_id: int
    id_mapping: dict[str, dict[str, str]]
    validate_result: dict[str, Any]
    preview_result: dict[str, Any]
    apply_result: dict[str, Any]
    repeated_preview_result: dict[str, Any]


@dataclass(frozen=True)
class StepResult:
    flow_id: str
    step_id: str
    session_id: str
    user_input: str
    mode: str
    reply_text: str
    committed_turn_id: int | None
    calls: tuple[RecordedLiveCall, ...]
    actual_tools: tuple[str, ...]
    status_before: dict[str, Any]
    status_after: dict[str, Any]
    plot_before: dict[str, Any]
    plot_after: dict[str, Any]
    persisted_messages: tuple[dict[str, Any], ...]
    backup_messages: tuple[dict[str, Any], ...]
    outcome: dict[str, Any] | None
    runtime_plot_directives: tuple[str, ...]
    stream_events: tuple[dict[str, Any], ...] = ()
    call_start: int = 0
    call_end_exclusive: int = 0

    def log_payload(self) -> dict[str, Any]:
        return {
            "flowId": self.flow_id,
            "stepId": self.step_id,
            "sessionId": self.session_id,
            "mode": self.mode,
            "input": self.user_input,
            "assistant": self.reply_text,
            "committedTurnId": self.committed_turn_id,
            "actualTools": list(self.actual_tools),
            "statusBefore": self.status_before,
            "statusAfter": self.status_after,
            "plotBefore": self.plot_before,
            "plotAfter": self.plot_after,
            "outcome": self.outcome,
            "runtimePlotDirectives": list(self.runtime_plot_directives),
            "persistedMessages": list(self.persisted_messages),
            "backupMessages": list(self.backup_messages),
            "streamEvents": list(self.stream_events),
            "providerCallCount": len(self.calls),
            "providerCallRange": {
                "start": self.call_start,
                "endExclusive": self.call_end_exclusive,
            },
        }


class StoryAcceptanceRunner:
    """Import one Pack and execute isolated sidecar flows through RPGGameAgent."""

    def __init__(
        self,
        *,
        gateway: Any,
        loaded: LoadedStoryPack,
        profile: StoryAcceptanceProfile,
        suite: str,
        calls: list[RecordedLiveCall],
        writer: AcceptanceRunWriter,
    ) -> None:
        self.gateway = gateway
        self.loaded = loaded
        self.profile = profile
        self.suite = str(suite)
        self.calls = calls
        self.writer = writer
        self.report = AcceptanceReport(
            pack_id=loaded.pack.pack_id,
            source_revision=loaded.pack.source_revision,
            source_digest=loaded.pack.source_digest,
            suite=self.suite,
        )
        self.application = build_runtime_application(gateway)
        self.imported: ImportedStory | None = None
        self._session_ids: list[str] = []
        self.semantic_review_items: list[dict[str, Any]] = []
        self._ref_material = _build_ref_material(loaded)
        self._player = next(
            item
            for item in loaded.pack.resources.characters
            if item.stable_id == profile.player_character_ref
        )

    async def run(self) -> AcceptanceReport:
        """Run deterministic import checks and every selected flow."""

        try:
            self.imported = self._import_pack()
            self._check_imported_resources(self.imported)
            self._check_plot_definition_and_distribution(self.imported)
        except Exception as exc:
            self._record_exception(
                check_id="runtime_import",
                category="import",
                exc=exc,
                infrastructure=False,
                summary="Story Pack 正式 validate/preview/apply 链路失败",
            )
            return self.report

        for ordinal, flow in enumerate(self.profile.flows, start=1):
            if not flow.selected_for(self.suite):
                self.report.add(
                    check_id=f"flow.{flow.id}",
                    category="flow",
                    status=AcceptanceStatus.NOT_APPLICABLE,
                    summary=f"{flow.title} 不属于 {self.suite} 套件",
                    flow_id=flow.id,
                )
                continue
            try:
                await self._run_flow(flow, ordinal=ordinal)
            except Exception as exc:
                self._record_exception(
                    check_id=f"flow.{flow.id}.unhandled",
                    category="flow",
                    exc=exc,
                    infrastructure=is_infrastructure_error(exc),
                    summary=f"流程 {flow.title} 发生未处理异常",
                    flow_id=flow.id,
                )
            finally:
                self.writer.flush_calls(self.calls)

        self._check_no_derivation_jobs()
        return self.report

    def _import_pack(self) -> ImportedStory:
        validation = self.application.validate_story_pack(self.loaded.value)
        self._check(
            check_id="import.validate",
            category="import",
            condition=validation.get("valid") is True,
            pass_summary="Story Pack 通过正式 RuntimeApplication 校验",
            fail_summary="Story Pack 未通过正式 RuntimeApplication 校验",
            evidence=(json.dumps(validation, ensure_ascii=False),),
        )
        if validation.get("valid") is not True:
            raise AssertionError("Story Pack validation failed")

        preview = self.application.preview_story_pack(self.loaded.value)
        conflicts = preview.get("plan", {}).get("conflicts", [])
        self._check(
            check_id="import.preview",
            category="import",
            condition=(
                preview.get("status") == "previewed"
                and not conflicts
                and preview.get("requiresConfirmation") is True
            ),
            pass_summary="正式 preview 无冲突且保留独立确认边界",
            fail_summary="正式 preview 存在冲突或确认边界异常",
            evidence=(
                f"operationId={preview.get('operationId')}",
                f"changes={len(preview.get('plan', {}).get('changes', []))}",
                f"conflicts={json.dumps(conflicts, ensure_ascii=False)}",
            ),
        )
        if conflicts:
            raise AssertionError(f"Story Pack preview conflicts: {conflicts!r}")

        applied = self.application.apply_story_pack(str(preview["operationId"]))
        result = dict(applied.get("result") or {})
        mapping = {
            str(kind): {str(key): str(value) for key, value in values.items()}
            for kind, values in dict(result.get("idMapping") or {}).items()
        }
        self._check(
            check_id="import.apply",
            category="import",
            condition=(
                applied.get("status") == "applied"
                and int(result.get("storyId") or 0) > 0
                and bool(mapping)
            ),
            pass_summary="正式 apply 在临时数据库成功并返回稳定 ID 映射",
            fail_summary="正式 apply 未产生完整运行态映射",
            evidence=(
                f"storyId={result.get('storyId')}",
                f"mappingKinds={sorted(mapping)}",
            ),
        )
        repeated_apply = self.application.apply_story_pack(
            str(preview["operationId"])
        )
        repeated_preview = self.application.preview_story_pack(self.loaded.value)
        self._check(
            check_id="import.idempotency",
            category="import",
            condition=(
                repeated_apply.get("status") == "applied"
                and repeated_preview.get("alreadyApplied") is True
                and repeated_preview.get("requiresConfirmation") is False
                and repeated_preview.get("result", {}).get("idMapping")
                == result.get("idMapping")
            ),
            pass_summary="同一 Pack 重复 apply/preview 幂等且稳定映射不变",
            fail_summary="同一 Pack 的重复导入不满足幂等契约",
            evidence=(
                f"alreadyApplied={repeated_preview.get('alreadyApplied')}",
                f"operationId={repeated_preview.get('operationId')}",
            ),
        )
        return ImportedStory(
            workspace_id=self.loaded.pack.target.workspace_id,
            story_id=int(result["storyId"]),
            id_mapping=mapping,
            validate_result=dict(validation),
            preview_result=dict(preview),
            apply_result=dict(applied),
            repeated_preview_result=dict(repeated_preview),
        )

    def _check_imported_resources(self, imported: ImportedStory) -> None:
        pack = self.loaded.pack
        snapshot = self.application.export_story_snapshot(
            imported.workspace_id,
            imported.story_id,
        )["designDocument"]
        resources = snapshot["resources"]
        expected = {
            "openings": len(pack.resources.openings),
            "characters": len(pack.resources.characters),
            "lorebook": len(pack.resources.lorebook),
            "statusTables": len(pack.resources.status_tables),
            "plotPools": len(pack.resources.plot_schedule.pools),
            "plotEvents": len(pack.resources.plot_schedule.events),
            "plotOutlines": len(pack.resources.plot_schedule.outlines),
        }
        actual = {
            "openings": len(resources["openings"]),
            "characters": len(resources["characters"]),
            "lorebook": len(resources["lorebook"]),
            "statusTables": len(resources["statusTables"]),
            "plotPools": len(resources["plotSchedule"]["pools"]),
            "plotEvents": len(resources["plotSchedule"]["events"]),
            "plotOutlines": len(resources["plotSchedule"]["outlines"]),
        }
        self._check(
            check_id="import.resource_counts",
            category="resources",
            condition=actual == expected,
            pass_summary="运行态资源数量与完整 Story Pack 一致",
            fail_summary="运行态资源数量与 Story Pack 不一致",
            evidence=(
                f"expected={json.dumps(expected, ensure_ascii=False, sort_keys=True)}",
                f"actual={json.dumps(actual, ensure_ascii=False, sort_keys=True)}",
            ),
        )

        required_mapping = {
            RESOURCE_CHARACTER: [item.stable_id for item in pack.resources.characters],
            RESOURCE_OPENING: [item.stable_id for item in pack.resources.openings],
            RESOURCE_STATUS_TABLE: [
                item.stable_id for item in pack.resources.status_tables
            ],
            RESOURCE_PLOT_POOL: [
                item.stable_id for item in pack.resources.plot_schedule.pools
            ],
            RESOURCE_PLOT_EVENT: [
                item.stable_id for item in pack.resources.plot_schedule.events
            ],
        }
        missing = {
            kind: sorted(set(refs).difference(imported.id_mapping.get(kind, {})))
            for kind, refs in required_mapping.items()
        }
        missing = {kind: refs for kind, refs in missing.items() if refs}
        self._check(
            check_id="import.stable_bindings",
            category="resources",
            condition=not missing,
            pass_summary="玩家、Opening、状态与 Plot stable ref 均获得运行态绑定",
            fail_summary="部分 stable ref 未获得运行态绑定",
            evidence=(f"missing={json.dumps(missing, ensure_ascii=False)}",),
        )

        archived_visuals = (
            imported.apply_result.get("result", {}).get(
                "archivedVisualSpecifications", []
            )
        )
        self._check(
            check_id="import.visual_archive_only",
            category="resources",
            condition=len(archived_visuals) == len(pack.resources.visual_catalog),
            pass_summary="Visual Catalog 仅归档在导入结果，未进入生成链路",
            fail_summary="Visual Catalog 归档数量异常",
            evidence=(
                f"visualSpecs={len(pack.resources.visual_catalog)}",
                f"archived={len(archived_visuals)}",
            ),
        )

        scene_specs = [
            item
            for item in pack.resources.status_tables
            if item.status_kind == "scene"
        ]
        scene_texts = [
            row.value
            for table in scene_specs
            for row in table.rows
            if row.key == "时间"
        ]
        self._check(
            check_id="resources.scene_time_format",
            category="resources",
            condition=all(not value.startswith("第") for value in scene_texts),
            pass_summary="SceneTime 文案使用无“第”字的统一格式",
            fail_summary="SceneTime 仍包含旧“第”字格式",
            evidence=tuple(scene_texts),
        )
        player_portrayal = [
            detail.stable_id
            for detail in self._player.details
            if "scope:npc_portrayal" in detail.tags
        ]
        if not player_portrayal:
            self.report.add(
                check_id="context.gm_player_portrayal_projection",
                category="context",
                status=AcceptanceStatus.NOT_APPLICABLE,
                summary=(
                    "当前玩家角色没有 scope:npc_portrayal 详情，GM 动态恢复项无可测试数据"
                ),
                evidence=(f"playerCharacterRef={self.profile.player_character_ref}",),
            )

    def _check_plot_definition_and_distribution(
        self,
        imported: ImportedStory,
    ) -> None:
        schedule_service = PlotScheduleManagementService(
            self.gateway.plot_scheduling
        )
        schedule = schedule_service.get_story_schedule(
            imported.workspace_id,
            imported.story_id,
        )
        if schedule is None:
            self._check(
                check_id="plot.definition",
                category="plot",
                condition=not self.loaded.pack.resources.plot_schedule.events,
                pass_summary="Story Pack 未定义 Plot Schedule",
                fail_summary="导入后缺少 Plot Schedule",
            )
            return
        pack_schedule = self.loaded.pack.resources.plot_schedule
        pool_by_ref = {
            item.stable_id: item for item in pack_schedule.pools
        }
        pool_by_id = {item.id: item for item in schedule.pools}
        pool_mismatches: list[str] = []
        for ref, spec in pool_by_ref.items():
            runtime_id = int(imported.id_mapping[RESOURCE_PLOT_POOL][ref])
            value = pool_by_id[runtime_id]
            if (
                value.selection_mode != spec.selection_mode
                or value.selection_weight != spec.selection_weight
                or value.candidate_batch_size != spec.candidate_batch_size
                or value.cooldown_minutes != spec.cooldown_minutes
                or value.enabled != spec.enabled
            ):
                pool_mismatches.append(ref)
        event_by_id = {item.id: item for item in schedule.events}
        event_mismatches: list[str] = []
        for spec in pack_schedule.events:
            runtime_id = int(
                imported.id_mapping[RESOURCE_PLOT_EVENT][spec.stable_id]
            )
            value = event_by_id[runtime_id]
            target_pool_id = int(
                imported.id_mapping[RESOURCE_PLOT_POOL][spec.pool_ref]
            )
            if (
                value.pool_id != target_pool_id
                or value.title != spec.title
                or value.directive != spec.directive
                or value.dispatch_mode != spec.dispatch_mode
                or value.selection_weight != spec.selection_weight
                or value.allow_repeat != spec.allow_repeat
                or value.repeat_cooldown_minutes != spec.repeat_cooldown_minutes
                or _scene_text(value.scheduled_time) != spec.scheduled_time
            ):
                event_mismatches.append(spec.stable_id)
        self._check(
            check_id="plot.definition",
            category="plot",
            condition=not pool_mismatches and not event_mismatches,
            pass_summary="池权重、冷却、batch、事件权重与日期完整导入",
            fail_summary="Plot Schedule 运行态字段与 Pack 不一致",
            evidence=(
                f"poolMismatches={pool_mismatches}",
                f"eventMismatches={event_mismatches}",
            ),
        )

        binding = {item.event_id: item for item in evaluate_event_bindings(schedule)}
        referenced = {
            node.event_ref
            for outline in pack_schedule.outlines
            for node in outline.nodes
        }
        binding_errors = [
            spec.stable_id
            for spec in pack_schedule.events
            if binding[
                int(imported.id_mapping[RESOURCE_PLOT_EVENT][spec.stable_id])
            ].outline_bound
            != (spec.stable_id in referenced)
        ]
        self._check(
            check_id="plot.outline_binding",
            category="plot",
            condition=not binding_errors,
            pass_summary="大纲引用事件与 pool lane 排除诊断一致",
            fail_summary="大纲绑定事件的 pool lane 资格异常",
            evidence=(
                f"boundRefs={sorted(referenced)}",
                f"errors={binding_errors}",
            ),
        )

        scene_time = _initial_scene_time(self.loaded)
        if not schedule.pools or scene_time is None:
            return
        selector = PlotScheduleSelector()
        counts: Counter[int] = Counter()
        primary_counts: dict[int, Counter[int]] = {}
        sample_size = 3000
        for index in range(sample_size):
            selected = selector.select(
                PlotScheduleSnapshot(
                    session_id=f"story_acceptance_seed_{index}",
                    story_id=imported.story_id,
                    enabled=True,
                    story=schedule,
                    overrides=data_models.SessionPlotOverrides(
                        session_id=f"story_acceptance_seed_{index}"
                    ),
                    decisions=(),
                ),
                scene_time=scene_time,
                current_turn_id=2,
                completed_world_turn_ids=(1,),
            )
            pool_item = next(
                (
                    item
                    for item in selected
                    if item.source_kind == data_models.PLOT_SOURCE_POOL
                ),
                None,
            )
            if pool_item is None:
                continue
            primary = getattr(pool_item, "primary", pool_item)
            counts[primary.container_id] += 1
            primary_counts.setdefault(primary.container_id, Counter())[
                primary.event.id
            ] += 1

        eligible_pool_ids = _eligible_pool_ids(schedule, scene_time)
        expected_weight = {
            pool.id: pool.selection_weight
            for pool in schedule.pools
            if pool.id in eligible_pool_ids
        }
        total_weight = sum(expected_weight.values())
        distribution_errors: list[str] = []
        if sum(counts.values()) != sample_size or not total_weight:
            distribution_errors.append(
                f"selected={sum(counts.values())}/{sample_size}, weights={expected_weight}"
            )
        else:
            for pool_id, weight in expected_weight.items():
                observed = counts[pool_id] / sample_size
                expected_probability = weight / total_weight
                if abs(observed - expected_probability) > 0.04:
                    distribution_errors.append(
                        f"pool={pool_id} expected={expected_probability:.4f} observed={observed:.4f}"
                    )
        self._check(
            check_id="plot.stable_pool_distribution",
            category="plot",
            condition=not distribution_errors,
            pass_summary="稳定 seed 下池权重形成可重复的概率分布",
            fail_summary="稳定 seed 池权重分布偏离配置",
            evidence=(
                f"sampleSize={sample_size}",
                f"weights={expected_weight}",
                f"counts={dict(counts)}",
                f"errors={distribution_errors}",
            ),
        )

        replay_id = "story_acceptance_replay"
        replay_snapshot = PlotScheduleSnapshot(
            session_id=replay_id,
            story_id=imported.story_id,
            enabled=True,
            story=schedule,
            overrides=data_models.SessionPlotOverrides(session_id=replay_id),
            decisions=(),
        )
        first = selector.select(
            replay_snapshot,
            scene_time=scene_time,
            current_turn_id=2,
            completed_world_turn_ids=(1,),
        )
        second = selector.select(
            replay_snapshot,
            scene_time=scene_time,
            current_turn_id=2,
            completed_world_turn_ids=(1,),
        )
        self._check(
            check_id="plot.stable_seed_replay",
            category="plot",
            condition=first == second,
            pass_summary="相同 Session/turn seed 的候选与 batch 完全一致",
            fail_summary="相同 seed 的 Plot 选择不可重放",
            evidence=(
                "selection="
                + json.dumps(
                    _selection_identity(first),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )

        weight_errors: list[str] = []
        events_by_pool: dict[int, list[Any]] = {}
        for event in schedule.events:
            if event.id in {
                item.event_id for item in binding.values() if item.outline_bound
            }:
                continue
            if event.scheduled_time is not None and event.scheduled_time > scene_time:
                continue
            events_by_pool.setdefault(event.pool_id, []).append(event)
        for pool_id, events in events_by_pool.items():
            pool_total = sum(primary_counts.get(pool_id, {}).values())
            if pool_total < 80 or not events:
                continue
            total_event_weight = sum(item.selection_weight for item in events)
            for event in events:
                observed = primary_counts[pool_id][event.id] / pool_total
                expected_probability = event.selection_weight / total_event_weight
                if abs(observed - expected_probability) > 0.10:
                    weight_errors.append(
                        f"event={event.id} expected={expected_probability:.4f} observed={observed:.4f}"
                    )
        self._check(
            check_id="plot.stable_event_recall_distribution",
            category="plot",
            condition=not weight_errors,
            pass_summary="池内主候选召回遵循事件权重的稳定分布",
            fail_summary="池内事件召回分布偏离事件权重",
            evidence=(
                f"primaryCounts={_jsonable(primary_counts)}",
                f"errors={weight_errors}",
            ),
        )

        calendar_errors = _calendar_gate_errors(
            selector=selector,
            schedule=schedule,
            story_id=imported.story_id,
        )
        self._check(
            check_id="plot.forced_calendar_gates",
            category="plot",
            condition=not calendar_errors,
            pass_summary="forced 日历事件在日期前不可选、到期后进入候选",
            fail_summary="forced 日历事件日期门禁异常",
            evidence=(f"errors={calendar_errors}",),
        )

    async def _run_flow(self, flow: StoryAcceptanceFlow, *, ordinal: int) -> None:
        imported = self._require_imported()
        session_id = flow.session_id or _session_id(flow.id, ordinal)
        catalog = SessionCatalogService(self.gateway.sessions)
        session = catalog.create_session(
            imported.workspace_id,
            imported.story_id,
            session_id=session_id,
            title=f"Story acceptance · {flow.title}"[:120],
        )
        if session is None:
            raise RuntimeError(f"failed to create acceptance session {session_id}")
        self._session_ids.append(session.id)
        player_id = int(
            imported.id_mapping[RESOURCE_CHARACTER][
                self.profile.player_character_ref
            ]
        )
        opening_id = (
            int(imported.id_mapping[RESOURCE_OPENING][self.profile.opening_ref])
            if self.profile.opening_ref is not None
            else None
        )
        bind = SessionRoleService(self.gateway.sessions).bind_player_character(
            session.id,
            player_id,
            story_opening_id=opening_id,
        )
        self._check(
            check_id=f"flow.{flow.id}.role_opening",
            category="session",
            condition=(
                bind.state.status.value == "bound"
                and bind.state.player is not None
                and bind.state.player.character_id == player_id
                and bind.story_opening_id == opening_id
            ),
            pass_summary="独立 Session 已按 stable ref 绑定玩家角色与 Opening",
            fail_summary="玩家角色或 Opening stable binding 失败",
            evidence=(
                f"sessionId={session.id}",
                f"playerCharacterId={player_id}",
                f"openingId={opening_id}",
                f"firstMessageChars={len(bind.first_message)}",
            ),
            flow_id=flow.id,
        )

        agent = RPGGameAgent(session_id=session.id)
        fixed_layers: list[tuple[str, str]] = []
        try:
            await agent.initialize()
            for step in flow.steps:
                call_offset = len(self.calls)
                try:
                    result = await self._execute_step(
                        agent=agent,
                        flow=flow,
                        step=step,
                        call_offset=call_offset,
                    )
                except Exception as exc:
                    self._record_exception(
                        check_id=f"flow.{flow.id}.{step.id}.execution",
                        category="turn",
                        exc=exc,
                        infrastructure=is_infrastructure_error(exc),
                        summary="真实 Agent turn 执行失败",
                        flow_id=flow.id,
                        step_id=step.id,
                    )
                    self.writer.append_step({
                        "flowId": flow.id,
                        "stepId": step.id,
                        "sessionId": session.id,
                        "mode": step.mode,
                        "input": step.input,
                        "error": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        },
                    })
                    self.writer.flush_calls(self.calls)
                    break
                self.writer.append_step(result.log_payload())
                self.writer.flush_calls(self.calls)
                self._check_step(flow, step, result)
                initial_main = _first_main_call(result.calls)
                if initial_main is not None and initial_main.messages:
                    fixed_layers.append(
                        (step.id, str(initial_main.messages[0].get("content", "")))
                    )
                if step.semantic_rubric:
                    self._queue_semantic_review(flow, step, result)
        finally:
            await agent.close()

        if flow.require_fixed_layer_stability and len(fixed_layers) > 1:
            baseline = fixed_layers[0][1]
            different = [step_id for step_id, value in fixed_layers if value != baseline]
            self._check(
                check_id=f"flow.{flow.id}.fixed_layer_stability",
                category="context",
                condition=not different,
                pass_summary="Neutral/IC/OOC/GM 共用的 Fixed Layer 字节稳定",
                fail_summary="不同 turn 模式改变了 Fixed Layer",
                evidence=(
                    f"baselineStep={fixed_layers[0][0]}",
                    f"differentSteps={different}",
                    f"fixedLayerChars={len(baseline)}",
                ),
                flow_id=flow.id,
            )

    async def _execute_step(
        self,
        *,
        agent: RPGGameAgent,
        flow: StoryAcceptanceFlow,
        step: StoryAcceptanceStep,
        call_offset: int,
    ) -> StepResult:
        session_id = agent.session_id
        status_before = _status_snapshot(self.gateway, session_id)
        plot_before = _plot_snapshot(self.gateway, session_id)
        schedule_before = self._schedule_snapshot(session_id)
        stream_events: tuple[dict[str, Any], ...] = ()
        if step.stream:
            events = []
            async with asyncio.timeout(step.timeout_seconds):
                async for event in agent.send_stream(step.input, mode=step.mode):
                    events.append(event)
            done = next(
                (item for item in reversed(events) if item.kind is StreamEventKind.DONE),
                None,
            )
            if done is None:
                error = next(
                    (
                        item
                        for item in reversed(events)
                        if item.kind is StreamEventKind.ERROR
                    ),
                    None,
                )
                raise RuntimeError(
                    f"stream ended without DONE: {getattr(error, 'content', '')}"
                )
            reply = AgentReply(
                text=done.content,
                tool_records=agent.last_tool_records,
                status_sub_agent_records=None,
                stats=done.stats,
                committed_turn_id=done.committed_turn_id,
            )
            stream_events = tuple(event.to_dict() for event in events)
        else:
            reply = await asyncio.wait_for(
                agent.send(step.input, mode=step.mode),
                timeout=step.timeout_seconds,
            )

        step_calls = tuple(self.calls[call_offset:])
        status_after = _status_snapshot(self.gateway, session_id)
        plot_after = _plot_snapshot(self.gateway, session_id)
        schedule_after = self._schedule_snapshot(session_id)
        persisted = tuple(
            _message_dict(item)
            for item in self.gateway.messages.list(session_id)
        )
        backup = tuple(
            _message_dict(item)
            for item in self.gateway.backup.messages.list(session_id)
        )
        outcome = (
            _jsonable(
                self.gateway.narrative_outcomes.get_for_turn(
                    session_id,
                    reply.committed_turn_id,
                )
            )
            if reply.committed_turn_id is not None
            else None
        )
        actual_tools = _actual_tool_names(reply, step_calls, stream_events)
        runtime_directives = _runtime_plot_directives(step_calls)
        result = StepResult(
            flow_id=flow.id,
            step_id=step.id,
            session_id=session_id,
            user_input=step.input,
            mode=step.mode,
            reply_text=reply.text,
            committed_turn_id=reply.committed_turn_id,
            calls=step_calls,
            actual_tools=actual_tools,
            status_before=status_before,
            status_after=status_after,
            plot_before={**plot_before, "schedule": schedule_before},
            plot_after={**plot_after, "schedule": schedule_after},
            persisted_messages=persisted,
            backup_messages=backup,
            outcome=outcome,
            runtime_plot_directives=runtime_directives,
            stream_events=stream_events,
            call_start=call_offset,
            call_end_exclusive=len(self.calls),
        )
        return result

    def _schedule_snapshot(self, session_id: str) -> dict[str, Any]:
        imported = self._require_imported()
        event_ref_by_id = {
            int(runtime_id): ref
            for ref, runtime_id in imported.id_mapping[
                RESOURCE_PLOT_EVENT
            ].items()
        }
        pool_ref_by_id = {
            int(runtime_id): ref
            for ref, runtime_id in imported.id_mapping[
                RESOURCE_PLOT_POOL
            ].items()
        }
        schedule, _overrides = PlotScheduleManagementService(
            self.gateway.plot_scheduling
        ).get_session_schedule(session_id)
        bindings = {
            item.event_id: item for item in evaluate_event_bindings(schedule)
        }
        return {
            "pools": {
                pool_ref_by_id[item.id]: _jsonable(item)
                for item in schedule.pools
            },
            "events": {
                event_ref_by_id[item.id]: {
                    **_jsonable(item),
                    "outlineBound": bindings[item.id].outline_bound,
                }
                for item in schedule.events
            },
        }

    def _check_step(
        self,
        flow: StoryAcceptanceFlow,
        step: StoryAcceptanceStep,
        result: StepResult,
    ) -> None:
        prefix = f"flow.{flow.id}.{step.id}"
        self._check(
            check_id=f"{prefix}.commit",
            category="persistence",
            condition=result.committed_turn_id is not None,
            pass_summary="真实 turn 已完成事务提交",
            fail_summary="真实 turn 未产生 committed_turn_id",
            evidence=(
                f"committedTurnId={result.committed_turn_id}",
                f"providerCalls={len(result.calls)}",
            ),
            flow_id=flow.id,
            step_id=step.id,
        )
        committed_messages = [
            item
            for item in result.persisted_messages
            if item["turn_id"] == result.committed_turn_id
            and item["role"] in {"user", "assistant"}
        ]
        self._check(
            check_id=f"{prefix}.mode_persistence",
            category="mode",
            condition=(
                len(committed_messages) == 2
                and {item["role"] for item in committed_messages}
                == {"user", "assistant"}
                and all(item["mode"] == step.mode for item in committed_messages)
            ),
            pass_summary="本轮 user/assistant 消息均持久化正确的 message_mode 标记",
            fail_summary="本轮消息的 message_mode 持久化标记异常",
            evidence=(
                "messages="
                + json.dumps(
                    [
                        {"role": item["role"], "mode": item["mode"]}
                        for item in committed_messages
                    ],
                    ensure_ascii=False,
                ),
            ),
            flow_id=flow.id,
            step_id=step.id,
        )

        actual = set(result.actual_tools)
        required_missing = sorted(set(step.required_tools).difference(actual))
        forbidden_called = sorted(set(step.forbidden_tools).intersection(actual))
        self._check(
            check_id=f"{prefix}.tool_calls",
            category="tools",
            condition=not required_missing and not forbidden_called,
            pass_summary="模型按自然意图正确选择实际工具",
            fail_summary="实际工具调用不符合 sidecar 声明",
            evidence=(
                f"actual={sorted(actual)}",
                f"missing={required_missing}",
                f"forbidden={forbidden_called}",
            ),
            flow_id=flow.id,
            step_id=step.id,
        )

        exposed = set().union(*(provider_tool_names(call) for call in result.calls))
        missing_exposed = sorted(
            set(step.required_exposed_tools).difference(exposed)
        )
        forbidden_exposed = sorted(
            set(step.forbidden_exposed_tools).intersection(exposed)
        )
        self._check(
            check_id=f"{prefix}.tool_exposure",
            category="tools",
            condition=not missing_exposed and not forbidden_exposed,
            pass_summary="Provider 实际收到的工具 schema 符合模式门禁",
            fail_summary="Provider 工具 schema 暴露不符合模式门禁",
            evidence=(
                f"exposed={sorted(exposed)}",
                f"missing={missing_exposed}",
                f"forbidden={forbidden_exposed}",
            ),
            flow_id=flow.id,
            step_id=step.id,
        )

        if step.mode == "ooc":
            ooc_world_unchanged = (
                result.status_before == result.status_after
                and result.plot_before.get("opportunity")
                == result.plot_after.get("opportunity")
                and result.plot_before.get("decisions")
                == result.plot_after.get("decisions")
            )
            self._check(
                check_id=f"{prefix}.ooc_read_only_world",
                category="mode",
                condition=ooc_world_unchanged,
                pass_summary="OOC 未改变 Scene、普通状态、机会或决策账本",
                fail_summary="OOC 意外推进或改写了世界事实",
                evidence=(
                    f"statusChanged={result.status_before != result.status_after}",
                    f"opportunityBefore={result.plot_before.get('opportunity')}",
                    f"opportunityAfter={result.plot_after.get('opportunity')}",
                ),
                flow_id=flow.id,
                step_id=step.id,
            )
            self._check(
                check_id=f"{prefix}.ooc_no_world_tools",
                category="mode",
                condition=not actual.intersection(_WORLD_WRITE_TOOLS),
                pass_summary="OOC 未调用状态写入或 Outcome 工具",
                fail_summary="OOC 调用了世界写入工具",
                evidence=(f"actual={sorted(actual)}",),
                flow_id=flow.id,
                step_id=step.id,
            )
            self._check(
                check_id=f"{prefix}.ooc_no_world_tool_exposure",
                category="mode",
                condition=not exposed.intersection(_WORLD_WRITE_TOOLS),
                pass_summary="OOC Provider 未收到状态写入或 Outcome schema",
                fail_summary="OOC Provider 错误暴露了世界写入 schema",
                evidence=(f"exposed={sorted(exposed)}",),
                flow_id=flow.id,
                step_id=step.id,
            )
        elif step.mode in {"ic", "neutral"}:
            self._check(
                check_id=f"{prefix}.no_plot_control",
                category="mode",
                condition=not exposed.intersection(_PLOT_CONTROL_TOOLS),
                pass_summary="IC/neutral 未注册 Plot 沙盘控制工具",
                fail_summary="IC/neutral 错误暴露 Plot 沙盘控制工具",
                evidence=(f"exposed={sorted(exposed)}",),
                flow_id=flow.id,
                step_id=step.id,
            )

        self._check_context(flow, step, result)
        self._check_status_expectations(flow, step, result)
        self._check_status_route_allowlist(flow, step, result)
        plot_checks = [
            *((step.plot,) if step.plot is not None else ()),
            *step.additional_plot_checks,
        ]
        for plot_index, plot_expectation in enumerate(plot_checks):
            self._check_plot_expectation(
                flow,
                step,
                result,
                expectation=plot_expectation,
                check_index=plot_index,
            )
        self._check_outcome_expectation(flow, step, result)
        self._check_persistence(flow, step, result)

        if step.mode != "ooc":
            tagged = (
                "<rp-narration>" in result.reply_text
                or "<rp-character" in result.reply_text
            )
            self._check(
                check_id=f"{prefix}.xml_output",
                category="response",
                condition=tagged,
                pass_summary="世界 turn 正文使用 RP XML 标签",
                fail_summary="世界 turn 正文缺少 RP XML 标签",
                evidence=(result.reply_text[:500],),
                flow_id=flow.id,
                step_id=step.id,
            )

    def _check_context(
        self,
        flow: StoryAcceptanceFlow,
        step: StoryAcceptanceStep,
        result: StepResult,
    ) -> None:
        expectation = step.context
        main_call = _first_main_call(result.calls)
        if expectation is None and main_call is None:
            return
        prefix = f"flow.{flow.id}.{step.id}.context"
        self._check(
            check_id=f"{prefix}.main_request",
            category="context",
            condition=main_call is not None,
            pass_summary="捕获到真实 agent.main Provider 请求",
            fail_summary="未捕获真实 agent.main Provider 请求",
            flow_id=flow.id,
            step_id=step.id,
        )
        if main_call is None:
            return
        all_main_calls = [
            call for call in result.calls if call.biz_key == AGENT_MAIN_BIZ_KEY
        ]
        all_text = "\n".join(
            str(message.get("content", ""))
            for call in all_main_calls
            for message in call.messages
        )
        fixed = str(main_call.messages[0].get("content", ""))
        system_text = "\n".join(
            str(message.get("content", ""))
            for message in main_call.messages
            if message.get("role") == "system"
        )
        user_messages = [
            str(message.get("content", ""))
            for message in main_call.messages
            if message.get("role") == "user"
        ]
        current_user = user_messages[-1] if user_messages else ""
        normal_names = [
            table.name
            for table in self.loaded.pack.resources.status_tables
            if table.status_kind == "normal"
        ]
        scene = next(
            (
                table
                for table in self.loaded.pack.resources.status_tables
                if table.status_kind == "scene"
            ),
            None,
        )
        status_layer = next(
            (
                str(message.get("content", ""))
                for message in main_call.messages
                if message.get("role") == "system"
                and "以下是本轮回复前的普通状态表快照" in str(
                    message.get("content", "")
                )
            ),
            "",
        )
        layering_ok = True
        if scene is not None:
            layering_ok = (
                "[scene]" in current_user
                and "[/scene]" in current_user
                and current_user.index("[scene]") < current_user.rfind(step.input)
                and scene.name not in status_layer
                and all(name in status_layer for name in normal_names)
                and all(name not in current_user for name in normal_names)
            )
        self._check(
            check_id=f"{prefix}.scene_status_layers",
            category="context",
            condition=layering_ok,
            pass_summary="Scene 位于高优先级 user prefix，普通状态仅在 system 层",
            fail_summary="Scene 与普通状态表的 Context 分层异常",
            evidence=(
                f"scene={getattr(scene, 'name', None)}",
                f"normalTables={normal_names}",
                f"currentUserPrefix={current_user[:600]}",
            ),
            flow_id=flow.id,
            step_id=step.id,
        )
        if expectation is None:
            return

        failures: list[str] = []
        if expectation.require_story_prompt and (
            self.loaded.pack.story.story_prompt not in system_text
        ):
            failures.append("storyPrompt missing from system context")
        if expectation.require_opening:
            opening = next(
                (
                    item
                    for item in self.loaded.pack.resources.openings
                    if item.stable_id == self.profile.opening_ref
                ),
                None,
            )
            if opening is None or opening.message not in all_text:
                failures.append("Opening missing from Provider messages")
        for ref in expectation.required_refs:
            if not _material_present(all_text, self._ref_material[ref]):
                failures.append(f"required ref absent: {ref}")
        for ref in expectation.forbidden_refs:
            if _material_present(all_text, self._ref_material[ref]):
                failures.append(f"forbidden ref present: {ref}")

        portrayal_texts = [
            item.content
            for item in self._player.details
            if "scope:npc_portrayal" in item.tags
        ]
        if expectation.player_portrayal_excluded and any(
            value and value in fixed for value in portrayal_texts
        ):
            failures.append("player npc_portrayal detail leaked into Fixed Layer")
        if expectation.player_portrayal_included and not all(
            value in system_text for value in portrayal_texts
        ):
            failures.append("GM message_mode lacks player portrayal details")
        self._check(
            check_id=f"{prefix}.expectations",
            category="context",
            condition=not failures,
            pass_summary="Story Prompt、Opening、角色/Lorebook 与玩家卡投影符合声明",
            fail_summary="Provider 真实 Context 不符合 sidecar 声明",
            evidence=tuple(failures) or (f"messages={len(main_call.messages)}",),
            flow_id=flow.id,
            step_id=step.id,
        )

    def _check_status_expectations(
        self,
        flow: StoryAcceptanceFlow,
        step: StoryAcceptanceStep,
        result: StepResult,
    ) -> None:
        for index, expectation in enumerate(step.status):
            spec = next(
                table
                for table in self.loaded.pack.resources.status_tables
                if table.stable_id == expectation.table_ref
            )
            before = result.status_before.get(spec.name)
            after = result.status_after.get(spec.name)
            ok, evidence = _evaluate_status_expectation(
                expectation,
                before=before,
                after=after,
            )
            self._check(
                check_id=(
                    f"flow.{flow.id}.{step.id}.status.{index}."
                    f"{expectation.operation}"
                ),
                category="status",
                condition=ok,
                pass_summary=(
                    f"状态表“{spec.name}”满足 {expectation.operation} 预期"
                ),
                fail_summary=(
                    f"状态表“{spec.name}”未满足 {expectation.operation} 预期"
                ),
                evidence=evidence,
                flow_id=flow.id,
                step_id=step.id,
            )

    def _check_status_route_allowlist(
        self,
        flow: StoryAcceptanceFlow,
        step: StoryAcceptanceStep,
        result: StepResult,
    ) -> None:
        route_calls = [
            call
            for call in result.calls
            if call.biz_key == AGENT_STATUS_SUB_AGENT_BIZ_KEY
            and _STATUS_ROUTE_TOOL in provider_tool_names(call)
        ]
        if not route_calls:
            return
        failures: list[str] = []
        route_targets: dict[int, dict[str, Any]] = {}
        for call in route_calls:
            for name, arguments in _response_tool_calls(call):
                if name != _STATUS_ROUTE_TOOL:
                    continue
                for target in arguments.get("tables", []):
                    if isinstance(target, dict):
                        route_targets[int(target.get("table_id") or 0)] = target
        session_table_ids = {
            int(value["id"]) for value in result.status_before.values()
        }
        for call in result.calls:
            if call.biz_key != AGENT_STATUS_SUB_AGENT_BIZ_KEY:
                continue
            exposed = provider_tool_names(call)
            update_tools = exposed.intersection({_STATUS_SET_TOOL, _STATUS_EDIT_TOOL})
            if not update_tools:
                continue
            for name, arguments in _response_tool_calls(call):
                if name not in update_tools:
                    continue
                table_id = int(arguments.get("table_id") or 0)
                target = route_targets.get(table_id)
                if table_id not in session_table_ids:
                    failures.append(f"tool {name} targeted foreign table {table_id}")
                    continue
                if target is None:
                    failures.append(f"tool {name} targeted unrouted table {table_id}")
                    continue
                allowed = set(target.get("keys") or [])
                structure = bool(target.get("structure", False))
                if name == _STATUS_EDIT_TOOL and not structure:
                    failures.append(
                        f"structure tool exposed/called without structure route: {table_id}"
                    )
                if name == _STATUS_SET_TOOL:
                    keys = {
                        str(item.get("key") or "")
                        for item in arguments.get("updates", [])
                        if isinstance(item, dict)
                    }
                    if not keys or not keys.issubset(allowed):
                        failures.append(
                            f"value keys {sorted(keys)} exceed route {sorted(allowed)}"
                        )
                if name == _STATUS_EDIT_TOOL:
                    source_keys = set(arguments.get("deletes") or [])
                    source_keys.update(
                        str(item.get("key") or "")
                        for item in arguments.get("renames", [])
                        if isinstance(item, dict)
                    )
                    if not source_keys.issubset(allowed):
                        failures.append(
                            f"structure source keys {sorted(source_keys)} exceed route {sorted(allowed)}"
                        )
        self._check(
            check_id=f"flow.{flow.id}.{step.id}.status.route_allowlist",
            category="status",
            condition=not failures,
            pass_summary="StatusSubAgent 路由与逐目标 table/key/structure allowlist 一致",
            fail_summary="StatusSubAgent 实际目标越过路由 allowlist",
            evidence=tuple(failures) or (
                f"targets={json.dumps(route_targets, ensure_ascii=False, sort_keys=True)}",
            ),
            flow_id=flow.id,
            step_id=step.id,
        )

    def _check_plot_expectation(
        self,
        flow: StoryAcceptanceFlow,
        step: StoryAcceptanceStep,
        result: StepResult,
        *,
        expectation: PlotExpectation,
        check_index: int,
    ) -> None:
        failures: list[str] = []
        pending = result.plot_after.get("pending")
        if expectation.pending is not None and bool(pending) != expectation.pending:
            failures.append(
                f"pending expected={expectation.pending}, actual={bool(pending)}"
            )
        imported = self._require_imported()
        expected_pending_event_id = (
            int(imported.id_mapping[RESOURCE_PLOT_EVENT][expectation.pending_event_ref])
            if expectation.pending_event_ref
            else None
        )
        if expected_pending_event_id is not None and (
            not pending
            or int(pending.get("source_event_id") or 0)
            != expected_pending_event_id
        ):
            failures.append(
                f"pending event expected={expected_pending_event_id}, actual={pending}"
            )
        checks_pending_snapshot = (
            expectation.pending is True
            or expectation.pending_event_ref is not None
        )
        if checks_pending_snapshot and expectation.snapshot_title is not None and (
            not pending or pending.get("event_title") != expectation.snapshot_title
        ):
            failures.append("pending title snapshot mismatch")
        if (
            checks_pending_snapshot
            and expectation.snapshot_directive is not None
            and (not pending or pending.get("directive") != expectation.snapshot_directive)
        ):
            failures.append("pending directive snapshot mismatch")
        if expectation.scene_opportunity is not None and (
            bool(result.plot_after.get("opportunity"))
            != expectation.scene_opportunity
        ):
            failures.append(
                "scene opportunity expected="
                f"{expectation.scene_opportunity}, actual="
                f"{bool(result.plot_after.get('opportunity'))}"
            )

        before_ids = {
            int(item["id"]) for item in result.plot_before.get("decisions", [])
        }
        delta = [
            item
            for item in result.plot_after.get("decisions", [])
            if int(item["id"]) not in before_ids
        ]
        decision = None
        if expectation.decision_event_ref:
            event_id = int(
                imported.id_mapping[RESOURCE_PLOT_EVENT][
                    expectation.decision_event_ref
                ]
            )
            decision = next(
                (item for item in delta if int(item["event_id"]) == event_id),
                None,
            )
            if decision is None:
                failures.append(
                    f"no new decision for {expectation.decision_event_ref}/{event_id}"
                )
        elif expectation.decision_pool_ref:
            pool_id = int(
                imported.id_mapping[RESOURCE_PLOT_POOL][
                    expectation.decision_pool_ref
                ]
            )
            decision = next(
                (item for item in delta if int(item["container_id"]) == pool_id),
                None,
            )
            if decision is None:
                failures.append(
                    f"no new pool decision for {expectation.decision_pool_ref}/{pool_id}"
                )
        elif delta:
            decision = delta[-1]
        if expectation.forbidden_decision_pool_ref:
            forbidden_pool_id = int(
                imported.id_mapping[RESOURCE_PLOT_POOL][
                    expectation.forbidden_decision_pool_ref
                ]
            )
            if any(
                int(item["container_id"]) == forbidden_pool_id
                and item.get("source_kind") == data_models.PLOT_SOURCE_POOL
                for item in delta
            ):
                failures.append(
                    "unexpected new pool decision for "
                    f"{expectation.forbidden_decision_pool_ref}/{forbidden_pool_id}"
                )
        for field_name, expected_value, data_key in (
            ("sourceKind", expectation.source_kind, "source_kind"),
            ("selectionOrigin", expectation.selection_origin, "selection_origin"),
            ("decisionStatus", expectation.decision_status, "decision_status"),
        ):
            if expected_value is not None and (
                decision is None or decision.get(data_key) != expected_value
            ):
                failures.append(
                    f"{field_name} expected={expected_value}, actual="
                    f"{None if decision is None else decision.get(data_key)}"
                )
        snapshot_source = (
            decision.get("event_snapshot", {}) if decision is not None else {}
        )
        if expectation.snapshot_title is not None and decision is not None and (
            snapshot_source.get("eventTitle") != expectation.snapshot_title
        ):
            failures.append("decision title snapshot mismatch")
        if expectation.snapshot_directive is not None and decision is not None and (
            snapshot_source.get("directive") != expectation.snapshot_directive
        ):
            failures.append("decision directive snapshot mismatch")
        selection_context = (
            snapshot_source.get("selectionContext", {})
            if isinstance(snapshot_source, dict)
            else {}
        )
        for label, expected_value, key in (
            ("selection method", expectation.selection_method, "method"),
            (
                "configured batch size",
                expectation.configured_batch_size,
                "configuredBatchSize",
            ),
            (
                "actual batch size",
                expectation.actual_batch_size,
                "actualBatchSize",
            ),
        ):
            if expected_value is not None and selection_context.get(key) != expected_value:
                failures.append(
                    f"{label} expected={expected_value}, actual={selection_context.get(key)}"
                )
        if expectation.configured_batch_size is not None and selection_context:
            candidate_ids = {
                int(item.get("eventId") or 0)
                for item in selection_context.get("candidates", [])
                if isinstance(item, dict)
            }
            runtime_events = result.plot_after["schedule"]["events"]
            candidate_titles = {
                str(item.get("title") or "")
                for item in runtime_events.values()
                if int(item.get("id") or 0) in candidate_ids
            }
            rerank_calls = [
                call
                for call in result.calls
                if "plot_schedule_decision" in provider_tool_names(call)
                and candidate_titles
                and all(
                    title
                    in "\n".join(
                        str(message.get("content", ""))
                        for message in call.messages
                    )
                    for title in candidate_titles
                )
            ]
            if len(rerank_calls) != 1:
                failures.append(
                    f"expected exactly one real batch rerank call, actual={len(rerank_calls)}"
                )
        unchanged_event_ref = (
            expectation.decision_event_ref or expectation.pending_event_ref
        )
        if expectation.original_event_unchanged and unchanged_event_ref:
            event_ref = unchanged_event_ref
            before_event = result.plot_before["schedule"]["events"].get(event_ref)
            after_event = result.plot_after["schedule"]["events"].get(event_ref)
            if before_event != after_event:
                failures.append("source event changed after temporary snapshot")
        if expectation.directive_runtime_only:
            directive = (
                expectation.snapshot_directive
                or snapshot_source.get("directive")
                or ""
            )
            main = _first_main_call(result.calls)
            runtime_text = ""
            if main is not None:
                users = [
                    str(item.get("content", ""))
                    for item in main.messages
                    if item.get("role") == "user"
                ]
                runtime_text = users[-1] if users else ""
            persisted_text = "\n".join(
                item["content"]
                for item in (*result.persisted_messages, *result.backup_messages)
            )
            system_text = "\n".join(
                str(item.get("content", ""))
                for item in (main.messages if main else [])
                if item.get("role") == "system"
            )
            if (
                _ENGINE_PLOT_OPEN not in runtime_text
                or _ENGINE_PLOT_CLOSE not in runtime_text
                or (directive and directive not in runtime_text)
                or _ENGINE_PLOT_OPEN in persisted_text
                or (directive and directive in persisted_text)
                or (directive and directive in system_text)
                or _ENGINE_PLOT_OPEN in result.reply_text
            ):
                failures.append("Plot directive was not confined to runtime user suffix")

        if expectation.pool_ref:
            pool_id = int(
                imported.id_mapping[RESOURCE_PLOT_POOL][expectation.pool_ref]
            )
            diagnostic = next(
                (
                    item
                    for item in _pool_cooldowns(self.gateway, result.session_id)
                    if item["pool_id"] == pool_id
                ),
                None,
            )
            if diagnostic is None:
                failures.append(f"missing cooldown diagnostic for pool {pool_id}")
            else:
                if (
                    expectation.cooldown_remaining_minutes is not None
                    and diagnostic["remaining_minutes"]
                    != expectation.cooldown_remaining_minutes
                ):
                    failures.append(
                        "cooldown remaining expected="
                        f"{expectation.cooldown_remaining_minutes}, actual="
                        f"{diagnostic['remaining_minutes']}"
                    )
                if (
                    expectation.cooldown_reason_code is not None
                    and diagnostic["reason_code"]
                    != expectation.cooldown_reason_code
                ):
                    failures.append(
                        "cooldown reason expected="
                        f"{expectation.cooldown_reason_code}, actual="
                        f"{diagnostic['reason_code']}"
                    )
        self._check(
            check_id=f"flow.{flow.id}.{step.id}.plot.{check_index}",
            category="plot",
            condition=not failures,
            pass_summary="pending、决策、快照、机会与冷却符合 Plot 声明",
            fail_summary="Plot 运行态不符合 sidecar 声明",
            evidence=tuple(failures) or (
                f"decisionDelta={json.dumps(delta, ensure_ascii=False, default=str)}",
            ),
            flow_id=flow.id,
            step_id=step.id,
        )

    def _check_outcome_expectation(
        self,
        flow: StoryAcceptanceFlow,
        step: StoryAcceptanceStep,
        result: StepResult,
    ) -> None:
        expectation = step.outcome
        if expectation is None:
            return
        failures: list[str] = []
        if expectation.required != bool(result.outcome):
            failures.append(
                f"required={expectation.required}, actual={bool(result.outcome)}"
            )
        if expectation.code is not None and result.outcome:
            actual_code = (
                result.outcome.get("outcome_code")
                or result.outcome.get("outcomeCode")
                or result.outcome.get("code")
            )
            if actual_code != expectation.code:
                failures.append(
                    f"code expected={expectation.code}, actual={actual_code}"
                )
        ledger_count = 0
        if result.committed_turn_id is not None:
            ledger_count = len(
                self.gateway.narrative_outcomes.list_for_turns(
                    result.session_id,
                    [result.committed_turn_id],
                )
            )
        if expectation.one_per_turn and ledger_count > 1:
            failures.append(
                f"onePerTurn expected at most one ledger row, actual={ledger_count}"
            )
        if expectation.required and result.committed_turn_id is not None and (
            ledger_count != 1
        ):
            failures.append(
                f"required outcome ledger rows expected=1, actual={ledger_count}"
            )
        self._check(
            check_id=f"flow.{flow.id}.{step.id}.outcome",
            category="outcome",
            condition=not failures,
            pass_summary="Narrative Outcome 账本与单轮契约符合声明",
            fail_summary="Narrative Outcome 未按声明落账",
            evidence=tuple(failures) or (
                f"ledgerRows={ledger_count}",
                json.dumps(result.outcome, ensure_ascii=False, default=str),
            ),
            flow_id=flow.id,
            step_id=step.id,
        )

    def _check_persistence(
        self,
        flow: StoryAcceptanceFlow,
        step: StoryAcceptanceStep,
        result: StepResult,
    ) -> None:
        expectation = step.persistence
        if expectation is None:
            return
        failures: list[str] = []
        if expectation.committed != (result.committed_turn_id is not None):
            failures.append("commit expectation mismatch")
        turn_users = [
            item
            for item in result.persisted_messages
            if item["turn_id"] == result.committed_turn_id and item["role"] == "user"
        ]
        backup_users = [
            item
            for item in result.backup_messages
            if item["turn_id"] == result.committed_turn_id and item["role"] == "user"
        ]
        if expectation.original_input_only and (
            len(turn_users) != 1
            or len(backup_users) != 1
            or not turn_users[0]["content"].endswith(step.input)
            or not backup_users[0]["content"].endswith(step.input)
            or _ENGINE_PLOT_OPEN in turn_users[0]["content"]
            or _ENGINE_PLOT_OPEN in backup_users[0]["content"]
        ):
            failures.append("persisted user message is not the original input only")
        if expectation.opening_count is not None:
            count = sum(
                _metadata(item).get("source") == "story_opening"
                for item in result.persisted_messages
            )
            if count != expectation.opening_count:
                failures.append(
                    f"opening count expected={expectation.opening_count}, actual={count}"
                )
        self._check(
            check_id=f"flow.{flow.id}.{step.id}.persistence",
            category="persistence",
            condition=not failures,
            pass_summary="主历史与冷备只持久化原始输入，Opening 次数正确",
            fail_summary="消息持久化或 Opening 次数异常",
            evidence=tuple(failures),
            flow_id=flow.id,
            step_id=step.id,
        )

    def _queue_semantic_review(
        self,
        flow: StoryAcceptanceFlow,
        step: StoryAcceptanceStep,
        result: StepResult,
    ) -> None:
        check_id = f"flow.{flow.id}.{step.id}.semantic"
        queue_item = {
            "checkId": check_id,
            "flowId": flow.id,
            "stepId": step.id,
            "story": {
                "title": self.loaded.pack.story.title,
                "summary": self.loaded.pack.story.summary,
                "storyPrompt": self.loaded.pack.story.story_prompt,
                "boundaries": list(self.loaded.pack.story.boundaries),
            },
            "playerCharacter": {
                "name": self._player.name,
                "description": self._player.description,
            },
            "mode": step.mode,
            "userInput": step.input,
            "assistantText": result.reply_text,
            "rubric": list(step.semantic_rubric),
            "relevantPackFacts": {
                ref: self._ref_material[ref]
                for ref in (step.context.required_refs if step.context else [])
            },
            "statusBefore": result.status_before,
            "statusAfter": result.status_after,
            "outcome": result.outcome,
            "plotDirectives": list(result.runtime_plot_directives),
            "providerCallRange": {
                "start": result.call_start,
                "endExclusive": result.call_end_exclusive,
            },
        }
        self.semantic_review_items.append(queue_item)
        self.report.add(
            check_id=check_id,
            category="semantic",
            status=AcceptanceStatus.NEEDS_REVIEW,
            summary="真实链路证据已入队，等待当前 Codex 逐条语义裁定",
            evidence=(
                "artifact=semantic-review-queue.json",
                f"rubricCount={len(step.semantic_rubric)}",
                "未生成 codex-review.json 前不得视为通过",
            ),
            flow_id=flow.id,
            step_id=step.id,
            details={
                "reviewQueueItem": True,
                "providerCallRange": queue_item["providerCallRange"],
            },
        )

    def _check_no_derivation_jobs(self) -> None:
        if not self._session_ids:
            return
        placeholders = ",".join("?" for _ in self._session_ids)
        counts: dict[str, int] = {}
        for label, table in (
            ("media", "rpg_media_jobs"),
            ("tts", "rpg_tts_jobs"),
            ("dream", "rpg_session_dream_proposals"),
        ):
            cursor = self.gateway.database.execute_sql(
                f"SELECT COUNT(*) FROM {table} WHERE session_id IN ({placeholders})",
                tuple(self._session_ids),
            )
            counts[label] = int(cursor.fetchone()[0])
        self._check(
            check_id="runtime.no_media_tts_dream",
            category="isolation",
            condition=not any(counts.values()),
            pass_summary="验收 Session 未创建 Media、TTS、生图或 Dream 任务",
            fail_summary="验收链路意外创建了范围外派生任务",
            evidence=(f"counts={counts}",),
        )

    def _check(
        self,
        *,
        check_id: str,
        category: str,
        condition: bool,
        pass_summary: str,
        fail_summary: str,
        evidence: Iterable[str] = (),
        flow_id: str | None = None,
        step_id: str | None = None,
    ) -> None:
        self.report.add(
            check_id=check_id,
            category=category,
            status=(AcceptanceStatus.PASS if condition else AcceptanceStatus.FAIL),
            summary=pass_summary if condition else fail_summary,
            evidence=evidence,
            flow_id=flow_id,
            step_id=step_id,
        )

    def _record_exception(
        self,
        *,
        check_id: str,
        category: str,
        exc: BaseException,
        infrastructure: bool,
        summary: str,
        flow_id: str | None = None,
        step_id: str | None = None,
    ) -> None:
        self.report.add(
            check_id=check_id,
            category=category,
            status=(
                AcceptanceStatus.INFRASTRUCTURE_ERROR
                if infrastructure
                else AcceptanceStatus.FAIL
            ),
            summary=summary,
            evidence=(f"{type(exc).__name__}: {exc}",),
            flow_id=flow_id,
            step_id=step_id,
        )

    def _require_imported(self) -> ImportedStory:
        if self.imported is None:
            raise RuntimeError("Story Pack has not been imported")
        return self.imported


def _status_snapshot(gateway: Any, session_id: str) -> dict[str, Any]:
    return {
        table.name: {
            "id": table.id,
            "sourceStoryStatusTableId": table.source_story_status_table_id,
            "origin": str(table.origin),
            "statusKind": str(table.status_kind),
            "description": table.description,
            "version": table.version,
            "rows": {
                row.key: {
                    "value": row.value,
                    "runtimeKeyLocked": row.runtime_key_locked,
                    "updateRule": row.update_rule,
                    "metadata": dict(row.metadata),
                }
                for row in table.document.rows
            },
        }
        for table in gateway.status.list_tables(session_id)
    }


def _plot_snapshot(gateway: Any, session_id: str) -> dict[str, Any]:
    pending = gateway.plot_scheduling.get_pending_injection(session_id)
    opportunity = gateway.plot_scheduling.get_scene_opportunity(session_id)
    decisions = gateway.plot_scheduling.list_session_decisions(session_id)
    return {
        "pending": _jsonable(pending),
        "opportunity": _jsonable(opportunity),
        "decisions": [_jsonable(item) for item in decisions],
        "cooldowns": _pool_cooldowns(gateway, session_id),
    }


def _pool_cooldowns(gateway: Any, session_id: str) -> list[dict[str, Any]]:
    schedule, _overrides = PlotScheduleManagementService(
        gateway.plot_scheduling
    ).get_session_schedule(session_id)
    scene_time = _session_scene_time(gateway, session_id)
    values = PlotScheduleManagementService(
        gateway.plot_scheduling
    ).get_session_pool_cooldown_diagnostics(
        session_id,
        schedule.pools,
        scene_time=scene_time,
    )
    return [_jsonable(item) for item in values]


def _session_scene_time(gateway: Any, session_id: str) -> SceneTime | None:
    for table in gateway.status.list_tables(session_id):
        if str(table.status_kind) != "scene":
            continue
        row = table.document.row_for_key("时间")
        if row is None or not row.value:
            return None
        try:
            return SceneTime.parse(row.value)
        except ValueError:
            return None
    return None


def _evaluate_status_expectation(
    expectation: StatusExpectation,
    *,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> tuple[bool, tuple[str, ...]]:
    if before is None or after is None:
        return False, ("status table missing before or after",)
    before_rows = dict(before.get("rows") or {})
    after_rows = dict(after.get("rows") or {})
    operation = expectation.operation
    matched_key: str | None = expectation.key
    if expectation.key_regex:
        pattern = re.compile(expectation.key_regex)
        candidates = [key for key in after_rows if pattern.search(key)]
        matched_key = candidates[0] if len(candidates) == 1 else None
    if operation == "changed":
        ok = (
            before != after
            if matched_key is None
            else before_rows.get(matched_key) != after_rows.get(matched_key)
        )
    elif operation == "unchanged":
        ok = (
            before == after
            if matched_key is None
            else before_rows.get(matched_key) == after_rows.get(matched_key)
        )
    elif operation == "created":
        ok = matched_key is not None and (
            matched_key not in before_rows and matched_key in after_rows
        )
    elif operation == "renamed":
        source = expectation.from_key or ""
        target = expectation.to_key or ""
        ok = (
            source in before_rows
            and source not in after_rows
            and target not in before_rows
            and target in after_rows
            and before_rows[source]["value"] == after_rows[target]["value"]
        )
        matched_key = target
    elif operation == "deleted":
        ok = matched_key is not None and (
            matched_key in before_rows and matched_key not in after_rows
        )
    elif operation == "key_exists":
        ok = matched_key is not None and matched_key in after_rows
    else:
        ok = matched_key is not None and matched_key not in after_rows

    row = after_rows.get(matched_key or "")
    if row is not None:
        if expectation.value is not None:
            ok = ok and row.get("value") == expectation.value
        if expectation.value_contains is not None:
            ok = ok and expectation.value_contains in str(row.get("value", ""))
        if expectation.runtime_key_locked is not None:
            ok = ok and (
                row.get("runtimeKeyLocked") == expectation.runtime_key_locked
            )
        if expectation.update_rule_empty is not None:
            ok = ok and (
                (not bool(row.get("updateRule"))) == expectation.update_rule_empty
            )
        if expectation.metadata_empty is not None:
            ok = ok and (
                (not bool(row.get("metadata"))) == expectation.metadata_empty
            )
    return ok, (
        f"matchedKey={matched_key!r}",
        f"beforeRows={json.dumps(before_rows, ensure_ascii=False, sort_keys=True)}",
        f"afterRows={json.dumps(after_rows, ensure_ascii=False, sort_keys=True)}",
    )


def _actual_tool_names(
    reply: AgentReply,
    calls: Sequence[RecordedLiveCall],
    stream_events: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    names: list[str] = []
    try:
        names.extend(item.name for item in main_tool_invocations(reply))
    except AssertionError:
        pass
    for record in reply.status_sub_agent_records or []:
        name = str(record.get("tool_name") or "")
        if name:
            names.append(name)
    for event in stream_events:
        if event.get("kind") == StreamEventKind.TOOL_CALL.value:
            name = str(event.get("tool_name") or "")
            if name:
                names.append(name)
    for call in calls:
        names.extend(name for name, _arguments in _response_tool_calls(call))
    return tuple(dict.fromkeys(names))


def _response_tool_calls(
    call: RecordedLiveCall,
) -> tuple[tuple[str, dict[str, Any]], ...]:
    response = call.response or {}
    raw_calls: list[Any] = []
    if isinstance(response.get("toolCalls"), list):
        raw_calls.extend(response["toolCalls"])
    for chunk in response.get("chunks", []) if isinstance(response.get("chunks"), list) else []:
        if isinstance(chunk, dict) and isinstance(chunk.get("toolCalls"), list):
            raw_calls.extend(chunk["toolCalls"])
    values: list[tuple[str, dict[str, Any]]] = []
    for raw in raw_calls:
        if not isinstance(raw, dict):
            continue
        function = raw.get("function")
        source = function if isinstance(function, dict) else raw
        name = str(source.get("name") or "")
        arguments = source.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if name and isinstance(arguments, dict):
            values.append((name, dict(arguments)))
    return tuple(values)


def _runtime_plot_directives(
    calls: Sequence[RecordedLiveCall],
) -> tuple[str, ...]:
    main = _first_main_call(calls)
    if main is None:
        return ()
    users = [
        str(message.get("content", ""))
        for message in main.messages
        if message.get("role") == "user"
    ]
    if not users:
        return ()
    content = users[-1]
    match = re.search(
        re.escape(_ENGINE_PLOT_OPEN) + r"\s*(.*?)\s*" + re.escape(_ENGINE_PLOT_CLOSE),
        content,
        re.DOTALL,
    )
    if match is None:
        return ()
    body = match.group(1).strip()
    return (body,) if body else ()


def _first_main_call(
    calls: Sequence[RecordedLiveCall],
) -> RecordedLiveCall | None:
    return next((call for call in calls if call.biz_key == AGENT_MAIN_BIZ_KEY), None)


def _message_dict(value: Any) -> dict[str, Any]:
    return {
        "id": value.id,
        "role": value.role,
        "mode": value.mode,
        "content": value.content,
        "turn_id": value.turn_id,
        "seq_in_turn": value.seq_in_turn,
        "metadata_json": value.metadata_json,
    }


def _metadata(message: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(str(message.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _build_ref_material(loaded: LoadedStoryPack) -> dict[str, dict[str, Any]]:
    pack = loaded.pack
    values: dict[str, dict[str, Any]] = {
        pack.story.stable_id: {
            "kind": "story",
            "name": pack.story.title,
            "texts": [pack.story.story_prompt, pack.story.summary],
        }
    }
    for item in pack.resources.openings:
        values[item.stable_id] = {
            "kind": "opening",
            "name": item.title,
            "texts": [item.message],
        }
    for item in pack.resources.characters:
        values[item.stable_id] = {
            "kind": "character",
            "name": item.name,
            "texts": [item.description],
        }
        for detail in item.details:
            values[detail.stable_id] = {
                "kind": "character_detail",
                "name": detail.name,
                "texts": [detail.content],
                "tags": list(detail.tags),
            }
    for item in pack.resources.lorebook:
        values[item.stable_id] = {
            "kind": "lorebook",
            "name": item.name,
            "texts": [item.content, item.description],
        }
    for item in pack.resources.status_tables:
        values[item.stable_id] = {
            "kind": "status_table",
            "name": item.name,
            "texts": [item.description, *(row.value for row in item.rows)],
        }
    for item in pack.resources.plot_schedule.pools:
        values[item.stable_id] = {
            "kind": "plot_pool",
            "name": item.name,
            "texts": [item.description],
        }
    for item in pack.resources.plot_schedule.events:
        values[item.stable_id] = {
            "kind": "plot_event",
            "name": item.title,
            "texts": [item.directive, item.description, item.suitability_hint],
        }
    for item in pack.resources.plot_schedule.outlines:
        values[item.stable_id] = {
            "kind": "plot_outline",
            "name": item.name,
            "texts": [item.description],
        }
        for node in item.nodes:
            values[node.stable_id] = {
                "kind": "plot_node",
                "name": node.stable_id,
                "texts": [node.event_ref, node.scheduled_time],
            }
    return values


def _material_present(text: str, material: Mapping[str, Any]) -> bool:
    name = str(material.get("name") or "")
    texts = [str(value) for value in material.get("texts", []) if str(value)]
    distinctive = [value for value in texts if len(value) >= 24]
    if distinctive:
        return any(value in text or value[:120] in text for value in distinctive)
    return bool(name and name in text)


def _initial_scene_time(loaded: LoadedStoryPack) -> SceneTime | None:
    for table in loaded.pack.resources.status_tables:
        if table.status_kind != "scene":
            continue
        row = next((item for item in table.rows if item.key == "时间"), None)
        if row is not None:
            return SceneTime.parse(row.value)
    return None


def _eligible_pool_ids(
    schedule: Any,
    scene_time: SceneTime,
) -> set[int]:
    bound = {
        node.event_id
        for outline in schedule.outlines
        for node in outline.nodes
    }
    eligible: set[int] = set()
    for event in schedule.events:
        if (
            event.enabled
            and event.id not in bound
            and (event.scheduled_time is None or event.scheduled_time <= scene_time)
            and (event.deadline_time is None or scene_time < event.deadline_time)
        ):
            eligible.add(event.pool_id)
    return {pool.id for pool in schedule.pools if pool.enabled and pool.id in eligible}


def _calendar_gate_errors(
    *,
    selector: PlotScheduleSelector,
    schedule: Any,
    story_id: int,
) -> list[str]:
    errors: list[str] = []
    forced = [
        item
        for item in schedule.events
        if item.dispatch_mode == data_models.PLOT_DISPATCH_FORCED
        and item.scheduled_time is not None
    ]
    for event in forced:
        before = _scene_from_ordinal_minutes(
            event.scheduled_time.ordinal_minutes - 1
        )
        seen_before = False
        seen_at = False
        for index in range(2500):
            session_id = f"calendar_{event.id}_{index}"
            snapshot = PlotScheduleSnapshot(
                session_id=session_id,
                story_id=story_id,
                enabled=True,
                story=schedule,
                overrides=data_models.SessionPlotOverrides(session_id=session_id),
                decisions=(),
            )
            for when, label in ((before, "before"), (event.scheduled_time, "at")):
                selected = selector.select(
                    snapshot,
                    scene_time=when,
                    current_turn_id=2,
                    completed_world_turn_ids=(1,),
                )
                ids = {
                    candidate.event.id
                    for item in selected
                    if item.source_kind == data_models.PLOT_SOURCE_POOL
                    for candidate in getattr(item, "candidates", (item,))
                }
                if event.id in ids:
                    if label == "before":
                        seen_before = True
                    else:
                        seen_at = True
            if seen_at and not seen_before:
                break
        if seen_before or not seen_at:
            errors.append(
                f"event={event.id} seenBefore={seen_before} seenAt={seen_at}"
            )
    return errors


def _scene_text(value: SceneTime | None) -> str | None:
    return value.format() if value is not None else None


def _scene_from_ordinal_minutes(value: int) -> SceneTime:
    if value < 0:
        raise ValueError("SceneTime ordinal must be non-negative")
    day_ordinal, minute_of_day = divmod(value, 24 * 60)
    year_month_ordinal, day_offset = divmod(day_ordinal, 31)
    year_offset, month_offset = divmod(year_month_ordinal, 12)
    hour, minute = divmod(minute_of_day, 60)
    return SceneTime(
        year=year_offset + 1,
        month=month_offset + 1,
        day=day_offset + 1,
        hour=hour,
        minute=minute,
    )


def _session_id(flow_id: str, ordinal: int) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", flow_id)
    return f"sa_{ordinal:02d}_{normalized}"[:96]


def _selection_identity(values: Sequence[Any]) -> list[dict[str, Any]]:
    """Compact stable-seed evidence without serializing full directives."""

    result: list[dict[str, Any]] = []
    for value in values:
        primary = getattr(value, "primary", value)
        result.append({
            "sourceKind": str(getattr(primary, "source_kind", "")),
            "containerId": int(getattr(primary, "container_id", 0) or 0),
            "eventId": int(
                getattr(getattr(primary, "event", None), "id", 0) or 0
            ),
            "candidateEventIds": [
                int(getattr(getattr(item, "event", None), "id", 0) or 0)
                for item in getattr(value, "candidates", ())
            ],
        })
    return result


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, SceneTime):
        return value.format()
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, Counter)):
        return [_jsonable(item) for item in value]
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int)):
        return enum_value
    return str(value)


__all__ = ["ImportedStory", "StepResult", "StoryAcceptanceRunner"]
