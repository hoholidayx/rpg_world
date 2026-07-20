from __future__ import annotations

from dataclasses import replace

import pytest

from commons.scene_time import SceneTime
from rpg_core.rp_modules.plot_scheduler import (
    CreatePlotEventCommand,
    CreatePlotNodeCommand,
    CreatePlotOutlineCommand,
    CreatePlotPoolCommand,
    PLOT_DERIVATION_COPY_POLICY,
    PlotDefinitionInUseError,
    PlotScheduleLedgerConflictError,
    PlotScheduleLedgerService,
    PlotScheduleManagementService,
    UpdatePlotEventCommand,
    UpdatePlotNodeCommand,
)
from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway


def test_management_owns_default_position_move_reorder_and_repeat_rules() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        service = PlotScheduleManagementService(gateway.plot_scheduling)
        first_pool = service.create_pool(
            CreatePlotPoolCommand(
                workspace_id="demo_workspace",
                story_id=1,
                name="日常池",
            )
        )
        second_pool = service.create_pool(
            CreatePlotPoolCommand(
                workspace_id="demo_workspace",
                story_id=1,
                name="夜间池",
            )
        )
        scheduled_time = SceneTime(1, 1, 1, 8)
        first = service.create_event(
            CreatePlotEventCommand(
                workspace_id="demo_workspace",
                story_id=1,
                pool_id=first_pool.id,
                title="来信",
                directive="送来一封信。",
                scheduled_time=scheduled_time,
            )
        )
        second = service.create_event(
            CreatePlotEventCommand(
                workspace_id="demo_workspace",
                story_id=1,
                pool_id=first_pool.id,
                title="钟声",
                directive="远处响起钟声。",
            )
        )
        assert (first.position, second.position) == (0, 1)

        moved = service.update_event(
            UpdatePlotEventCommand(
                workspace_id="demo_workspace",
                story_id=1,
                event_id=second.id,
                pool_id=second_pool.id,
            )
        )
        assert moved.pool_id == second_pool.id
        assert moved.position == 0

        third = service.create_event(
            CreatePlotEventCommand(
                workspace_id="demo_workspace",
                story_id=1,
                pool_id=first_pool.id,
                title="雨停",
                directive="雨势逐渐停歇。",
            )
        )
        reordered = service.reorder_events(
            "demo_workspace",
            1,
            first_pool.id,
            (third.id, first.id),
        )
        assert [item.id for item in reordered] == [third.id, first.id]

        with pytest.raises(ValueError, match="every current id"):
            service.reorder_events(
                "demo_workspace",
                1,
                first_pool.id,
                (first.id,),
            )
        assert [
            item.id
            for item in service.get_story_schedule("demo_workspace", 1).events
            if item.pool_id == first_pool.id
        ] == [third.id, first.id]

        unchanged_time = service.update_event(
            UpdatePlotEventCommand(
                workspace_id="demo_workspace",
                story_id=1,
                event_id=first.id,
                title="加急来信",
            )
        )
        assert unchanged_time.scheduled_time == scheduled_time
        cleared_time = service.update_event(
            UpdatePlotEventCommand(
                workspace_id="demo_workspace",
                story_id=1,
                event_id=first.id,
                scheduled_time=None,
            )
        )
        assert cleared_time.scheduled_time is None

        with pytest.raises(ValueError, match="must be positive"):
            service.create_event(
                CreatePlotEventCommand(
                    workspace_id="demo_workspace",
                    story_id=1,
                    pool_id=first_pool.id,
                    title="非法重复",
                    directive="不会保存。",
                    allow_repeat=True,
                    repeat_cooldown_minutes=0,
                )
            )
        repeating = service.create_event(
            CreatePlotEventCommand(
                workspace_id="demo_workspace",
                story_id=1,
                pool_id=first_pool.id,
                title="巡夜钟",
                directive="巡夜钟再次响起。",
                allow_repeat=True,
                repeat_cooldown_minutes=30,
            )
        )
        disabled_repeat = service.update_event(
            UpdatePlotEventCommand(
                workspace_id="demo_workspace",
                story_id=1,
                event_id=repeating.id,
                allow_repeat=False,
            )
        )
        assert disabled_repeat.allow_repeat is False
        assert disabled_repeat.repeat_cooldown_minutes == 0
    finally:
        gateway.close()


def test_management_keeps_outline_time_rules_atomic_and_maps_in_use_errors() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        service = PlotScheduleManagementService(gateway.plot_scheduling)
        pool = service.create_pool(
            CreatePlotPoolCommand(
                workspace_id="demo_workspace",
                story_id=1,
                name="主线事件池",
            )
        )
        event = service.create_event(
            CreatePlotEventCommand(
                workspace_id="demo_workspace",
                story_id=1,
                pool_id=pool.id,
                title="主线事件",
                directive="推进主线。",
            )
        )
        outline = service.create_outline(
            CreatePlotOutlineCommand(
                workspace_id="demo_workspace",
                story_id=1,
                name="时间线",
            )
        )
        first = service.create_node(
            CreatePlotNodeCommand(
                workspace_id="demo_workspace",
                story_id=1,
                outline_id=outline.id,
                event_id=event.id,
                scheduled_time=SceneTime(1, 1, 2, 10),
            )
        )

        with pytest.raises(ValueError, match="nondecreasing"):
            service.create_node(
                CreatePlotNodeCommand(
                    workspace_id="demo_workspace",
                    story_id=1,
                    outline_id=outline.id,
                    event_id=event.id,
                    scheduled_time=SceneTime(1, 1, 1, 10),
                )
            )
        current = service.get_story_schedule("demo_workspace", 1)
        assert current is not None
        assert current.outlines[0].nodes == (first,)

        second = service.create_node(
            CreatePlotNodeCommand(
                workspace_id="demo_workspace",
                story_id=1,
                outline_id=outline.id,
                event_id=event.id,
                scheduled_time=SceneTime(1, 1, 3, 10),
            )
        )
        with pytest.raises(ValueError, match="nondecreasing"):
            service.update_node(
                UpdatePlotNodeCommand(
                    workspace_id="demo_workspace",
                    story_id=1,
                    outline_id=outline.id,
                    node_id=second.id,
                    scheduled_time=SceneTime(1, 1, 1, 9),
                )
            )
        refreshed = service.get_story_schedule("demo_workspace", 1)
        assert refreshed is not None
        assert refreshed.outlines[0].nodes[1].scheduled_time == SceneTime(
            1,
            1,
            3,
            10,
        )

        with pytest.raises(ValueError, match="nondecreasing"):
            service.reorder_nodes(
                "demo_workspace",
                1,
                outline.id,
                (second.id, first.id),
            )
        with pytest.raises(ValueError, match="every current id"):
            service.reorder_nodes(
                "demo_workspace",
                1,
                outline.id,
                (first.id,),
            )
        refreshed = service.get_story_schedule("demo_workspace", 1)
        assert refreshed is not None
        assert [item.id for item in refreshed.outlines[0].nodes] == [
            first.id,
            second.id,
        ]

        with pytest.raises(PlotDefinitionInUseError):
            service.delete_event("demo_workspace", 1, event.id)
        with pytest.raises(PlotDefinitionInUseError):
            service.delete_pool("demo_workspace", 1, pool.id)

        service.delete_outline("demo_workspace", 1, outline.id)
        service.delete_event("demo_workspace", 1, event.id)
        service.delete_pool("demo_workspace", 1, pool.id)
    finally:
        gateway.close()


def test_plot_ledger_policy_validates_lanes_and_owns_derivation_selection() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        ledger = PlotScheduleLedgerService(gateway.plot_scheduling)
        pool_decision = models.StagedPlotScheduleDecision(
            source_kind=models.PLOT_SOURCE_POOL,
            source_id=1,
            event_id=1,
            container_id=1,
            decision_status=models.PLOT_DECISION_TRIGGERED,
            dispatch_mode=models.PLOT_DISPATCH_FORCED,
            scene_time=SceneTime(1, 1, 1, 8),
            event_snapshot={"eventTitle": "池事件"},
        )
        outline_decision = replace(
            pool_decision,
            source_kind=models.PLOT_SOURCE_OUTLINE,
            source_id=2,
            container_id=2,
        )

        created = ledger.record(
            "s_forest001",
            1,
            (pool_decision, outline_decision),
        )
        assert {item.source_kind for item in created} == models.PLOT_SOURCE_KINDS

        with pytest.raises(ValueError, match="one plot schedule decision"):
            ledger.record(
                "s_forest001",
                2,
                (pool_decision, replace(pool_decision, source_id=3)),
            )
        with pytest.raises(ValueError, match="supported scheduling lanes"):
            ledger.record(
                "s_forest001",
                2,
                (pool_decision, outline_decision, pool_decision),
            )
        with pytest.raises(ValueError, match="unsupported plot decision status"):
            ledger.record(
                "s_forest001",
                2,
                (replace(pool_decision, decision_status="invalid-status"),),
            )
        with pytest.raises(PlotScheduleLedgerConflictError):
            ledger.record("s_forest001", 1, (pool_decision,))

        assert PLOT_DERIVATION_COPY_POLICY.copy_overrides is True
        assert PLOT_DERIVATION_COPY_POLICY.decision_statuses == frozenset(
            (models.PLOT_DECISION_TRIGGERED,)
        )
    finally:
        gateway.close()
