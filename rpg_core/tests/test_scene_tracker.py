from __future__ import annotations

import pytest

from rpg_core.scene.tracker import SceneTracker
from rpg_core.tests.conftest import FakeStatusManager


def test_scene_tracker_loads_and_saves_status_table():
    mgr = FakeStatusManager(
        {
            "id": 42,
            "type_name": "场景状态",
            "name": "当前场景",
            "headers": ["属性", "值"],
            "rows": [],
        }
    )
    tracker = SceneTracker()
    tracker.bind_status_manager(mgr)

    loaded = tracker.load_from_status_table()
    assert loaded is False
    assert tracker.get_context().startswith("[scene]")
    assert "时间:" in tracker.get_context()
    assert ("set", 42, "时间", "第 1 年 1 月 1 日 6 时") in mgr.calls

    tracker.set_attr("位置", "城堡")
    assert ["位置", "城堡"] in mgr.scene_table["rows"]
    assert ("set", 42, "位置", "城堡") in mgr.calls


def test_scene_tracker_existing_table_round_trip():
    mgr = FakeStatusManager(
        {
            "id": 7,
            "type_name": "场景状态",
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


def test_scene_tracker_does_not_create_unmounted_scene():
    mgr = FakeStatusManager()
    tracker = SceneTracker()
    tracker.bind_status_manager(mgr)

    assert tracker.load_from_status_table() is False
    tracker.set_attr("位置", "城堡")

    assert mgr.scene_table is None
    assert mgr.calls == []


def test_scene_tracker_attr_limit_and_protected_delete():
    tracker = SceneTracker()
    for idx in range(1, tracker.MAX_ATTRS - len(tracker.DEFAULT_ATTRS) + 1):
        tracker.set_attr(f"额外{idx}", str(idx))

    with pytest.raises(ValueError):
        tracker.set_attr("溢出", "nope")

    before = tracker.attr_count
    tracker.delete_attr("时间")
    assert tracker.attr_count == before
