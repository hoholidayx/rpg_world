from __future__ import annotations

import pytest

from rpg_core.scene.tracker import SceneTracker
from rpg_core.tests.conftest import FakeStatusManager


def test_scene_tracker_loads_and_saves_status_table():
    mgr = FakeStatusManager(
        {
            "id": 42,
            "status_kind": "scene",
            "name": "当前场景",
            "headers": ["属性", "值"],
            "rows": [],
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
    assert "这是本轮回复前的场景快照" in context
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
            "rows": [],
        }
    )
    cloned = SceneTracker()
    cloned.bind_status_manager(mgr)
    assert cloned.load_from_status_table() is True
    cloned.set_time_state(source.get_time_state())

    assert cloned.set_time(hour=16)["时间"] == "第 3 年 6 月 15 日 16 时 30 分"


def test_scene_tracker_does_not_create_unmounted_scene():
    mgr = FakeStatusManager()
    tracker = SceneTracker()
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
    tracker = SceneTracker()
    tracker.bind_status_manager(mgr)
    assert tracker.load_from_status_table() is True

    with pytest.raises(ValueError):
        tracker.set_attr("溢出", "nope")

    before = tracker.attr_count
    tracker.delete_attr("额外1")
    assert tracker.attr_count == before - 1
