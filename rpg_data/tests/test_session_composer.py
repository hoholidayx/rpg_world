from __future__ import annotations

from pathlib import Path

import pytest
from peewee import IntegrityError, SqliteDatabase

from rpg_core.rp_modules.application import RPModuleApplicationService
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.composer import SessionComposerApplicationService
from rpg_data import db
from rpg_data.errors import DataIntegrityError
from rpg_data.migrations.runner import run_migrations
from rpg_data.services.gateway import DataServiceGateway
from rpg_data.services.session_composer import SessionComposerDataService


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


def _assert_integrity_chain(
    exc: DataIntegrityError,
    expected_message: str,
) -> None:
    assert str(exc) == expected_message
    assert isinstance(exc.__cause__, IntegrityError)
    assert "constraint" in str(exc.__cause__).lower()


def test_session_composer_modes_styles_and_story_defaults(tmp_path: Path) -> None:
    gateway = DataServiceGateway(tmp_path / "composer.sqlite3")
    gateway.initialize()
    try:
        rp_modules = RPModuleApplicationService(
            RPModuleRegistry(),
            gateway.rp_modules,
        )
        service = SessionComposerApplicationService(
            gateway.session_composer,
            rp_modules,
        )
        catalog = gateway.catalog
        demo_snapshot = service.get_snapshot("s_forest001")
        assert demo_snapshot is not None
        assert [(item.mode.value, item.short_name) for item in demo_snapshot.modes] == [
            ("neutral", "默认"),
            ("ic", "角色内"),
            ("ooc", "场外"),
            ("gm", "主持"),
        ]

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

        new_story = SessionCatalogService(gateway.sessions).create_story(
            "demo_workspace",
            title="Composer Story",
        )
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
        gateway.close()


def test_session_composer_workspace_isolation_and_quick_reply_order(tmp_path: Path) -> None:
    database = _database(tmp_path)
    try:
        service = SessionComposerApplicationService(
            SessionComposerDataService(database)
        )
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
        with pytest.raises(
            DataIntegrityError,
            match="Quick reply write violated persisted constraints",
        ) as conflict:
            service.create_quick_reply(
                "demo_workspace", 1, title="第一", message="duplicate",
            )
        _assert_integrity_chain(
            conflict.value,
            "Quick reply write violated persisted constraints",
        )
    finally:
        database.close()


def test_session_composer_translates_style_and_quick_reply_integrity_errors(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    try:
        service = SessionComposerApplicationService(
            SessionComposerDataService(database)
        )
        first_style = service.create_style(
            "demo_workspace",
            name="Boundary First",
            prompt="first",
        )
        second_style = service.create_style(
            "demo_workspace",
            name="Boundary Second",
            prompt="second",
        )
        assert first_style is not None and second_style is not None

        with pytest.raises(DataIntegrityError) as style_create_conflict:
            service.create_style(
                "demo_workspace",
                name="Boundary First",
                prompt="duplicate",
            )
        _assert_integrity_chain(
            style_create_conflict.value,
            "Narrative style write violated persisted constraints",
        )

        with pytest.raises(DataIntegrityError) as style_update_conflict:
            service.update_style(
                "demo_workspace",
                second_style.id,
                name="Boundary First",
            )
        _assert_integrity_chain(
            style_update_conflict.value,
            "Narrative style write violated persisted constraints",
        )

        first_reply = service.create_quick_reply(
            "demo_workspace",
            1,
            title="Boundary First",
            message="first",
        )
        second_reply = service.create_quick_reply(
            "demo_workspace",
            1,
            title="Boundary Second",
            message="second",
        )
        assert first_reply is not None and second_reply is not None

        with pytest.raises(DataIntegrityError) as reply_update_conflict:
            service.update_quick_reply(
                "demo_workspace",
                1,
                second_reply.id,
                title="Boundary First",
            )
        _assert_integrity_chain(
            reply_update_conflict.value,
            "Quick reply write violated persisted constraints",
        )
    finally:
        database.close()


def test_session_composer_translates_low_frequency_write_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = _database(tmp_path)
    try:
        data = SessionComposerDataService(database)
        service = SessionComposerApplicationService(data)
        style = service.create_style(
            "demo_workspace",
            name="Boundary Mount",
            prompt="mount",
        )
        reply = service.create_quick_reply(
            "demo_workspace",
            1,
            title="Boundary Delete",
            message="delete",
        )
        assert style is not None and reply is not None

        def _fail_write(*_args, **_kwargs):
            raise IntegrityError("forced constraint failure")

        cases = (
            (
                "delete_style",
                lambda: service.delete_style("demo_workspace", style.id),
                "Narrative style write violated persisted constraints",
            ),
            (
                "mount_story_styles",
                lambda: service.mount_story_style(
                    "demo_workspace",
                    1,
                    style.id,
                ),
                "Story narrative style write violated persisted constraints",
            ),
            (
                "unmount_story_style",
                lambda: service.unmount_story_style(
                    "demo_workspace",
                    1,
                    999,
                ),
                "Story narrative style write violated persisted constraints",
            ),
            (
                "set_story_base_style",
                lambda: service.set_story_base_style(
                    "demo_workspace",
                    1,
                    None,
                ),
                "Story narrative style write violated persisted constraints",
            ),
            (
                "delete_quick_reply",
                lambda: service.delete_quick_reply(
                    "demo_workspace",
                    1,
                    reply.id,
                ),
                "Quick reply write violated persisted constraints",
            ),
        )

        for repository_method, operation, expected_message in cases:
            with monkeypatch.context() as scoped:
                scoped.setattr(data._repo, repository_method, _fail_write)
                with pytest.raises(DataIntegrityError) as conflict:
                    operation()
            _assert_integrity_chain(conflict.value, expected_message)
    finally:
        database.close()
