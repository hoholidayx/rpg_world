from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from commons.scene_time import SceneTime
from rpg_core.rp_modules.plot_scheduler import (
    PlotPendingInjectionTurnState,
    PlotScheduleSnapshot,
)
from rpg_core.rp_modules.plot_scheduler.tools import (
    PlotEventMarkNextTool,
    PlotSandboxReadTool,
)
from rpg_data import models


def _snapshot(
    *,
    pending: models.SessionPlotPendingInjection | None = None,
) -> PlotScheduleSnapshot:
    event = models.StoryPlotEvent(
        id=11,
        story_id=1,
        pool_id=7,
        title="原事件标题",
        directive="原事件指令。",
        description="事件描述",
        suitability_hint="雨夜",
        dispatch_mode=models.PLOT_DISPATCH_SOFT,
        scheduled_time=SceneTime(1, 1, 1, 10),
        deadline_time=SceneTime(1, 1, 1, 20),
        position=2,
        enabled=False,
        version=4,
    )
    return PlotScheduleSnapshot(
        session_id="s1",
        story_id=1,
        enabled=True,
        story=models.StoryPlotSchedule(
            story_id=1,
            pools=(
                models.StoryPlotEventPool(
                    id=7,
                    story_id=1,
                    name="雨夜池",
                    priority=3,
                ),
            ),
            events=(event,),
            outlines=(
                models.StoryPlotOutline(
                    id=5,
                    story_id=1,
                    name="主线",
                    nodes=(
                        models.StoryPlotOutlineNode(
                            id=9,
                            story_id=1,
                            outline_id=5,
                            event_id=11,
                            scheduled_time=SceneTime(1, 1, 1, 12),
                        ),
                    ),
                ),
            ),
        ),
        overrides=models.SessionPlotOverrides(
            "s1",
            disabled_event_ids=frozenset((11,)),
        ),
        decisions=(),
        pending_injection=pending,
    )


def _scratch(
    pending: models.SessionPlotPendingInjection | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        turn_id=8,
        plot_pending_injection=PlotPendingInjectionTurnState(base=pending),
    )


@pytest.mark.asyncio
async def test_plot_sandbox_read_lists_details_and_pending_snapshot() -> None:
    pending = models.SessionPlotPendingInjection(
        session_id="s1",
        story_id=1,
        source_event_id=99,
        source_event_version=2,
        source_pool_id=7,
        source_pool_name="已删除事件池",
        event_title="冻结标题",
        directive="冻结指令。",
        requested_turn_id=6,
    )
    tool = PlotSandboxReadTool(_snapshot(pending=pending), _scratch(pending))

    schedule = json.loads(await tool.execute(resource="schedule"))
    event = json.loads(await tool.execute(resource="event", id=11))
    outline = json.loads(await tool.execute(resource="outline", id=5))

    assert schedule["ok"] is True
    assert schedule["counts"] == {
        "pools": 1,
        "events": 1,
        "outlines": 1,
        "nodes": 1,
    }
    assert schedule["pendingInjection"]["sourceEventId"] == 99
    assert event["item"]["directive"] == "原事件指令。"
    assert event["item"]["pool"]["name"] == "雨夜池"
    assert event["item"]["outlineNodeRefs"][0]["nodeId"] == 9
    assert outline["item"]["nodes"][0]["eventTitle"] == "原事件标题"


@pytest.mark.asyncio
async def test_plot_event_mark_freezes_original_or_temporary_content() -> None:
    scratch = _scratch()
    tool = PlotEventMarkNextTool(_snapshot(), scratch)

    original = json.loads(await tool.execute(event_id=11))
    assert original["pendingInjection"]["eventTitle"] == "原事件标题"
    assert original["pendingInjection"]["directive"] == "原事件指令。"
    first = scratch.plot_pending_injection.desired
    assert first is not None
    assert first.source_event_version == 4
    assert first.event_snapshot["originalDirective"] == "原事件指令。"

    custom = json.loads(
        await tool.execute(
            event_id=11,
            title="临时标题",
            directive="临时注入指令。",
        )
    )
    assert custom["pendingInjection"]["eventTitle"] == "临时标题"
    assert custom["pendingInjection"]["directive"] == "临时注入指令。"
    assert custom["replacedOrCleared"]["eventTitle"] == "原事件标题"
    desired = scratch.plot_pending_injection.desired
    assert desired is not None
    assert desired.event_snapshot["eventTitle"] == "临时标题"
    assert desired.event_snapshot["directive"] == "临时注入指令。"


@pytest.mark.asyncio
async def test_plot_event_mark_null_clears_and_rejects_temporary_fields() -> None:
    scratch = _scratch()
    tool = PlotEventMarkNextTool(_snapshot(), scratch)
    await tool.execute(event_id=11)

    cleared = json.loads(await tool.execute(event_id=None))
    invalid = json.loads(
        await tool.execute(event_id=None, directive="不允许")
    )

    assert cleared == {
        "ok": True,
        "changed": True,
        "pendingForNextWorldTurn": False,
        "pendingInjection": None,
        "replacedOrCleared": {
            "sourceEventId": 11,
            "sourceEventVersion": 4,
            "sourcePoolId": 7,
            "sourcePoolName": "雨夜池",
            "eventTitle": "原事件标题",
            "directive": "原事件指令。",
            "requestedTurnId": 8,
            "version": None,
        },
    }
    assert scratch.plot_pending_injection.desired is None
    assert invalid["errorCode"] == "invalid_arguments"


@pytest.mark.asyncio
async def test_plot_tools_reject_cross_story_or_invalid_pagination() -> None:
    scratch = _scratch()
    read = PlotSandboxReadTool(_snapshot(), scratch)
    mark = PlotEventMarkNextTool(_snapshot(), scratch)

    missing = json.loads(await mark.execute(event_id=999))
    bad_limit = json.loads(
        await read.execute(resource="event", limit=51)
    )

    assert missing["errorCode"] == "not_found"
    assert bad_limit["errorCode"] == "invalid_arguments"
