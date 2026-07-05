from __future__ import annotations

from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway


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

        rebound = gateway.session_roles.bind_player_character(session.id, bob.snapshot.character_id)
        assert rebound.first_message == ""
        assert gateway.messages.count(session.id) == 1

        state = gateway.session_roles.get_state(session.id)
        assert state.status == models.PLAYER_CHARACTER_STATUS_BOUND
        assert state.player is not None
        assert state.player.name == "Bob"
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
