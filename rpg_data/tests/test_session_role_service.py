from __future__ import annotations

import pytest

from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway
from rpg_data.story_template import StoryTextTemplateError


def test_session_role_binding_and_first_message() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = gateway.catalog.create_session("demo_workspace", 1, title="Role Test")
        assert session is not None

        initial = gateway.session_roles.get_state(session.id)
        assert initial.status == models.PLAYER_CHARACTER_STATUS_INVALID
        assert initial.player is None

        options = gateway.session_roles.list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")

        bound = gateway.session_roles.bind_player_character(session.id, bob.snapshot.character_id)
        assert bound.state.status == models.PLAYER_CHARACTER_STATUS_BOUND
        assert bound.state.player is not None
        assert bound.state.player.name == "Bob"
        assert "北境森林的霜雾" in bound.first_message
        assert gateway.messages.count(session.id) == 1
        assert gateway.backup.messages.count(session.id) == 1
        assert "1. Bob（当前扮演）" in gateway.session_roles.render_role_bind_prompt(session.id)

        rebound = gateway.session_roles.bind_player_character(session.id, bob.snapshot.character_id)
        assert rebound.first_message == ""
        assert gateway.messages.count(session.id) == 1

        state = gateway.session_roles.get_state(session.id)
        assert state.status == models.PLAYER_CHARACTER_STATUS_BOUND
        assert state.player is not None
        assert state.player.name == "Bob"
    finally:
        gateway.close()


def test_session_role_renders_alice_first_message_without_mutating_template() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        story = gateway.catalog.get_story("demo_workspace", 1)
        assert story is not None
        template = "欢迎，{USER_PLAY_ROLE_NAME}。"
        gateway.catalog.update_story(
            "demo_workspace",
            story.id,
            first_message=template,
        )
        session = gateway.catalog.create_session(
            "demo_workspace",
            story.id,
            title="Alice Role Test",
        )
        assert session is not None
        alice = next(
            option
            for option in gateway.session_roles.list_options(session.id)
            if option.snapshot.name == "Alice"
        )

        bound = gateway.session_roles.bind_player_character(
            session.id,
            alice.snapshot.character_id,
        )

        assert bound.first_message == "欢迎，Alice。"
        assert gateway.messages.list(session.id)[0].content == "欢迎，Alice。"
        assert gateway.backup.messages.list(session.id)[0].content == "欢迎，Alice。"
        stored_story = gateway.catalog.get_story("demo_workspace", story.id)
        assert stored_story is not None
        assert stored_story.first_message == template
    finally:
        gateway.close()


def test_role_switch_after_clear_does_not_reappend_first_message() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = gateway.catalog.create_session("demo_workspace", 1, title="Cleared Role Test")
        assert session is not None
        options = gateway.session_roles.list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")
        alice = next(option for option in options if option.snapshot.name == "Alice")

        first_bind = gateway.session_roles.bind_player_character(
            session.id,
            bob.snapshot.character_id,
        )
        assert first_bind.first_message
        assert gateway.messages.clear(session.id) == 1

        switched = gateway.session_roles.bind_player_character(
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


def test_invalid_legacy_first_message_does_not_partially_bind() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = gateway.catalog.create_session("demo_workspace", 1, title="Invalid Template")
        assert session is not None
        gateway.database.execute_sql(
            "UPDATE rpg_stories SET first_message = ? WHERE id = ?",
            ("欢迎，{UNKNOWN_ROLE}。", session.story_id),
        )
        alice = next(
            option
            for option in gateway.session_roles.list_options(session.id)
            if option.snapshot.name == "Alice"
        )

        with pytest.raises(StoryTextTemplateError, match="UNKNOWN_ROLE"):
            gateway.session_roles.bind_player_character(
                session.id,
                alice.snapshot.character_id,
            )

        state = gateway.session_roles.get_state(session.id)
        assert state.status == models.PLAYER_CHARACTER_STATUS_INVALID
        assert gateway.messages.count(session.id) == 0
        assert gateway.backup.messages.count(session.id) == 0
    finally:
        gateway.close()


def test_session_role_invalid_when_character_unmounted() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = gateway.catalog.create_session("demo_workspace", 1, title="Unmount Test")
        assert session is not None

        options = gateway.session_roles.list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")
        gateway.session_roles.bind_player_character(session.id, bob.snapshot.character_id)

        deleted = gateway.character_management.unmount_character(
            "demo_workspace",
            1,
            bob.snapshot.mount_id,
        )
        assert deleted is True

        state = gateway.session_roles.get_state(session.id)
        assert state.status == models.PLAYER_CHARACTER_STATUS_INVALID
        assert state.player is None
    finally:
        gateway.close()


def test_session_role_invalid_when_snapshot_is_corrupted() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = gateway.catalog.create_session("demo_workspace", 1, title="Corrupt Snapshot Test")
        assert session is not None

        options = gateway.session_roles.list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")
        gateway.session_roles.bind_player_character(session.id, bob.snapshot.character_id)

        gateway.database.execute_sql(
            "UPDATE rpg_session_profiles SET player_character_snapshot_json = ? WHERE session_id = ?",
            ('{"characterId":%d}' % bob.snapshot.character_id, session.id),
        )

        state = gateway.session_roles.get_state(session.id)
        assert state.status == models.PLAYER_CHARACTER_STATUS_INVALID
        assert state.player is None
    finally:
        gateway.close()


def test_session_role_invalid_when_snapshot_mount_is_stale() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        session = gateway.catalog.create_session("demo_workspace", 1, title="Stale Snapshot Test")
        assert session is not None

        options = gateway.session_roles.list_options(session.id)
        bob = next(option for option in options if option.snapshot.name == "Bob")
        gateway.session_roles.bind_player_character(session.id, bob.snapshot.character_id)

        gateway.database.execute_sql(
            """
            UPDATE rpg_session_profiles
            SET player_character_snapshot_json = REPLACE(player_character_snapshot_json, ?, ?)
            WHERE session_id = ?
            """,
            (f'"mountId":{bob.snapshot.mount_id}', f'"mountId":{bob.snapshot.mount_id + 999}', session.id),
        )

        state = gateway.session_roles.get_state(session.id)
        assert state.status == models.PLAYER_CHARACTER_STATUS_INVALID
        assert state.player is None
    finally:
        gateway.close()
