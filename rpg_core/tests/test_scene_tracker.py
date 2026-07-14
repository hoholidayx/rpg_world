from __future__ import annotations

import pytest

from rpg_core.scene.tools import DeleteAttrTool, SetAttrTool, SetTimeTool
from rpg_core.scene.tracker import SceneTracker
from rpg_core.tests.conftest import FakeStatusManager


def test_scene_tracker_loads_and_saves_status_table():
    mgr = FakeStatusManager(
        {
            "id": 42,
            "status_kind": "scene",
            "name": "当前场景",
            "headers": ["属性", "值"],
            "rows": [["位置", ""]],
        }
    )
    tracker = SceneTracker()
    tracker.bind_status_manager(mgr)

    loaded = tracker.load_from_status_table()
    assert loaded is True
    assert tracker.get_context().startswith("[scene]")
    assert "时间:" not in tracker.get_context()

    tracker.set_attr("位置", "城堡")
    assert ["位置", "城堡"] in mgr.scene_table["rows"]
    assert ("set", 42, "位置", "城堡") in mgr.calls


def test_scene_tracker_existing_table_round_trip():
    mgr = FakeStatusManager(
        {
            "id": 7,
            "status_kind": "scene",
            "name": "当前场景",
            "headers": ["属性", "值"],
            "rows": [["时间", "第 9 年 8 月 7 日 12 时"], ["位置", "大厅"]],
        }
    )
    tracker = SceneTracker()
    tracker.bind_status_manager(mgr)

    assert tracker.load_from_status_table() is True
    context = tracker.get_context()
    assert "第 9 年 8 月 7 日 12 时" in context
    assert "大厅" in context
    assert "scene 数据可能不准确" in context
    assert "遵循核心状态同步协议" in context
    assert "StatusSubAgent" not in context
    assert "scene_time" not in context
    assert "no-op" not in context


def test_scene_tracker_exports_and_restores_time_state():
    source = SceneTracker()
    source.set_time(year=3, month=6, day=15, hour=14, minute=30)

    mgr = FakeStatusManager(
        {
            "id": 8,
            "status_kind": "scene",
            "name": "当前场景",
            "headers": ["属性", "值"],
            "rows": [["时间", "第 1 年 1 月 1 日 6 时"]],
        }
    )
    cloned = SceneTracker()
    cloned.bind_status_manager(mgr)
    assert cloned.load_from_status_table() is True
    cloned.set_time_state(source.get_time_state())

    assert cloned.set_time(hour=16)["时间"] == "第 3 年 6 月 15 日 16 时 30 分"


def test_scene_tracker_does_not_create_unmounted_scene():
    mgr = FakeStatusManager()
    tracker = SceneTracker(allow_runtime_key_changes=True)
    tracker.bind_status_manager(mgr)

    assert tracker.load_from_status_table() is False
    tracker.set_attr("位置", "城堡")

    assert mgr.scene_table is None
    assert mgr.calls == []


def test_scene_tracker_attr_limit_and_runtime_delete():
    mgr = FakeStatusManager(
        {
            "id": 9,
            "status_kind": "scene",
            "name": "当前场景",
            "headers": ["属性", "值"],
            "rows": [[f"额外{idx}", str(idx)] for idx in range(1, SceneTracker.MAX_ATTRS + 1)],
        }
    )
    tracker = SceneTracker(allow_runtime_key_changes=True)
    tracker.bind_status_manager(mgr)
    assert tracker.load_from_status_table() is True

    with pytest.raises(ValueError):
        tracker.set_attr("溢出", "nope")

    before = tracker.attr_count
    tracker.delete_attr("额外1")
    assert tracker.attr_count == before - 1


@pytest.mark.asyncio
async def test_scene_tracker_default_policy_is_existing_value_only():
    mgr = FakeStatusManager(
        {
            "id": 10,
            "status_kind": "scene",
            "name": "当前场景",
            "headers": ["属性", "值"],
            "rows": [
                ["时间", "第 1 年 1 月 1 日 6 时"],
                ["位置", "大厅"],
                ["天气", "晴"],
            ],
        }
    )
    tracker = SceneTracker()
    tracker.bind_status_manager(mgr)
    assert tracker.load_from_status_table() is True

    tools = tracker.get_tools()
    assert [tool.name for tool in tools] == ["scene_time", "scene_attr"]
    attr_tool = next(tool for tool in tools if isinstance(tool, SetAttrTool))
    assert attr_tool.parameters()["properties"]["key"]["enum"] == [
        "时间",
        "位置",
        "天气",
    ]

    assert await attr_tool.execute(key="位置", value="城堡") == "场景属性已设置：位置 = 城堡"
    assert mgr.get_scene_attrs()["位置"] == "城堡"
    assert ("set", 10, "位置", "城堡") in mgr.calls

    assert (await attr_tool.execute(key="氛围", value="紧张")).startswith("设置失败：")
    assert (await DeleteAttrTool(tracker).execute(key="天气")).startswith("设置失败：")
    assert "氛围" not in mgr.get_scene_attrs()
    assert "天气" in mgr.get_scene_attrs()


@pytest.mark.asyncio
async def test_scene_tracker_default_policy_never_creates_time_or_empty_scene_keys():
    mgr = FakeStatusManager(
        {
            "id": 11,
            "status_kind": "scene",
            "name": "当前场景",
            "headers": ["属性", "值"],
            "rows": [["位置", "森林"]],
        }
    )
    tracker = SceneTracker()
    tracker.bind_status_manager(mgr)
    assert tracker.load_from_status_table() is True

    assert [tool.name for tool in tracker.get_tools()] == ["scene_attr"]
    before_time_state = tracker.get_time_state()
    result = await SetTimeTool(tracker).execute(hour=9)
    assert result.startswith("设置失败：")
    assert tracker.get_time_state() == before_time_state
    assert "时间" not in mgr.get_scene_attrs()

    mgr.scene_table["rows"] = []
    assert tracker.get_tools() == []


def test_scene_tracker_opt_in_preserves_structural_tools_and_limit():
    mgr = FakeStatusManager(
        {
            "id": 12,
            "status_kind": "scene",
            "name": "当前场景",
            "headers": ["属性", "值"],
            "rows": [],
        }
    )
    tracker = SceneTracker(allow_runtime_key_changes=True)
    tracker.bind_status_manager(mgr)
    assert tracker.load_from_status_table() is True

    assert [tool.name for tool in tracker.get_tools()] == [
        "scene_time",
        "scene_attr",
        "scene_del_attr",
    ]
    tracker.set_attr("天气", "雨")
    assert mgr.get_scene_attrs()["天气"] == "雨"
    tracker.delete_attr("天气")
    assert "天气" not in mgr.get_scene_attrs()
