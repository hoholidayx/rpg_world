from __future__ import annotations

from commons.scene_time import SceneTime
from rpg_core.rp_modules.plot_scheduler import PlotStoryProjectionService
from rpg_data import models


class _PlotStoryData:
    def __init__(self) -> None:
        first = models.StoryPlotEvent(
            id=101,
            story_id=1,
            pool_id=10,
            title="公开起点",
            directive="展示故事起点。",
            position=0,
        )
        repeated = models.StoryPlotEvent(
            id=102,
            story_id=1,
            pool_id=10,
            title="已出现事件的新文案",
            directive="展示已经出现的事件。",
            description="同一事件被大纲和事件池重复引用。",
            suitability_hint="角色仍在场。",
            deadline_time=SceneTime(1, 1, 2, 12),
            position=1,
            allow_repeat=True,
            repeat_cooldown_minutes=30,
        )
        hidden = models.StoryPlotEvent(
            id=103,
            story_id=1,
            pool_id=10,
            title="未来秘密",
            directive="不要提前公开。",
            position=2,
            enabled=False,
        )
        outline = models.StoryPlotOutline(
            id=20,
            story_id=1,
            name="主线",
            description="按顺序推进。",
            priority=5,
            nodes=(
                models.StoryPlotOutlineNode(
                    id=201,
                    story_id=1,
                    outline_id=20,
                    event_id=101,
                    scheduled_time=SceneTime(1, 1, 1, 8),
                    position=0,
                ),
                models.StoryPlotOutlineNode(
                    id=202,
                    story_id=1,
                    outline_id=20,
                    event_id=102,
                    scheduled_time=SceneTime(1, 1, 1, 9),
                    dispatch_mode=models.PLOT_DISPATCH_FORCED,
                    position=1,
                ),
                models.StoryPlotOutlineNode(
                    id=203,
                    story_id=1,
                    outline_id=20,
                    event_id=103,
                    scheduled_time=SceneTime(1, 1, 1, 10),
                    position=2,
                ),
            ),
        )
        self.schedule = models.StoryPlotSchedule(
            story_id=1,
            pools=(
                models.StoryPlotEventPool(
                    id=10,
                    story_id=1,
                    name="动态事件",
                    description="随机插曲。",
                ),
            ),
            events=(first, repeated, hidden),
            outlines=(outline,),
        )
        self.overrides = models.SessionPlotOverrides(
            session_id="s1",
            disabled_event_ids=frozenset((103,)),
            disabled_outline_node_ids=frozenset((202,)),
        )
        self.aggregates = models.SessionPlotDecisionAggregates(
            events=(
                models.SessionPlotEventDecisionAggregate(
                    event_id=102,
                    decision_count=2,
                    latest_turn_id=8,
                ),
            ),
            sources=(
                models.SessionPlotSourceDecisionAggregate(
                    source_kind=models.PLOT_SOURCE_OUTLINE,
                    source_id=202,
                    decision_count=1,
                    latest_turn_id=7,
                ),
            ),
        )
        self.requested_statuses: tuple[str, ...] = ()

    def get_session_schedule(
        self,
        session_id: str,
    ) -> tuple[
        models.StoryPlotSchedule,
        models.SessionPlotOverrides,
    ]:
        assert session_id == "s1"
        return self.schedule, self.overrides

    def summarize_session_decisions(
        self,
        session_id: str,
        *,
        decision_statuses,
    ) -> models.SessionPlotDecisionAggregates:
        assert session_id == "s1"
        self.requested_statuses = tuple(decision_statuses)
        return self.aggregates


def test_plot_story_projection_masks_future_events_and_separates_sources() -> None:
    data = _PlotStoryData()
    story = PlotStoryProjectionService(data).project("s1")

    assert data.requested_statuses == (models.PLOT_DECISION_TRIGGERED,)
    assert story.spoiler_protection_enabled is True
    assert [line.name for line in story.outlines] == ["主线"]
    assert [line.name for line in story.pools] == ["动态事件"]

    outline_nodes = story.outlines[0].nodes
    assert outline_nodes[0].revealed is True
    assert outline_nodes[0].event_injected is False
    assert outline_nodes[0].event_detail is not None

    repeated_outline = outline_nodes[1]
    assert repeated_outline.revealed is True
    assert repeated_outline.event_injection_count == 2
    assert repeated_outline.last_event_injection_turn_id == 8
    assert repeated_outline.source_injected is True
    assert repeated_outline.source_injection_count == 1
    assert repeated_outline.last_source_injection_turn_id == 7
    assert repeated_outline.session_disabled is True
    assert repeated_outline.event_detail is not None
    assert repeated_outline.event_detail.title == "已出现事件的新文案"
    assert repeated_outline.event_detail.dispatch_mode == models.PLOT_DISPATCH_FORCED
    assert repeated_outline.event_detail.scheduled_time == SceneTime(1, 1, 1, 9)
    assert repeated_outline.event_detail.allow_repeat is False

    hidden_outline = outline_nodes[2]
    assert hidden_outline.revealed is False
    assert hidden_outline.event_detail is None
    assert hidden_outline.slot_key == "outline:20:2"

    repeated_pool = story.pools[0].nodes[1]
    assert repeated_pool.revealed is True
    assert repeated_pool.event_injected is True
    assert repeated_pool.source_injected is False
    assert repeated_pool.event_detail is not None
    assert repeated_pool.event_detail.allow_repeat is True
    assert repeated_pool.event_detail.repeat_cooldown_minutes == 30

    hidden_pool = story.pools[0].nodes[2]
    assert hidden_pool.revealed is False
    assert hidden_pool.session_disabled is True
    assert hidden_pool.event_detail is None


def test_plot_story_projection_reveals_every_current_event_on_request() -> None:
    story = PlotStoryProjectionService(_PlotStoryData()).project(
        "s1",
        reveal_spoilers=True,
    )

    assert story.spoiler_protection_enabled is False
    hidden_outline = story.outlines[0].nodes[2]
    assert hidden_outline.revealed is True
    assert hidden_outline.event_detail is not None
    assert hidden_outline.event_detail.title == "未来秘密"
