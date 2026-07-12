from __future__ import annotations

from pathlib import Path

import pytest
from peewee import IntegrityError, SqliteDatabase

from rpg_data import db
from rpg_data.migrations.runner import run_migrations
from rpg_data.services.catalog import CatalogService
from rpg_data.services.session_composer import SessionComposerService


def _database(tmp_path: Path) -> SqliteDatabase:
    path = tmp_path / "composer.sqlite3"
    connection = db.connect(path)
    try:
        run_migrations(connection)
    finally:
        connection.close()
    database = db.bind_peewee_database(db.make_peewee_database(path))
    database.connect()
    return database


def test_session_composer_modes_styles_and_story_defaults(tmp_path: Path) -> None:
    database = _database(tmp_path)
    try:
        service = SessionComposerService(database)
        catalog = CatalogService(database)
        modes = service.list_modes("demo_workspace")
        assert modes is not None
        assert [(item.mode, item.short_name) for item in modes] == [
            ("ic", "角色内"),
            ("ooc", "场外"),
            ("gm", "主持"),
        ]
        updated = service.update_mode(
            "demo_workspace",
            " OOC ",
            short_name="幕后",
            prompt="只讨论设定",
        )
        assert updated is not None and updated.short_name == "幕后"
        with pytest.raises(ValueError, match="invalid turn mode"):
            service.update_mode("demo_workspace", "chat", short_name="聊天", prompt="")

        existing = service.list_story_styles("demo_workspace", 1)
        assert existing is not None and len(existing) == 3
        new_style = service.create_style(
            "demo_workspace",
            name="冷峻留白",
            prompt="使用冷峻留白。",
            sort_order=40,
        )
        assert new_style is not None
        assert len(service.list_story_styles("demo_workspace", 1) or []) == 3

        new_story = catalog.create_story("demo_workspace", title="Composer Story")
        assert new_story is not None
        new_mounts = service.list_story_styles("demo_workspace", new_story.id) or []
        assert {mount.narrative_style_id for mount in new_mounts} == {
            style.id for style in service.list_styles("demo_workspace") or []
        }

        first, second = new_mounts[:2]
        assert service.set_story_base_style("demo_workspace", new_story.id, first.id).is_base
        assert service.set_story_base_style("demo_workspace", new_story.id, second.id).is_base
        refreshed = service.list_story_styles("demo_workspace", new_story.id) or []
        assert [mount.id for mount in refreshed if mount.is_base] == [second.id]

        session = catalog.create_session("demo_workspace", new_story.id, session_id="s_composer")
        assert session is not None
        assert service.resolve_session_style("s_composer", None).id == second.id
        assert service.resolve_session_style("s_composer", first.narrative_style_id).id == first.id
        with pytest.raises(ValueError, match="not mounted"):
            service.resolve_session_style("s_forest001", new_style.id)

        assert service.delete_style("demo_workspace", second.narrative_style_id)
        assert not any(mount.is_base for mount in service.list_story_styles("demo_workspace", new_story.id) or [])
    finally:
        database.close()


def test_session_composer_workspace_isolation_and_quick_reply_order(tmp_path: Path) -> None:
    database = _database(tmp_path)
    try:
        service = SessionComposerService(database)
        with database.atomic():
            database.execute_sql(
                "INSERT INTO rpg_workspaces (id, name, root_path) VALUES ('other', 'Other', 'other')"
            )
            database.execute_sql(
                "INSERT INTO rpg_stories (workspace_id, title) VALUES ('other', 'Other Story')"
            )
        other_story_id = int(database.execute_sql(
            "SELECT id FROM rpg_stories WHERE workspace_id = 'other'"
        ).fetchone()[0])
        foreign = service.create_style("other", name="Foreign", prompt="foreign")
        assert foreign is not None
        with pytest.raises(FileNotFoundError):
            service.mount_story_style("demo_workspace", 1, foreign.id)

        second = service.create_quick_reply(
            "demo_workspace", 1, title="第二", message="message 2", sort_order=20,
        )
        first = service.create_quick_reply(
            "demo_workspace", 1, title="第一", message="message 1", sort_order=10,
        )
        disabled = service.create_quick_reply(
            "demo_workspace", 1, title="停用", message="disabled", sort_order=0, enabled=False,
        )
        assert second and first and disabled
        assert [item.title for item in service.list_quick_replies("demo_workspace", 1) or []] == [
            "停用", "第一", "第二",
        ]
        assert [item.title for item in service.list_quick_replies(
            "demo_workspace", 1, enabled_only=True,
        ) or []] == ["第一", "第二"]
        assert service.list_quick_replies("other", other_story_id) == []
        with pytest.raises(IntegrityError):
            service.create_quick_reply(
                "demo_workspace", 1, title="第一", message="duplicate",
            )
    finally:
        database.close()
