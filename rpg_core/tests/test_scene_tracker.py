from __future__ import annotations

import pytest

from rpg_core.scene.tracker import SceneTracker
from rpg_core.tests.conftest import FakeStatusManager


def test_scene_tracker_loads_and_saves_status_table():
    mgr = FakeStatusManager()
    tracker = SceneTracker()
    tracker.bind_status_manager(mgr)

    loaded = tracker.load_from_status_table()
    assert loaded is False
    assert tracker.get_context().startswith("[scene]")
    assert "时间:" in tracker.get_context()
    assert "当前场景" in mgr.tables["全局状态"]

    tracker.set_attr("位置", "城堡")
    assert mgr.tables["全局状态"]["当前场景"]["rows"][1] == ["位置", "城堡"]


def test_scene_tracker_existing_table_round_trip():
    mgr = FakeStatusManager(
        {
            "全局状态": {
                "当前场景": {
                    "name": "当前场景",
                    "headers": ["属性", "值"],
                    "rows": [["时间", "第 9 年 8 月 7 日 12 时"], ["位置", "大厅"]],
                }
            }
        }
    )
    tracker = SceneTracker()
    tracker.bind_status_manager(mgr)

    assert tracker.load_from_status_table() is True
    context = tracker.get_context()
    assert "第 9 年 8 月 7 日 12 时" in context
    assert "大厅" in context


def test_scene_tracker_attr_limit_and_protected_delete():
    tracker = SceneTracker()
    for idx in range(1, tracker.MAX_ATTRS - len(tracker.DEFAULT_ATTRS) + 1):
        tracker.set_attr(f"额外{idx}", str(idx))

    with pytest.raises(ValueError):
        tracker.set_attr("溢出", "nope")

    before = tracker.attr_count
    tracker.delete_attr("时间")
    assert tracker.attr_count == before
