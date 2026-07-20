from __future__ import annotations

from dataclasses import replace

import pytest

from commons.scene_time import SceneTime
from rpg_data import models
from rpg_data.services import PlotScheduleDataIntegrityError
from rpg_data.services.gateway import DataServiceGateway


def test_plot_data_service_exposes_explicit_crud_and_ownership_checks() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        service = gateway.plot_scheduling
        pool = service.create_pool(
            story_id=1,
            name="日常事件",
            description="显式持久化参数",
            selection_mode=models.PLOT_POOL_SEQUENTIAL,
            priority=20,
            enabled=True,
        )
        first = service.create_event(
            story_id=1,
            pool_id=pool.id,
            title="来信",
            directive="让信使送来一封信。",
            description="",
            suitability_hint="",
            dispatch_mode=models.PLOT_DISPATCH_SOFT,
            scheduled_time=None,
            position=4,
            enabled=True,
            allow_repeat=False,
            repeat_cooldown_minutes=0,
        )
        second = service.create_event(
            story_id=1,
            pool_id=pool.id,
            title="钟声",
            directive="远处响起钟声。",
            description="",
            suitability_hint="",
            dispatch_mode=models.PLOT_DISPATCH_FORCED,
            scheduled_time=SceneTime(1, 1, 1, 8),
            position=9,
            enabled=True,
            allow_repeat=True,
            repeat_cooldown_minutes=60,
        )
        outline = service.create_outline(
            story_id=1,
            name="主线",
            description="",
            priority=10,
            enabled=True,
        )
        node = service.create_node(
            story_id=1,
            outline_id=outline.id,
            event_id=first.id,
            scheduled_time=SceneTime(1, 1, 1, 9),
            dispatch_mode=models.PLOT_DISPATCH_FORCED,
            position=3,
            enabled=True,
        )

        updated_pool = service.update_pool(
            pool.id,
            name="日常事件池",
            description="更新后的描述",
            selection_mode=models.PLOT_POOL_RANDOM,
            priority=30,
            enabled=False,
        )
        updated_event = service.update_event(
            first.id,
            pool_id=pool.id,
            title="加急来信",
            description="更新",
            directive="让信使送来一封加急信。",
            suitability_hint="角色仍在城内",
            dispatch_mode=models.PLOT_DISPATCH_SOFT,
            scheduled_time=SceneTime(1, 1, 1, 7),
            position=2,
            enabled=True,
            allow_repeat=False,
            repeat_cooldown_minutes=0,
        )
        updated_outline = service.update_outline(
            outline.id,
            name="主线 A",
            description="更新",
            priority=11,
            enabled=False,
        )
        updated_node = service.update_node(
            node.id,
            event_id=second.id,
            scheduled_time=SceneTime(1, 1, 1, 10),
            dispatch_mode=models.PLOT_DISPATCH_SOFT,
            position=1,
            enabled=False,
        )

        assert updated_pool is not None and updated_pool.name == "日常事件池"
        assert updated_event is not None and updated_event.position == 2
        assert updated_outline is not None and updated_outline.name == "主线 A"
        assert updated_node is not None and updated_node.event_id == second.id
        assert service.get_pool(999, pool.id) is None
        assert service.get_event(999, first.id) is None
        assert service.get_outline(999, outline.id) is None
        assert service.get_node(1, outline.id + 1, node.id) is None

        service.set_event_positions((second.id, first.id))
        service.set_node_positions((node.id,))
        schedule = service.get_story_schedule("demo_workspace", 1)
        assert schedule is not None
        assert [item.id for item in schedule.events] == [second.id, first.id]
        assert schedule.outlines[0].nodes[0].position == 0

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
        assert overrides.disabled_event_ids == frozenset((second.id,))
        assert overrides.disabled_outline_node_ids == frozenset((node.id,))

        assert service.delete_node(node.id) == 1
        assert service.delete_outline(outline.id) == 1
        assert service.delete_event(first.id) == 1
        assert service.delete_event(second.id) == 1
        assert service.delete_pool(pool.id) == 1
    finally:
        gateway.close()


def test_plot_data_constraints_and_transaction_rollback() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        service = gateway.plot_scheduling
        pool = service.create_pool(
            story_id=1,
            name="约束池",
            description="",
            selection_mode=models.PLOT_POOL_RANDOM,
            priority=0,
            enabled=True,
        )

        with pytest.raises(PlotScheduleDataIntegrityError):
            service.create_event(
                story_id=1,
                pool_id=pool.id,
                title="非法重复事件",
                directive="不会保存。",
                description="",
                suitability_hint="",
                dispatch_mode=models.PLOT_DISPATCH_SOFT,
                scheduled_time=None,
                position=0,
                enabled=True,
                allow_repeat=True,
                repeat_cooldown_minutes=0,
            )
        assert service.list_events(1, pool_id=pool.id) == []

        with pytest.raises(RuntimeError, match="rollback marker"):
            with service.transaction():
                service.create_outline(
                    story_id=1,
                    name="应回滚大纲",
                    description="",
                    priority=0,
                    enabled=True,
                )
                raise RuntimeError("rollback marker")
        schedule = service.get_story_schedule_by_id(1)
        assert schedule.outlines == ()

        with pytest.raises(FileNotFoundError):
            service.create_event(
                story_id=999,
                pool_id=pool.id,
                title="错误归属",
                directive="不会保存。",
                description="",
                suitability_hint="",
                dispatch_mode=models.PLOT_DISPATCH_SOFT,
                scheduled_time=None,
                position=0,
                enabled=True,
                allow_repeat=False,
                repeat_cooldown_minutes=0,
            )

        duplicate_lane = models.StagedPlotScheduleDecision(
            source_kind=models.PLOT_SOURCE_POOL,
            source_id=1,
            event_id=1,
            container_id=pool.id,
            decision_status=models.PLOT_DECISION_TRIGGERED,
            dispatch_mode=models.PLOT_DISPATCH_FORCED,
            scene_time=SceneTime(1, 1, 1, 8),
            event_snapshot={"eventTitle": "批量回滚"},
        )
        with pytest.raises(PlotScheduleDataIntegrityError):
            service.append_decisions(
                "s_forest001",
                5,
                (duplicate_lane, replace(duplicate_lane, source_id=2)),
            )
        assert service.list_session_decisions("s_forest001") == []
    finally:
        gateway.close()


def test_plot_data_ledger_pagination_and_caller_selected_copy() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        service = gateway.plot_scheduling
        pool = service.create_pool(
            story_id=1,
            name="账本池",
            description="",
            selection_mode=models.PLOT_POOL_RANDOM,
            priority=0,
            enabled=True,
        )
        event = service.create_event(
            story_id=1,
            pool_id=pool.id,
            title="事件",
            directive="推进事件。",
            description="",
            suitability_hint="",
            dispatch_mode=models.PLOT_DISPATCH_SOFT,
            scheduled_time=None,
            position=0,
            enabled=True,
            allow_repeat=False,
            repeat_cooldown_minutes=0,
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
        triggered = service.append_decisions("s_forest001", 2, (staged,))
        errored = service.append_decisions(
            "s_forest001",
            1,
            (
                replace(
                    staged,
                    decision_status=models.PLOT_DECISION_ERROR,
                    error_code="JUDGE_UNAVAILABLE",
                    error_message="judge unavailable",
                ),
            ),
        )

        first_page = service.list_session_decisions("s_forest001", limit=1)
        second_page = service.list_session_decisions(
            "s_forest001",
            limit=1,
            before_id=first_page[0].id,
        )
        assert [item.id for item in first_page] == [errored[0].id]
        assert [item.id for item in second_page] == [triggered[0].id]

        service.set_session_event_disabled("s_forest001", event.id, True)
        target = gateway.catalog.create_session(
            "demo_workspace",
            1,
            session_id="s_plot_branch",
            title="剧情分支",
        )
        assert target is not None
        service.copy_overrides("s_forest001", target.id)
        copied_count = service.copy_decisions(
            "s_forest001",
            target.id,
            2,
            decision_statuses=frozenset((models.PLOT_DECISION_ERROR,)),
        )
        assert copied_count == 1

        _, copied_overrides, copied = service.get_session_state(target.id)
        assert copied_overrides.disabled_event_ids == frozenset((event.id,))
        assert [item.decision_status for item in copied] == [
            models.PLOT_DECISION_ERROR
        ]
        assert copied[0].error_code == "JUDGE_UNAVAILABLE"
        assert copied[0].error_message == "judge unavailable"
        with pytest.raises(PlotScheduleDataIntegrityError):
            service.copy_decisions(
                "s_forest001",
                target.id,
                2,
                decision_statuses=frozenset((models.PLOT_DECISION_ERROR,)),
            )
        assert service.copy_decisions(
            "s_forest001",
            target.id,
            2,
            decision_statuses=frozenset(),
        ) == 0

        assert service.clear_decisions(target.id) == 1
        _, retained_overrides, decisions = service.get_session_state(target.id)
        assert decisions == []
        assert retained_overrides.disabled_event_ids == frozenset((event.id,))
    finally:
        gateway.close()
