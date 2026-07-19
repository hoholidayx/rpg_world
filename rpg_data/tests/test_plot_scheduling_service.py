from __future__ import annotations

from dataclasses import replace

import pytest

from commons.scene_time import SceneTime
from rpg_data import models
from rpg_data.services import PlotDefinitionInUseError
from rpg_data.services.gateway import DataServiceGateway


def test_plot_definition_crud_ordering_and_session_overrides() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        service = gateway.plot_scheduling
        pool = service.create_pool(
            "demo_workspace",
            1,
            name="日常事件",
            selection_mode=models.PLOT_POOL_SEQUENTIAL,
            priority=20,
        )
        first = service.create_event(
            "demo_workspace",
            1,
            pool_id=pool.id,
            title="来信",
            directive="让信使送来一封信。",
            dispatch_mode=models.PLOT_DISPATCH_SOFT,
        )
        second = service.create_event(
            "demo_workspace",
            1,
            pool_id=pool.id,
            title="钟声",
            directive="远处响起钟声。",
            allow_repeat=True,
            repeat_cooldown_minutes=60,
        )
        outline = service.create_outline(
            "demo_workspace",
            1,
            name="主线",
            priority=10,
        )
        node = service.create_node(
            "demo_workspace",
            1,
            outline.id,
            event_id=first.id,
            scheduled_time=SceneTime(1, 1, 1, 9),
            dispatch_mode=models.PLOT_DISPATCH_FORCED,
        )

        schedule = service.get_story_schedule("demo_workspace", 1)
        assert schedule is not None
        assert schedule.pools == (pool,)
        assert [item.id for item in schedule.events] == [first.id, second.id]
        assert schedule.outlines[0].nodes == (node,)

        reordered = service.reorder_events(
            "demo_workspace",
            1,
            pool.id,
            [second.id, first.id],
        )
        assert [item.id for item in reordered] == [second.id, first.id]
        overrides = service.set_session_event_disabled(
            "s_forest001",
            second.id,
            True,
        )
        overrides = service.set_session_node_disabled(
            "s_forest001",
            node.id,
            True,
        )
        assert overrides.disabled_event_ids == frozenset({second.id})
        assert overrides.disabled_outline_node_ids == frozenset({node.id})

        with pytest.raises(PlotDefinitionInUseError):
            service.delete_event("demo_workspace", 1, first.id)
        with pytest.raises(PlotDefinitionInUseError):
            service.delete_pool("demo_workspace", 1, pool.id)
    finally:
        gateway.close()


def test_outline_time_validation_and_repeat_policy_are_atomic() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        service = gateway.plot_scheduling
        pool = service.create_pool("demo_workspace", 1, name="池")
        event = service.create_event(
            "demo_workspace",
            1,
            pool_id=pool.id,
            title="事件",
            directive="发生事件。",
        )
        with pytest.raises(ValueError, match="must be positive"):
            service.create_event(
                "demo_workspace",
                1,
                pool_id=pool.id,
                title="错误重复",
                directive="不会保存。",
                allow_repeat=True,
                repeat_cooldown_minutes=0,
            )
        outline = service.create_outline("demo_workspace", 1, name="时间线")
        service.create_node(
            "demo_workspace",
            1,
            outline.id,
            event_id=event.id,
            scheduled_time=SceneTime(1, 1, 2, 10),
        )
        with pytest.raises(ValueError, match="nondecreasing"):
            service.create_node(
                "demo_workspace",
                1,
                outline.id,
                event_id=event.id,
                scheduled_time=SceneTime(1, 1, 1, 10),
            )
        current = service.get_story_schedule_by_id(1)
        assert len(current.outlines[0].nodes) == 1
    finally:
        gateway.close()


def test_plot_decisions_round_trip_clear_and_derivation_copy() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        service = gateway.plot_scheduling
        pool = service.create_pool("demo_workspace", 1, name="池")
        event = service.create_event(
            "demo_workspace",
            1,
            pool_id=pool.id,
            title="事件",
            directive="推进事件。",
        )
        scene_time = SceneTime(1, 1, 1, 12)
        staged = models.StagedPlotScheduleDecision(
            source_kind=models.PLOT_SOURCE_POOL,
            source_id=event.id,
            event_id=event.id,
            container_id=pool.id,
            decision_status=models.PLOT_DECISION_TRIGGERED,
            dispatch_mode=models.PLOT_DISPATCH_SOFT,
            scene_time=scene_time,
            event_snapshot={"eventTitle": event.title},
            reason="适合",
        )
        created = service.record_decisions("s_forest001", 2, [staged])
        assert created[0].scene_time == scene_time
        assert created[0].event_snapshot == {"eventTitle": "事件"}
        late_earlier_turn = service.record_decisions(
            "s_forest001",
            1,
            [replace(staged, decision_status=models.PLOT_DECISION_DEFERRED)],
        )
        first_page = service.list_session_decisions("s_forest001", limit=1)
        second_page = service.list_session_decisions(
            "s_forest001",
            limit=1,
            before_id=first_page[0].id,
        )
        assert [item.id for item in first_page] == [late_earlier_turn[0].id]
        assert [item.id for item in second_page] == [created[0].id]

        service.set_session_event_disabled("s_forest001", event.id, True)
        target = gateway.catalog.create_session(
            "demo_workspace",
            1,
            session_id="s_plot_branch",
            title="剧情分支",
        )
        assert target is not None
        assert service.copy_derivation_state("s_forest001", target.id, 2) == 1
        _, copied_overrides, copied = service.get_session_state(target.id)
        assert copied_overrides.disabled_event_ids == frozenset({event.id})
        assert [item.decision_status for item in copied] == [models.PLOT_DECISION_TRIGGERED]

        assert service.clear_session_decisions(target.id) == 1
        _, retained_overrides, decisions = service.get_session_state(target.id)
        assert decisions == []
        assert retained_overrides.disabled_event_ids == frozenset({event.id})
    finally:
        gateway.close()
