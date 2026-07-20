from __future__ import annotations

import json

import pytest

from rpg_core.session.catalog import SessionCatalogService
from rpg_data import models
from rpg_data.models import StatusRowRef
from rpg_data.repositories.records import CharacterRecord, SessionStatusTableRecord, StatusTableTemplateRecord
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways


@pytest.fixture(autouse=True)
def _reset_gateways(tmp_path, monkeypatch):
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path / "root_base"))
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def _workspace(tmp_path, name: str = "status_ws"):
    gateway = get_data_service_gateway(tmp_path / f"{name}.sqlite3")
    workspace_root = tmp_path / name
    WorkspaceRepository(gateway.database).create(
        name,
        f"Workspace {name}",
        str(workspace_root),
    )
    story = StoryRepository(gateway.database).create(name, "北境森林")
    return gateway, name, workspace_root, story


def _document(*rows: tuple[str, str], locked: set[str] | None = None) -> models.StatusTableDocument:
    locked = locked or set()
    return models.StatusTableDocument.from_rows(
        rows=[
            models.StatusTableRow(key, value, key in locked)
            for key, value in rows
        ],
        metadata={"ui": {}},
    )


def test_template_crud_uses_sql_document_source(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, _story = _workspace(tmp_path)
    service = gateway.status

    template = service.create_template(
        workspace_id,
        "装备",
        document=_document(("手部", "长剑")),
        description="角色装备",
        sort_order=20,
    )

    assert template.status_kind == models.STATUS_KIND_NORMAL
    assert template.headers == ("属性", "值")
    assert template.rows == (("手部", "长剑"),)

    StatusTableTemplateRecord.update(
        document_json=models.serialize_status_document(_document(("手部", "短剑")))
    ).where(StatusTableTemplateRecord.id == template.id).execute()

    reread = service.get_template(template.id)
    assert reread is not None
    assert reread.rows == (("手部", "短剑"),)

    renamed = service.update_template(template.id, name="背包", rows=[["金币", "7"]])

    assert renamed.name == "背包"
    assert renamed.rows == (("金币", "7"),)

    service.delete_template(template.id)
    assert service.get_template(template.id) is None


def test_template_create_does_not_materialize_status_file_dirs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    gateway = get_data_service_gateway(tmp_path / "relative.sqlite3")
    WorkspaceRepository(gateway.database).create(
        "relative_ws",
        "Relative Workspace",
        "relative_workspace",
    )
    StoryRepository(gateway.database).create("relative_ws", "北境森林")

    service = gateway.status
    service.create_template(
        "relative_ws",
        "旗帜",
        rows=[["封印", "完整"]],
    )

    assert not (tmp_path / "relative_workspace" / "template_status").exists()


def test_story_mount_controls_session_copy_visibility(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, forest_story = _workspace(tmp_path, "mount_ws")
    academy_story = StoryRepository(gateway.database).create(workspace_id, "学院旧梦")
    service = gateway.status

    template = service.create_template(
        workspace_id,
        "旗帜",
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, forest_story.id, template.id)

    forest_session = SessionCatalogService(gateway.sessions).create_session(workspace_id, forest_story.id, title="Forest")
    academy_session = SessionCatalogService(gateway.sessions).create_session(workspace_id, academy_story.id, title="Academy")

    assert forest_session is not None
    assert academy_session is not None
    assert [table.name for table in service.list_tables(str(forest_session.id))] == ["旗帜"]
    assert service.list_tables(str(academy_session.id)) == []

    session_table = service.get_table(str(forest_session.id), "旗帜")
    assert session_table.origin == models.STATUS_ORIGIN_TEMPLATE_COPY
    assert session_table.source_table_id == template.id
    assert session_table.workspace_id == workspace_id
    assert session_table.story_id == forest_story.id


def test_story_status_mount_character_binding_and_session_metadata(tmp_path, caplog) -> None:
    gateway, workspace_id, _workspace_root, forest_story = _workspace(tmp_path, "role_mount_ws")
    academy_story = StoryRepository(gateway.database).create(workspace_id, "学院旧梦")
    status = gateway.status
    characters = gateway.character_management

    alice = characters.create_character(workspace_id, name="Alice")
    bob = characters.create_character(workspace_id, name="Bob")
    outsider = characters.create_character(workspace_id, name="Outsider")
    assert alice is not None and bob is not None and outsider is not None
    alice_mount = characters.mount_character(workspace_id, forest_story.id, alice.id)
    bob_mount = characters.mount_character(workspace_id, forest_story.id, bob.id)
    outsider_mount = characters.mount_character(workspace_id, academy_story.id, outsider.id)
    assert alice_mount is not None and bob_mount is not None and outsider_mount is not None

    first_template = status.create_template(workspace_id, "Alice 状态", rows=[["心情", "平静"]])
    second_template = status.create_template(workspace_id, "Alice 装备", rows=[["手部", "长剑"]])
    first_mount = status.mount_template(
        workspace_id,
        forest_story.id,
        first_template.id,
        character_mount_id=alice_mount.mount.id,
    )
    second_mount = status.mount_template(
        workspace_id,
        forest_story.id,
        second_template.id,
        character_mount_id=alice_mount.mount.id,
    )

    assert first_mount.story_character_mount_id == alice_mount.mount.id
    assert second_mount.story_character_mount_id == alice_mount.mount.id

    rebound = status.update_story_mount_character(
        workspace_id,
        forest_story.id,
        first_mount.id,
        character_mount_id=bob_mount.mount.id,
    )
    assert rebound.story_character_mount_id == bob_mount.mount.id

    unbound = status.update_story_mount_character(
        workspace_id,
        forest_story.id,
        first_mount.id,
        character_mount_id=None,
    )
    assert unbound.story_character_mount_id is None

    with pytest.raises(FileNotFoundError):
        status.update_story_mount_character(
            workspace_id,
            forest_story.id,
            first_mount.id,
            character_mount_id=outsider_mount.mount.id,
        )

    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, forest_story.id, title="Role Metadata")
    assert session is not None
    copied = status.get_table(str(session.id), "Alice 装备")
    metadata = json.loads(copied.metadata_json)
    assert metadata["storyStatusMount"] == {
        "mountId": second_mount.id,
        "mountOrigin": models.STORY_STATUS_MOUNT_ORIGIN_SYSTEM,
        "characterMountId": alice_mount.mount.id,
        "characterId": alice.id,
        "characterName": "Alice",
    }

    del metadata["storyStatusMount"]["characterName"]
    SessionStatusTableRecord.update(
        metadata_json=json.dumps(metadata, ensure_ascii=False)
    ).where(SessionStatusTableRecord.id == copied.id).execute()

    with caplog.at_level("WARNING", logger="rpg_data.status"):
        context_table = next(
            table for table in status.list_context_tables(str(session.id))
            if table.id == copied.id
        )

    repaired_metadata = json.loads(context_table.metadata_json)
    assert repaired_metadata["storyStatusMount"]["characterName"] == "Alice"
    assert "backfilled missing status table character name" in caplog.text
    persisted = status.get_table_by_id(copied.id)
    assert json.loads(persisted.metadata_json)["storyStatusMount"]["characterName"] == "Alice"

    fallback_metadata = json.loads(persisted.metadata_json)
    fallback_metadata["storyStatusMount"]["characterName"] = None
    fallback_metadata["storyStatusMount"]["characterMountId"] = None
    SessionStatusTableRecord.update(
        metadata_json=json.dumps(fallback_metadata, ensure_ascii=False)
    ).where(SessionStatusTableRecord.id == copied.id).execute()
    caplog.clear()

    with caplog.at_level("WARNING", logger="rpg_data.status"):
        fallback_context_table = next(
            table for table in status.list_context_tables(str(session.id))
            if table.id == copied.id
        )

    fallback_repaired = json.loads(fallback_context_table.metadata_json)["storyStatusMount"]
    assert fallback_repaired["characterMountId"] == alice_mount.mount.id
    assert fallback_repaired["characterName"] == "Alice"
    assert "backfilled missing status table character name" in caplog.text

    fallback_repaired["characterName"] = None
    fallback_repaired["characterMountId"] = None
    SessionStatusTableRecord.update(
        metadata_json=json.dumps({"storyStatusMount": fallback_repaired}, ensure_ascii=False)
    ).where(SessionStatusTableRecord.id == copied.id).execute()
    status.update_story_mount_character(
        workspace_id,
        forest_story.id,
        second_mount.id,
        character_mount_id=bob_mount.mount.id,
    )
    caplog.clear()

    with caplog.at_level("WARNING", logger="rpg_data.status"):
        context_tables = status.list_context_tables(str(session.id))

    assert copied.id not in {table.id for table in context_tables}
    assert "excluded character-bound status table from context" in caplog.text


def test_unresolved_character_bound_table_is_excluded_from_context(tmp_path, caplog) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "unresolved_role_status_ws")
    status = gateway.status
    characters = gateway.character_management
    character = characters.create_character(workspace_id, name="Alice")
    assert character is not None
    character_mount = characters.mount_character(workspace_id, story.id, character.id)
    assert character_mount is not None
    template = status.create_template(workspace_id, "Alice 状态", rows=[["生命", "10"]])
    status.mount_template(
        workspace_id,
        story.id,
        template.id,
        character_mount_id=character_mount.mount.id,
    )
    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Unresolved Role")
    assert session is not None
    copied = status.get_table(str(session.id), "Alice 状态")
    metadata = json.loads(copied.metadata_json)
    metadata["storyStatusMount"]["characterName"] = None
    metadata["storyStatusMount"]["characterMountId"] = 999999
    metadata["storyStatusMount"]["mountId"] = 999999
    SessionStatusTableRecord.update(
        metadata_json=json.dumps(metadata, ensure_ascii=False)
    ).where(SessionStatusTableRecord.id == copied.id).execute()

    with caplog.at_level("WARNING", logger="rpg_data.status"):
        context_tables = status.list_context_tables(str(session.id))

    assert copied.id not in {table.id for table in context_tables}
    assert "excluded character-bound status table from context" in caplog.text


def test_status_character_binding_requires_non_empty_character_name(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "empty_role_name_ws")
    status = gateway.status
    characters = gateway.character_management
    character = characters.create_character(workspace_id, name="Alice")
    assert character is not None
    character_mount = characters.mount_character(workspace_id, story.id, character.id)
    assert character_mount is not None
    template = status.create_template(workspace_id, "角色状态", rows=[["生命", "10"]])

    CharacterRecord.update(name="").where(CharacterRecord.id == character.id).execute()
    with pytest.raises(ValueError, match="non-empty character name"):
        status.mount_template(
            workspace_id,
            story.id,
            template.id,
            character_mount_id=character_mount.mount.id,
        )


def test_session_creation_rejects_bound_character_that_lost_name(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "lost_role_name_ws")
    status = gateway.status
    characters = gateway.character_management
    character = characters.create_character(workspace_id, name="Alice")
    assert character is not None
    character_mount = characters.mount_character(workspace_id, story.id, character.id)
    assert character_mount is not None
    template = status.create_template(workspace_id, "角色状态", rows=[["生命", "10"]])
    status.mount_template(
        workspace_id,
        story.id,
        template.id,
        character_mount_id=character_mount.mount.id,
    )

    CharacterRecord.update(name="").where(CharacterRecord.id == character.id).execute()
    with pytest.raises(ValueError, match="non-empty character name"):
        SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Should Roll Back")
    assert all(session.title != "Should Roll Back" for session in gateway.catalog.list_sessions(workspace_id, story.id))


def test_story_owned_status_template_can_be_deleted_by_mount(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "story_owned_ws")
    characters = gateway.character_management
    status = gateway.status

    character = characters.create_character(workspace_id, name="Keeper")
    assert character is not None
    character_mount = characters.mount_character(workspace_id, story.id, character.id)
    assert character_mount is not None

    owned_mount = status.create_story_template(
        workspace_id,
        story.id,
        "Keeper 状态",
        character_mount_id=character_mount.mount.id,
        rows=[["姿态", "警戒"]],
    )
    assert owned_mount.mount_origin == models.STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE
    assert owned_mount.story_character_mount_id == character_mount.mount.id
    assert status.get_template(owned_mount.status_table_id) is not None

    status.delete_story_template_mount(workspace_id, story.id, owned_mount.id)
    assert status.get_template(owned_mount.status_table_id) is None

    system_template = status.create_template(workspace_id, "系统模板", rows=[["旗帜", "亮起"]])
    system_mount = status.mount_template(workspace_id, story.id, system_template.id)
    with pytest.raises(ValueError):
        status.delete_story_template_mount(workspace_id, story.id, system_mount.id)
    assert status.get_template(system_template.id) is not None


def test_session_copy_is_independent_from_template_and_other_sessions(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "copy_ws")
    service = gateway.status

    template = service.create_template(
        workspace_id,
        "旗帜",
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, story.id, template.id)

    first = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="First")
    assert first is not None

    service.update_template(template.id, rows=[["封印", "破裂"]])
    second = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Second")
    assert second is not None

    first_table = service.get_table(str(first.id), "旗帜")
    second_table = service.get_table(str(second.id), "旗帜")
    assert first_table.rows == (("封印", "完整"),)
    assert second_table.rows == (("封印", "破裂"),)

    service.save_table(first_table.id, _document(("封印", "已修复")))

    assert service.get_table_by_id(first_table.id).rows == (("封印", "已修复"),)
    assert service.get_table_by_id(second_table.id).rows == (("封印", "破裂"),)


def test_session_scoped_save_warns_and_keeps_last_write(tmp_path, caplog) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "scoped_save_ws")
    service = gateway.status
    template = service.create_template(workspace_id, "旗帜", rows=[["封印", "完整"]])
    service.mount_template(workspace_id, story.id, template.id)
    first = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="First")
    second = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Second")
    assert first is not None and second is not None

    table = service.get_table(str(first.id), "旗帜")
    base_document = table.document
    service.save_table(table.id, _document(("封印", "破裂")))

    with caplog.at_level("WARNING", logger="rpg_data.status"):
        saved = service.save_table_for_session(
            str(first.id),
            table.id,
            _document(("封印", "已修复")),
            expected_status_kind=models.STATUS_KIND_NORMAL,
            base_document=base_document,
            write_source="agent_turn",
        )

    assert saved.rows == (("封印", "已修复"),)
    assert "last-write-wins" in caplog.text

    with pytest.raises(FileNotFoundError, match="unavailable"):
        service.get_table_for_session(str(second.id), table.id)
    with pytest.raises(FileNotFoundError, match="unavailable"):
        service.save_table_for_session(
            str(second.id),
            table.id,
            _document(("封印", "越权")),
            expected_status_kind=models.STATUS_KIND_NORMAL,
        )
    with pytest.raises(ValueError, match="kind changed"):
        service.save_table_for_session(
            str(first.id),
            table.id,
            _document(("封印", "错误类型")),
            expected_status_kind=models.STATUS_KIND_SCENE,
        )


def test_table_id_selector_writes_are_visible_from_document(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "selector_ws")
    service = gateway.status

    template = service.create_template(
        workspace_id,
        "旗帜",
        headers=["名称", "值"],
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, story.id, template.id)
    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Selector")
    assert session is not None

    table = service.get_table(str(session.id), "旗帜")
    service.set_cell(table.id, StatusRowRef.match("名称", "封印"), "值", "破裂")
    service.append_row(table.id, ["钟声", "响起", "ignored"])
    service.replace_row(table.id, StatusRowRef.match("名称", "钟声"), ["钟声", "静默"])
    updated = service.delete_row(table.id, StatusRowRef.match("名称", "封印"))

    assert updated.document.key_column == "名称"
    assert updated.document.value_column == "值"
    assert updated.rows == (("钟声", "静默"),)
    assert updated.document.rows[0].runtime_key_locked is False

    updated = service.set_key_value(table.id, "钟声", "彻底静默")
    assert updated.rows == (("钟声", "彻底静默"),)
    updated = service.delete_key_value(table.id, "钟声")
    assert updated.rows == ()


def test_key_value_write_updates_appends_and_rejects_duplicates(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "key_ws")
    service = gateway.status

    template = service.create_template(
        workspace_id,
        "当前场景",
        status_kind=models.STATUS_KIND_SCENE,
        rows=[["位置", "森林"]],
    )
    service.mount_template(workspace_id, story.id, template.id)
    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Key")
    assert session is not None

    table = service.get_active_scene_table(str(session.id))
    assert table is not None
    assert service.set_key_value(table.id, "位置", "城堡").rows == (("位置", "城堡"),)
    assert service.set_key_value(table.id, "天气", "雨").rows == (("位置", "城堡"), ("天气", "雨"))
    assert service.delete_key_value(table.id, "位置").rows == (("天气", "雨"),)

    with pytest.raises(ValueError):
        service.append_row(table.id, ["天气", "雾"])


def test_scene_is_story_mounted_and_active_scene_uses_first_sorted_table(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "scene_ws")
    service = gateway.status

    later_scene = service.create_template(
        workspace_id,
        "备用场景",
        status_kind=models.STATUS_KIND_SCENE,
        rows=[["位置", "营地"]],
    )
    active_scene = service.create_template(
        workspace_id,
        "当前场景",
        status_kind=models.STATUS_KIND_SCENE,
        rows=[["时间", "第 1 年 1 月 1 日 6 时"], ["位置", "森林"]],
    )
    normal = service.create_template(
        workspace_id,
        "世界旗帜",
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, story.id, later_scene.id, sort_order=20)
    service.mount_template(workspace_id, story.id, active_scene.id, sort_order=10)
    service.mount_template(workspace_id, story.id, normal.id, sort_order=30)

    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Scene")
    assert session is not None
    session_id = str(session.id)

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


def test_runtime_key_lock_allows_value_update_but_blocks_runtime_delete(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "runtime_lock_ws")
    service = gateway.status

    template = service.create_template(
        workspace_id,
        "当前场景",
        status_kind=models.STATUS_KIND_SCENE,
        rows=[["位置", "森林"], ["天气", "雨"]],
    )
    service.mount_template(workspace_id, story.id, template.id)
    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Runtime Lock")
    assert session is not None

    table = service.get_active_scene_table(str(session.id))
    assert table is not None

    assert table.document.row_for_key("位置").runtime_key_locked is True
    assert table.document.row_for_key("天气").runtime_key_locked is False
    assert service.runtime_set_key_value(table.id, "位置", "城堡").rows[0] == ("位置", "城堡")
    with pytest.raises(PermissionError):
        service.runtime_delete_key_value(table.id, "位置")
    assert "位置" in service.get_scene_attrs(str(session.id))

    service.runtime_delete_key_value(table.id, "天气")
    assert "天气" not in service.get_scene_attrs(str(session.id))

    service.delete_key_value(table.id, "位置")
    assert "位置" not in service.get_scene_attrs(str(session.id))


def test_session_native_table_crud(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "native_ws")
    service = gateway.status
    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Native")
    assert session is not None

    table = service.create_table(str(session.id), "临时状态", rows=[["钟声", "响起"]])
    assert table.origin == models.STATUS_ORIGIN_SESSION_NATIVE
    assert table.source_table_id is None
    assert service.get_table_by_id(table.id).rows == (("钟声", "响起"),)

    renamed = service.rename_table(table.id, "运行时状态")
    assert renamed.name == "运行时状态"
    service.delete_table(table.id)
    with pytest.raises(FileNotFoundError):
        service.get_table_by_id(table.id)


def test_deferred_update_and_progress_commit_atomically(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "deferred_ws")
    service = gateway.status
    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Deferred")
    assert session is not None
    document = models.StatusTableDocument.from_rows(rows=[
        models.StatusTableRow(
            "长期信任",
            "低",
            update_frequency=models.STATUS_UPDATE_FREQUENCY_DEFERRED,
            deferred_interval_turns=2,
        )
    ])
    table = service.create_table(str(session.id), "人物关系", document=document)
    updated = document.with_existing_values([("长期信任", "中")])

    service.commit_deferred_update(
        str(session.id),
        table.id,
        updated,
        processed_keys=["长期信任"],
        last_processed_turn_id=4,
        base_document=document,
    )

    assert service.get_table_by_id(table.id).document.rows[0].value == "中"
    assert service.list_deferred_progress(str(session.id))[0].last_processed_turn_id == 4
    assert service.clamp_deferred_progress(str(session.id), 2) == 1
    assert service.list_deferred_progress(str(session.id))[0].last_processed_turn_id == 2
    assert service.clamp_deferred_progress(str(session.id), 9) == 0

    with pytest.raises(PermissionError, match="not deferred"):
        service.commit_deferred_update(
            str(session.id),
            table.id,
            models.StatusTableDocument.from_rows(rows=[
                models.StatusTableRow("长期信任", "高")
            ]),
            processed_keys=["长期信任"],
            last_processed_turn_id=5,
        )
    assert service.list_deferred_progress(str(session.id))[0].last_processed_turn_id == 2


def test_bootstrap_state_commits_documents_and_all_deferred_progress_atomically(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "bootstrap_ws")
    service = gateway.status
    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Bootstrap")
    assert session is not None
    base = models.StatusTableDocument.from_rows(rows=[
        models.StatusTableRow("生命", "10"),
        models.StatusTableRow(
            "长期信任",
            "低",
            update_frequency=models.STATUS_UPDATE_FREQUENCY_DEFERRED,
        ),
    ])
    table = service.create_table(str(session.id), "角色状态", document=base)
    updated = base.with_existing_values([("生命", "8"), ("长期信任", "中")])

    service.commit_bootstrap_state(
        str(session.id),
        [models.StatusBootstrapDocument(
            table_id=table.id,
            status_kind=models.STATUS_KIND_NORMAL,
            document=updated,
            base_document=base,
        )],
        deferred_progress={table.id: ("长期信任",)},
        boundary_turn_id=12,
    )

    assert service.get_table_by_id(table.id).document == updated
    assert service.list_deferred_progress(str(session.id)) == [
        models.StatusDeferredProgress(table.id, "长期信任", 12)
    ]

    with pytest.raises(PermissionError, match="not deferred"):
        service.commit_bootstrap_state(
            str(session.id),
            [models.StatusBootstrapDocument(
                table_id=table.id,
                status_kind=models.STATUS_KIND_NORMAL,
                document=base,
                base_document=updated,
            )],
            deferred_progress={table.id: ("生命",)},
            boundary_turn_id=13,
        )
    assert service.get_table_by_id(table.id).document == updated
    assert service.list_deferred_progress(str(session.id))[0].last_processed_turn_id == 12


def test_scene_not_mounted_is_not_visible_to_session(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "no_scene_ws")
    service = gateway.status

    service.create_template(
        workspace_id,
        "当前场景",
        status_kind=models.STATUS_KIND_SCENE,
        rows=[["位置", "森林"]],
    )

    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="No Scene")
    assert session is not None

    assert service.get_active_scene_table(str(session.id)) is None
    assert service.get_scene_attrs(str(session.id)) is None


def test_catalog_status_timing_works_when_catalog_is_accessed_first(tmp_path) -> None:
    gateway, workspace_id, _workspace_root, story = _workspace(tmp_path, "timing_ws")
    catalog = gateway.catalog
    service = gateway.status

    template = service.create_template(
        workspace_id,
        "旗帜",
        rows=[["封印", "完整"]],
    )
    service.mount_template(workspace_id, story.id, template.id)

    session = SessionCatalogService(gateway.sessions).create_session(workspace_id, story.id, title="Timing")

    assert session is not None
    assert service.get_table(str(session.id), "旗帜").rows == (("封印", "完整"),)
