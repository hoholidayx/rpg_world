from __future__ import annotations

import pytest

from rpg_core.agent.command.role import render_role_bind_prompt
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.reset import SessionResetService
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionRoleService,
)
from rpg_core.story.template import StoryTextTemplateError
from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway


def _catalog(gateway: DataServiceGateway) -> SessionCatalogService:
    return SessionCatalogService(gateway.sessions)


def _roles(gateway: DataServiceGateway) -> SessionRoleService:
    return SessionRoleService(gateway.sessions)


def test_session_role_binding_and_first_message() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = _catalog(gateway).create_session("demo_workspace", 1, title="Role Test")
        assert session is not None

        initial = _roles(gateway).get_state(session.id)
        assert initial.status == PlayerCharacterBindingStatus.INVALID
        assert initial.player is None

        options = _roles(gateway).list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")

        bound = _roles(gateway).bind_player_character(session.id, bob.snapshot.character_id)
        assert bound.state.status == PlayerCharacterBindingStatus.BOUND
        assert bound.state.player is not None
        assert bound.state.player.name == "Bob"
        assert "北境森林的霜雾" in bound.first_message
        assert gateway.messages.count(session.id) == 1
        assert gateway.backup.messages.count(session.id) == 1
        assert "1. Bob（当前扮演）" in render_role_bind_prompt(
            _roles(gateway).list_options(session.id),
            _roles(gateway).get_state(session.id),
        )

        rebound = _roles(gateway).bind_player_character(session.id, bob.snapshot.character_id)
        assert rebound.first_message == ""
        assert gateway.messages.count(session.id) == 1

        state = _roles(gateway).get_state(session.id)
        assert state.status == PlayerCharacterBindingStatus.BOUND
        assert state.player is not None
        assert state.player.name == "Bob"
    finally:
        gateway.close()


def test_session_role_lists_rendered_openings_and_selects_one_atomically() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        story = _catalog(gateway).create_story(
            "demo_workspace",
            title="三开局角色测试",
            openings=(
                models.StoryOpeningInput(title="第一幕", message="{USER_PLAY_ROLE_NAME} 在门外。"),
                models.StoryOpeningInput(title="第二幕", message="{USER_PLAY_ROLE_NAME} 在雨中。"),
                models.StoryOpeningInput(title="第三幕", message="{USER_PLAY_ROLE_NAME} 在梦里。"),
            ),
        )
        assert story is not None
        bob_mount = gateway.character_management.mount_character(
            "demo_workspace",
            story.id,
            1,
        )
        assert bob_mount is not None
        session = _catalog(gateway).create_session(
            "demo_workspace",
            story.id,
            title="选择第二开局",
        )
        assert session is not None

        options = _roles(gateway).list_opening_options(session.id, 1)
        assert [item.opening.title for item in options] == ["第一幕", "第二幕", "第三幕"]
        assert [item.rendered_message for item in options] == [
            "Bob 在门外。",
            "Bob 在雨中。",
            "Bob 在梦里。",
        ]
        assert gateway.catalog.get_session(session.id).player_character_id is None
        assert gateway.messages.count(session.id) == 0

        selected = _roles(gateway).bind_player_character(
            session.id,
            1,
            story_opening_id=story.openings[1].id,
        )

        stored = gateway.catalog.get_session(session.id)
        assert selected.story_opening_id == story.openings[1].id
        assert selected.first_message == "Bob 在雨中。"
        assert stored is not None
        assert stored.player_character_id == 1
        assert stored.story_opening_id == story.openings[1].id
        assert gateway.messages.list(session.id)[0].content == "Bob 在雨中。"
        assert gateway.backup.messages.list(session.id)[0].content == "Bob 在雨中。"
    finally:
        gateway.close()


def test_session_role_defaults_first_opening_and_supports_story_without_opening() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        story = gateway.catalog.get_story("demo_workspace", 1)
        assert story is not None and story.openings
        default_session = _catalog(gateway).create_session(
            "demo_workspace",
            story.id,
            title="默认开局",
        )
        assert default_session is not None
        default_result = _roles(gateway).bind_player_character(
            default_session.id,
            1,
        )
        assert default_result.story_opening_id == story.openings[0].id
        assert gateway.catalog.get_session(default_session.id).story_opening_id == story.openings[0].id

        empty_story = _catalog(gateway).create_story(
            "demo_workspace",
            title="空开局角色测试",
        )
        assert empty_story is not None
        assert gateway.character_management.mount_character(
            "demo_workspace",
            empty_story.id,
            1,
        ) is not None
        empty_session = _catalog(gateway).create_session(
            "demo_workspace",
            empty_story.id,
            title="空开局",
        )
        assert empty_session is not None
        empty_result = _roles(gateway).bind_player_character(empty_session.id, 1)
        assert empty_result.story_opening_id is None
        assert empty_result.first_message == ""
        assert gateway.messages.count(empty_session.id) == 0
    finally:
        gateway.close()


def test_non_initial_role_switch_rejects_opening_selection_without_changes() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        story = gateway.catalog.get_story("demo_workspace", 1)
        assert story is not None and story.openings
        session = _catalog(gateway).create_session("demo_workspace", story.id, title="禁止重选开局")
        assert session is not None
        _roles(gateway).bind_player_character(session.id, 1)
        before = gateway.catalog.get_session(session.id)
        message_count = gateway.messages.count(session.id)

        with pytest.raises(ValueError, match="only be selected"):
            _roles(gateway).bind_player_character(
                session.id,
                2,
                story_opening_id=story.openings[0].id,
            )

        after = gateway.catalog.get_session(session.id)
        assert after is not None and before is not None
        assert after.player_character_id == before.player_character_id
        assert after.story_opening_id == before.story_opening_id
        assert gateway.messages.count(session.id) == message_count
    finally:
        gateway.close()


def test_reset_reuses_selected_opening_id_with_latest_body_and_falls_back_after_delete() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        original = gateway.catalog.get_story("demo_workspace", 1)
        assert original is not None and original.openings
        story = _catalog(gateway).update_story(
            "demo_workspace",
            original.id,
            openings=(
                models.StoryOpeningInput(
                    id=original.openings[0].id,
                    title="默认线",
                    message="默认线：{USER_PLAY_ROLE_NAME}",
                ),
                models.StoryOpeningInput(
                    title="秘密线",
                    message="秘密线旧正文：{USER_PLAY_ROLE_NAME}",
                ),
            ),
        )
        assert story is not None
        session = _catalog(gateway).create_session("demo_workspace", story.id, title="稳定开局")
        assert session is not None
        selected_id = story.openings[1].id
        _roles(gateway).bind_player_character(
            session.id,
            1,
            story_opening_id=selected_id,
        )

        story = _catalog(gateway).update_story(
            "demo_workspace",
            story.id,
            openings=(
                models.StoryOpeningInput(
                    id=story.openings[0].id,
                    title="默认线",
                    message="默认线：{USER_PLAY_ROLE_NAME}",
                ),
                models.StoryOpeningInput(
                    id=selected_id,
                    title="秘密线",
                    message="秘密线新正文：{USER_PLAY_ROLE_NAME}",
                ),
            ),
        )
        assert story is not None
        first_reset = SessionResetService(gateway.sessions).reset(session.id)
        assert first_reset.first_message == "秘密线新正文：Bob"
        assert gateway.catalog.get_session(session.id).story_opening_id == selected_id

        story = _catalog(gateway).update_story(
            "demo_workspace",
            story.id,
            openings=(
                models.StoryOpeningInput(
                    id=story.openings[0].id,
                    title="默认线",
                    message="默认线更新：{USER_PLAY_ROLE_NAME}",
                ),
            ),
        )
        assert story is not None
        assert gateway.catalog.get_session(session.id).story_opening_id is None
        second_reset = SessionResetService(gateway.sessions).reset(session.id)
        assert second_reset.first_message == "默认线更新：Bob"
        assert gateway.catalog.get_session(session.id).story_opening_id == story.openings[0].id
    finally:
        gateway.close()


def test_session_role_renders_alice_first_message_without_mutating_template() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        story = gateway.catalog.get_story("demo_workspace", 1)
        assert story is not None
        template = "欢迎，{USER_PLAY_ROLE_NAME}。"
        _catalog(gateway).update_story(
            "demo_workspace",
            story.id,
            openings=(
                models.StoryOpeningInput(
                    id=story.openings[0].id,
                    title=story.openings[0].title,
                    message=template,
                ),
            ),
        )
        session = _catalog(gateway).create_session(
            "demo_workspace",
            story.id,
            title="Alice Role Test",
        )
        assert session is not None
        alice = next(
            option
            for option in _roles(gateway).list_options(session.id)
            if option.snapshot.name == "Alice"
        )

        bound = _roles(gateway).bind_player_character(
            session.id,
            alice.snapshot.character_id,
        )

        assert bound.first_message == "欢迎，Alice。"
        assert gateway.messages.list(session.id)[0].content == "欢迎，Alice。"
        assert gateway.backup.messages.list(session.id)[0].content == "欢迎，Alice。"
        stored_story = gateway.catalog.get_story("demo_workspace", story.id)
        assert stored_story is not None
        assert stored_story.openings[0].message == template
    finally:
        gateway.close()


def test_role_switch_after_clear_does_not_reappend_first_message() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = _catalog(gateway).create_session("demo_workspace", 1, title="Cleared Role Test")
        assert session is not None
        options = _roles(gateway).list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")
        alice = next(option for option in options if option.snapshot.name == "Alice")

        first_bind = _roles(gateway).bind_player_character(
            session.id,
            bob.snapshot.character_id,
        )
        assert first_bind.first_message
        assert gateway.messages.clear(session.id) == 1

        switched = _roles(gateway).bind_player_character(
            session.id,
            alice.snapshot.character_id,
        )

        assert switched.first_message == ""
        assert gateway.messages.count(session.id) == 0
        assert gateway.backup.messages.count(session.id) == 1
        assert switched.state.player is not None
        assert switched.state.player.name == "Alice"
    finally:
        gateway.close()


def test_invalid_story_opening_does_not_partially_bind() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = _catalog(gateway).create_session("demo_workspace", 1, title="Invalid Template")
        assert session is not None
        gateway.database.execute_sql(
            "UPDATE rpg_story_openings SET message = ? WHERE story_id = ? AND sort_order = 0",
            ("欢迎，{UNKNOWN_ROLE}。", session.story_id),
        )
        alice = next(
            option
            for option in _roles(gateway).list_options(session.id)
            if option.snapshot.name == "Alice"
        )

        with pytest.raises(StoryTextTemplateError, match="UNKNOWN_ROLE"):
            _roles(gateway).bind_player_character(
                session.id,
                alice.snapshot.character_id,
            )

        state = _roles(gateway).get_state(session.id)
        assert state.status == PlayerCharacterBindingStatus.INVALID
        assert gateway.messages.count(session.id) == 0
        assert gateway.backup.messages.count(session.id) == 0
    finally:
        gateway.close()


def test_session_role_invalid_when_character_unmounted() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = _catalog(gateway).create_session("demo_workspace", 1, title="Unmount Test")
        assert session is not None

        options = _roles(gateway).list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")
        _roles(gateway).bind_player_character(session.id, bob.snapshot.character_id)

        deleted = gateway.character_management.unmount_character(
            "demo_workspace",
            1,
            bob.snapshot.mount_id,
        )
        assert deleted is True

        state = _roles(gateway).get_state(session.id)
        assert state.status == PlayerCharacterBindingStatus.INVALID
        assert state.player is None
    finally:
        gateway.close()


def test_session_role_invalid_when_snapshot_is_corrupted() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = _catalog(gateway).create_session("demo_workspace", 1, title="Corrupt Snapshot Test")
        assert session is not None

        options = _roles(gateway).list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")
        _roles(gateway).bind_player_character(session.id, bob.snapshot.character_id)

        gateway.database.execute_sql(
            "UPDATE rpg_session_profiles SET player_character_snapshot_json = ? WHERE session_id = ?",
            ('{"characterId":%d}' % bob.snapshot.character_id, session.id),
        )

        state = _roles(gateway).get_state(session.id)
        assert state.status == PlayerCharacterBindingStatus.INVALID
        assert state.player is None
    finally:
        gateway.close()


def test_session_role_invalid_when_snapshot_mount_is_stale() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = _catalog(gateway).create_session("demo_workspace", 1, title="Stale Snapshot Test")
        assert session is not None

        options = _roles(gateway).list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")
        _roles(gateway).bind_player_character(session.id, bob.snapshot.character_id)

        gateway.database.execute_sql(
            """
            UPDATE rpg_session_profiles
            SET player_character_snapshot_json = REPLACE(player_character_snapshot_json, ?, ?)
            WHERE session_id = ?
            """,
            (f'"mountId":{bob.snapshot.mount_id}', f'"mountId":{bob.snapshot.mount_id + 999}', session.id),
        )

        state = _roles(gateway).get_state(session.id)
        assert state.status == PlayerCharacterBindingStatus.INVALID
        assert state.player is None
    finally:
        gateway.close()
