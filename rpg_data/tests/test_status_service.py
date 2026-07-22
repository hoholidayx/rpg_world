from __future__ import annotations

import json

import pytest

from rpg_core.scene.status import SceneStatusService
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.status import SessionStatusLifecycleService
from rpg_core.status.administration import StatusTableAdministrationService
from rpg_core.status.context_service import StatusContextService
from rpg_core.status.manager import StatusManager
from rpg_data import models
from rpg_data.repositories.records import StoryCharacterRecord, StoryStatusTableRecord
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


def _document(
    *rows: tuple[str, str],
    locked: set[str] | None = None,
) -> models.StatusTableDocument:
    locked = locked or set()
    return models.StatusTableDocument.from_rows(
        rows=[
            models.StatusTableRow(key, value, key in locked)
            for key, value in rows
        ],
        metadata={"ui": {}},
    )


def test_story_status_crud_uses_sql_document_source(tmp_path) -> None:
    gateway, workspace_id, _root, story = _workspace(tmp_path)
    service = gateway.status
    table = service.create_story_table(
        workspace_id,
        story.id,
        "装备",
        document=_document(("手部", "长剑")),
        description="角色装备",
        sort_order=20,
    )
    assert table.story_id == story.id
    assert table.status_kind == models.STATUS_KIND_NORMAL
    assert table.rows == (("手部", "长剑"),)

    replacement = _document(("手部", "法杖"))
    StoryStatusTableRecord.update(
        document_json=models.serialize_status_document(replacement)
    ).where(StoryStatusTableRecord.id == table.id).execute()
    assert service.get_story_table(table.id).rows == (("手部", "法杖"),)

    renamed = service.update_story_table(
        workspace_id,
        story.id,
        table.id,
        name="背包",
        document=_document(("金币", "7")),
    )
    assert renamed.name == "背包"
    assert renamed.rows == (("金币", "7"),)
    with pytest.raises(ValueError, match="already exists"):
        service.create_story_table(
            workspace_id,
            story.id,
            "背包",
            document=_document(),
        )
    service.delete_story_table(workspace_id, story.id, table.id)
    assert service.get_story_table(table.id) is None


def test_story_status_crud_does_not_materialize_legacy_status_dirs(tmp_path) -> None:
    gateway, workspace_id, workspace_root, story = _workspace(tmp_path, "no_status_dirs")
    gateway.status.create_story_table(
        workspace_id,
        story.id,
        "状态",
        document=_document(("生命", "10")),
    )
    assert not (workspace_root / "template_status").exists()
    assert not (workspace_root / "status").exists()


def test_session_copies_exact_story_status_table_set(tmp_path) -> None:
    gateway, workspace_id, _root, story = _workspace(tmp_path, "copy_set")
    other_story = StoryRepository(gateway.database).create(workspace_id, "学院")
    first = gateway.status.create_story_table(
        workspace_id, story.id, "第一张", document=_document(("A", "1"))
    )
    second = gateway.status.create_story_table(
        workspace_id, story.id, "第二张", document=_document(("B", "2"))
    )
    outsider = gateway.status.create_story_table(
        workspace_id, other_story.id, "外部", document=_document(("C", "3"))
    )
    session = gateway.sessions.create_session(
        workspace_id, story.id, session_id="s_exact_status"
    )
    assert session is not None

    copied = gateway.status.copy_story_status_tables_to_session(
        session.id, (second.id,)
    )
    assert len(copied) == 1
    assert copied[0].name == "第二张"
    assert copied[0].origin == models.STATUS_ORIGIN_STORY_COPY
    assert copied[0].source_story_status_table_id == second.id
    assert gateway.status.get_story_table(first.id) is not None
    with pytest.raises(FileNotFoundError, match="Story status tables not found"):
        gateway.status.copy_story_status_tables_to_session(
            session.id, (outsider.id,)
        )


def test_character_binding_is_snapshotted_by_stable_story_character_id(tmp_path) -> None:
    gateway, workspace_id, _root, story = _workspace(tmp_path, "character_status")
    alice = gateway.character_management.create_character(
        workspace_id, story.id, name="Alice"
    )
    bob = gateway.character_management.create_character(
        workspace_id, story.id, name="Bob"
    )
    assert alice is not None and bob is not None
    table = gateway.status.create_story_table(
        workspace_id,
        story.id,
        "Alice 状态",
        story_character_id=alice.id,
        document=_document(("心情", "平静")),
    )
    session = SessionCatalogService(gateway.sessions).create_session(
        workspace_id, story.id, session_id="s_character_status"
    )
    assert session is not None
    copied = gateway.status.list_tables(session.id)[0]
    metadata = models.parse_session_status_metadata(copied.metadata_json)
    assert metadata.story_source is not None
    assert metadata.story_source.story_status_table_id == table.id
    assert metadata.story_source.character_id == alice.id
    assert metadata.story_source.character_name == "Alice"

    rebound = gateway.status.update_story_table(
        workspace_id,
        story.id,
        table.id,
        story_character_id=bob.id,
        update_story_character=True,
    )
    assert rebound.story_character_id == bob.id
    unchanged = models.parse_session_status_metadata(
        gateway.status.get_table_by_id(copied.id).metadata_json
    )
    assert unchanged.story_source is not None
    assert unchanged.story_source.character_id == alice.id
    assert unchanged.story_source.character_name == "Alice"

    assert gateway.character_management.delete_character(
        workspace_id, story.id, bob.id
    ) is True
    assert gateway.status.get_story_table(table.id).story_character_id is None
    assert StatusContextService(gateway.status).list_tables(session.id)[0].id == copied.id


def test_copy_rejects_character_with_blank_name(tmp_path) -> None:
    gateway, workspace_id, _root, story = _workspace(tmp_path, "blank_character")
    character = gateway.character_management.create_character(
        workspace_id, story.id, name="Alice"
    )
    assert character is not None
    table = gateway.status.create_story_table(
        workspace_id,
        story.id,
        "角色状态",
        story_character_id=character.id,
        document=_document(("生命", "10")),
    )
    StoryCharacterRecord.update(name="").where(
        StoryCharacterRecord.id == character.id
    ).execute()
    session = gateway.sessions.create_session(
        workspace_id, story.id, session_id="s_blank_character"
    )
    assert session is not None
    with pytest.raises(ValueError, match="non-empty name"):
        gateway.status.copy_story_status_tables_to_session(session.id, (table.id,))


def test_session_copy_is_independent_and_survives_source_delete(tmp_path) -> None:
    gateway, workspace_id, _root, story = _workspace(tmp_path, "copy_independent")
    source = gateway.status.create_story_table(
        workspace_id,
        story.id,
        "封印",
        document=_document(("状态", "完整")),
    )
    session = SessionCatalogService(gateway.sessions).create_session(
        workspace_id, story.id, session_id="s_copy_independent"
    )
    assert session is not None
    copied = gateway.status.list_tables(session.id)[0]
    gateway.status.update_story_table(
        workspace_id,
        story.id,
        source.id,
        document=_document(("状态", "破裂")),
    )
    assert gateway.status.get_table_by_id(copied.id).rows == (("状态", "完整"),)

    gateway.status.delete_story_table(workspace_id, story.id, source.id)
    orphan_copy = gateway.status.get_table_by_id(copied.id)
    assert orphan_copy.source_story_status_table_id is None
    assert orphan_copy.rows == (("状态", "完整"),)


def test_session_status_reset_rebuilds_story_copies_and_clears_native_values(tmp_path) -> None:
    gateway, workspace_id, _root, story = _workspace(tmp_path, "status_reset")
    source = gateway.status.create_story_table(
        workspace_id,
        story.id,
        "剧情状态",
        document=_document(("封印", "完整")),
    )
    session = SessionCatalogService(gateway.sessions).create_session(
        workspace_id, story.id, session_id="s_status_reset"
    )
    assert session is not None
    native = gateway.status.create_table(
        session.id,
        "临时记录",
        document=_document(("备注", "保留结构")),
    )
    original_native_id = native.id
    gateway.status.update_story_table(
        workspace_id,
        story.id,
        source.id,
        document=_document(("封印", "破裂")),
    )

    result = SessionStatusLifecycleService(gateway.sessions).reset(session.id)
    assert result.story_tables_cleared == 1
    assert result.story_tables_initialized == 1
    assert result.native_tables_reset == 1
    tables = gateway.status.list_tables(session.id)
    rebuilt = next(table for table in tables if table.origin == models.STATUS_ORIGIN_STORY_COPY)
    reset_native = next(table for table in tables if table.origin == models.STATUS_ORIGIN_SESSION_NATIVE)
    assert rebuilt.rows == (("封印", "破裂"),)
    assert reset_native.id == original_native_id
    assert reset_native.rows == (("备注", ""),)


def test_scene_policy_and_status_manager_use_session_runtime_tables(tmp_path) -> None:
    gateway, workspace_id, _root, story = _workspace(tmp_path, "scene_status")
    administration = StatusTableAdministrationService(gateway.status)
    administration.create_story_table(
        workspace_id,
        story.id,
        "后备场景",
        status_kind=models.STATUS_KIND_SCENE,
        document=_document(("时间", "第 1 年 1 月 2 日"), ("位置", "学院")),
        sort_order=20,
    )
    administration.create_story_table(
        workspace_id,
        story.id,
        "当前场景",
        status_kind=models.STATUS_KIND_SCENE,
        document=_document(("时间", "第 1 年 1 月 1 日"), ("位置", "森林")),
        sort_order=10,
    )
    administration.create_story_table(
        workspace_id,
        story.id,
        "角色状态",
        document=_document(("生命", "10")),
        sort_order=30,
    )
    session = SessionCatalogService(gateway.sessions).create_session(
        workspace_id, story.id, session_id="s_scene_status"
    )
    assert session is not None
    scene = SceneStatusService(gateway.status).get_active_table(session.id)
    assert scene is not None
    assert scene.name == "当前场景"
    assert all(row.runtime_key_locked for row in scene.document.rows)
    assert SceneStatusService(gateway.status).get_attrs(session.id)["位置"] == "森林"

    manager = StatusManager(session.id, gateway.status)
    assert manager.list_tables(models.STATUS_KIND_NORMAL) == ["角色状态"]
    normal_table = gateway.status.get_table(session.id, "角色状态")
    result = manager.runtime_set_existing_values(normal_table.id, [("生命", "8")])
    assert result.changed is True
    assert gateway.status.get_table(session.id, "角色状态").document.rows[0].value == "8"


def test_status_reset_plan_is_atomic_on_invalid_story_table(tmp_path) -> None:
    gateway, workspace_id, _root, story = _workspace(tmp_path, "atomic_reset")
    session = gateway.sessions.create_session(
        workspace_id, story.id, session_id="s_atomic_reset"
    )
    assert session is not None
    native = gateway.status.create_table(
        session.id, "原生", document=_document(("值", "before"))
    )
    with pytest.raises(FileNotFoundError, match="Story status tables not found"):
        gateway.status.apply_session_reset_plan(
            session.id,
            models.SessionStatusResetPlan(
                document_writes=(
                    models.SessionStatusDocumentWrite(
                        table_id=native.id,
                        document=_document(("值", "after")),
                    ),
                ),
                story_status_table_ids=(999999,),
            ),
        )
    assert gateway.status.get_table_by_id(native.id).rows == (("值", "before"),)


def test_session_copy_metadata_uses_story_source_not_mount_fields(tmp_path) -> None:
    gateway, workspace_id, _root, story = _workspace(tmp_path, "metadata_shape")
    table = gateway.status.create_story_table(
        workspace_id, story.id, "全局", document=_document(("天气", "晴"))
    )
    session = gateway.sessions.create_session(
        workspace_id, story.id, session_id="s_metadata_shape"
    )
    assert session is not None
    copy = gateway.status.copy_story_status_tables_to_session(
        session.id, (table.id,)
    )[0]
    raw = json.loads(copy.metadata_json)
    assert raw["storyStatusSource"] == {
        "storyStatusTableId": table.id,
        "characterId": None,
        "characterName": None,
    }
    assert "storyStatusMount" not in raw
    assert "mountId" not in copy.metadata_json
