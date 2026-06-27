from __future__ import annotations

import csv
from pathlib import Path

import pytest

from rpg_data.models import StatusRowRef
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways


@pytest.fixture(autouse=True)
def _reset_gateways():
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(rows)


def _workspace(
    tmp_path: Path,
    name: str = "status_ws",
) -> tuple[object, str, Path, object]:
    gateway = get_data_service_gateway(tmp_path / f"{name}.sqlite3")
    workspace_root = tmp_path / name
    WorkspaceRepository(gateway.database).create(
        name,
        f"Workspace {name}",
        str(workspace_root),
    )
    story = StoryRepository(gateway.database).create(name, "北境森林")
    return gateway, name, workspace_root, story


def test_template_crud_uses_csv_as_source_of_truth(tmp_path: Path) -> None:
    gateway, workspace_id, workspace_root, _story = _workspace(tmp_path)
    service = gateway.status

    service.create_type(workspace_id, "角色状态", sort_order=20)
    template = service.create_template(
        workspace_id,
        "角色状态",
        "装备",
        headers=["部位", "物品"],
        rows=[["手部", "长剑"]],
    )

    template_path = workspace_root / template.relative_path
    assert template.relative_path == "template_status/角色状态/装备.csv"
    assert template_path.is_file()
    assert template.headers == ("部位", "物品")
    assert template.rows == (("手部", "长剑"),)

    _write_csv(template_path, ["部位", "物品", "状态"], [["手部", "短剑", "破损"]])
    reread = service.get_template(template.id)

    assert reread is not None
    assert reread.headers == ("部位", "物品", "状态")
    assert reread.rows == (("手部", "短剑", "破损"),)

    renamed = service.update_template(template.id, name="背包")

    assert renamed.relative_path == "template_status/角色状态/背包.csv"
    assert not template_path.exists()
    assert (workspace_root / renamed.relative_path).is_file()

    service.delete_template(template.id)

    assert service.get_template(template.id) is None
    assert not (workspace_root / renamed.relative_path).exists()


def test_relative_workspace_root_uses_configured_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    gateway = get_data_service_gateway(tmp_path / "relative.sqlite3")
    WorkspaceRepository(gateway.database).create(
        "relative_ws",
        "Relative Workspace",
        "relative_workspace",
    )
    StoryRepository(gateway.database).create("relative_ws", "北境森林")

    service = gateway.status
    service.create_type("relative_ws", "世界状态")
    template = service.create_template(
        "relative_ws",
        "世界状态",
        "旗帜",
        headers=["名称", "值"],
        rows=[["封印", "完整"]],
    )

    assert (tmp_path / "relative_workspace" / template.relative_path).is_file()


def test_story_mount_controls_session_copy_visibility(tmp_path: Path) -> None:
    gateway, workspace_id, workspace_root, forest_story = _workspace(tmp_path, "mount_ws")
    academy_story = StoryRepository(gateway.database).create(workspace_id, "学院旧梦")
    service = gateway.status

    service.create_type(workspace_id, "世界状态")
    template = service.create_template(
        workspace_id,
        "世界状态",
        "旗帜",
        headers=["名称", "值"],
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, forest_story.id, template.id)

    forest_session = gateway.catalog.create_session(workspace_id, forest_story.id, title="Forest")
    academy_session = gateway.catalog.create_session(workspace_id, academy_story.id, title="Academy")

    assert forest_session is not None
    assert academy_session is not None
    assert [table.name for table in service.list_tables(str(forest_session["id"]))] == ["旗帜"]
    assert service.list_tables(str(academy_session["id"])) == []

    session_table = service.get_table(str(forest_session["id"]), "世界状态", "旗帜")
    assert session_table.relative_path == f"stories/{forest_story.id}/{forest_session['id']}/status/世界状态/旗帜.csv"
    assert (workspace_root / session_table.relative_path).is_file()


def test_session_copy_is_independent_from_template_and_other_sessions(tmp_path: Path) -> None:
    gateway, workspace_id, workspace_root, story = _workspace(tmp_path, "copy_ws")
    service = gateway.status

    service.create_type(workspace_id, "世界状态")
    template = service.create_template(
        workspace_id,
        "世界状态",
        "旗帜",
        headers=["名称", "值"],
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, story.id, template.id)

    first = gateway.catalog.create_session(workspace_id, story.id, title="First")
    assert first is not None

    _write_csv(
        workspace_root / template.relative_path,
        ["名称", "值"],
        [["封印", "破裂"]],
    )

    second = gateway.catalog.create_session(workspace_id, story.id, title="Second")
    assert second is not None

    assert service.get_table(str(first["id"]), "世界状态", "旗帜").rows == (("封印", "完整"),)
    assert service.get_table(str(second["id"]), "世界状态", "旗帜").rows == (("封印", "破裂"),)

    service.save_table(
        str(first["id"]),
        "世界状态",
        "旗帜",
        ["名称", "值"],
        [["封印", "已修复"]],
    )

    assert service.get_table(str(first["id"]), "世界状态", "旗帜").rows == (("封印", "已修复"),)
    assert service.get_table(str(second["id"]), "世界状态", "旗帜").rows == (("封印", "破裂"),)


def test_table_id_selector_writes_are_visible_from_csv(tmp_path: Path) -> None:
    gateway, workspace_id, workspace_root, story = _workspace(tmp_path, "selector_ws")
    service = gateway.status

    service.create_type(workspace_id, "世界状态")
    template = service.create_template(
        workspace_id,
        "世界状态",
        "旗帜",
        headers=["名称", "值"],
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, story.id, template.id)
    session = gateway.catalog.create_session(workspace_id, story.id, title="Selector")
    assert session is not None

    table = service.get_table(str(session["id"]), "世界状态", "旗帜")
    service.set_cell(table.id, StatusRowRef.match("名称", "封印"), "值", "破裂")
    service.append_row(table.id, ["钟声", "响起", "ignored"])
    service.replace_row(table.id, StatusRowRef.match("名称", "钟声"), ["钟声", "静默"])
    updated = service.delete_row(table.id, StatusRowRef.match("名称", "封印"))

    assert updated.rows == (("钟声", "静默"),)
    with (workspace_root / table.relative_path).open("r", encoding="utf-8-sig", newline="") as fh:
        assert list(csv.reader(fh)) == [["名称", "值"], ["钟声", "静默"]]


def test_key_value_write_updates_appends_and_rejects_duplicates(tmp_path: Path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "key_ws")
    service = gateway.status

    service.create_type(workspace_id, "场景状态", builtin_key="scene")
    template = service.create_template(
        workspace_id,
        "场景状态",
        "当前场景",
        headers=["属性", "值"],
        rows=[["位置", "森林"]],
    )
    service.mount_template(workspace_id, story.id, template.id)
    session = gateway.catalog.create_session(workspace_id, story.id, title="Key")
    assert session is not None

    table = service.get_active_scene_table(str(session["id"]))
    assert table is not None
    assert service.set_key_value(table.id, "位置", "城堡").rows == (("位置", "城堡"),)
    assert service.set_key_value(table.id, "天气", "雨").rows == (("位置", "城堡"), ("天气", "雨"))
    assert service.delete_key_value(table.id, "位置").rows == (("天气", "雨"),)

    service.append_row(table.id, ["天气", "雾"])
    with pytest.raises(ValueError):
        service.set_key_value(table.id, "天气", "晴")


def test_scene_is_story_mounted_and_active_scene_uses_first_sorted_table(tmp_path: Path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "scene_ws")
    service = gateway.status

    service.create_type(workspace_id, "场景状态", builtin_key="scene")
    later_scene = service.create_template(
        workspace_id,
        "场景状态",
        "备用场景",
        headers=["属性", "值"],
        rows=[["位置", "营地"]],
    )
    active_scene = service.create_template(
        workspace_id,
        "场景状态",
        "当前场景",
        headers=["属性", "值"],
        rows=[["时间", "第 1 年 1 月 1 日 6 时"], ["位置", "森林"]],
    )
    service.create_type(workspace_id, "普通状态")
    normal = service.create_template(
        workspace_id,
        "普通状态",
        "世界旗帜",
        headers=["名称", "值"],
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, story.id, later_scene.id, sort_order=20)
    service.mount_template(workspace_id, story.id, active_scene.id, sort_order=10)
    service.mount_template(workspace_id, story.id, normal.id, sort_order=30)

    session = gateway.catalog.create_session(workspace_id, story.id, title="Scene")
    assert session is not None
    session_id = str(session["id"])

    assert service.get_active_scene_table(session_id).name == "当前场景"
    assert service.get_scene_attrs(session_id) == {
        "时间": "第 1 年 1 月 1 日 6 时",
        "位置": "森林",
    }

    service.set_scene_attr(session_id, "天气", "雨")
    assert service.get_scene_attrs(session_id)["天气"] == "雨"

    service.delete_scene_attr(session_id, "时间")
    assert "时间" in service.get_scene_attrs(session_id)

    assert [table.name for table in service.list_context_tables(session_id)] == ["世界旗帜"]


def test_scene_not_mounted_is_not_visible_to_session(tmp_path: Path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "no_scene_ws")
    service = gateway.status

    service.create_type(workspace_id, "场景状态", builtin_key="scene")
    service.create_template(
        workspace_id,
        "场景状态",
        "当前场景",
        headers=["属性", "值"],
        rows=[["位置", "森林"]],
    )

    session = gateway.catalog.create_session(workspace_id, story.id, title="No Scene")
    assert session is not None

    assert service.get_active_scene_table(str(session["id"])) is None
    assert service.get_scene_attrs(str(session["id"])) is None


def test_catalog_status_timing_works_when_catalog_is_accessed_first(tmp_path: Path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "timing_ws")
    catalog = gateway.catalog
    service = gateway.status

    service.create_type(workspace_id, "世界状态")
    template = service.create_template(
        workspace_id,
        "世界状态",
        "旗帜",
        headers=["名称", "值"],
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, story.id, template.id)

    session = catalog.create_session(workspace_id, story.id, title="Timing")

    assert session is not None
    assert service.get_table(str(session["id"]), "世界状态", "旗帜").rows == (("封印", "完整"),)


def test_clear_unindexed_session_files_only_removes_orphan_csv(tmp_path: Path) -> None:
    gateway, workspace_id, workspace_root, story = _workspace(tmp_path, "cleanup_ws")
    service = gateway.status

    service.create_type(workspace_id, "世界状态")
    template = service.create_template(
        workspace_id,
        "世界状态",
        "旗帜",
        headers=["名称", "值"],
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, story.id, template.id)
    session = gateway.catalog.create_session(workspace_id, story.id, title="Cleanup")
    assert session is not None
    session_id = str(session["id"])

    indexed_table = service.get_table(session_id, "世界状态", "旗帜")
    indexed_path = workspace_root / indexed_table.relative_path
    orphan_path = indexed_path.with_name("孤儿.csv")
    orphan_nested_path = indexed_path.parent.parent / "临时状态" / "临时.csv"
    non_csv_path = indexed_path.with_name("notes.txt")
    _write_csv(orphan_path, ["名称"], [["孤儿"]])
    _write_csv(orphan_nested_path, ["名称"], [["临时"]])
    non_csv_path.write_text("keep me", encoding="utf-8")

    removed = service.clear_unindexed_session_files(session_id)

    assert removed == [
        f"stories/{story.id}/{session_id}/status/世界状态/孤儿.csv",
        f"stories/{story.id}/{session_id}/status/临时状态/临时.csv",
    ]
    assert indexed_path.is_file()
    assert non_csv_path.is_file()
    assert not orphan_path.exists()
    assert not orphan_nested_path.exists()
    assert service.get_table(session_id, "世界状态", "旗帜").rows == (("封印", "完整"),)
