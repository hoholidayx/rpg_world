from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from rpg_data import models
from rpg_data.model.session_reference import (
    SessionReferenceLocator,
    SessionReferenceStatusOrder,
)
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways


@pytest.fixture(autouse=True)
def _reset_gateways(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def _locator(
    *,
    session_id: str = "s_forest001",
    workspace_id: str = "demo_workspace",
    story_id: int = 1,
) -> SessionReferenceLocator:
    return SessionReferenceLocator(
        session_id=session_id,
        workspace_id=workspace_id,
        story_id=story_id,
    )


def test_reference_scope_requires_exact_catalog_ownership_but_reports_lifecycle(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "scope.sqlite3")
    data = gateway.session_reference

    scope = data.require_scope(_locator())
    assert scope.session_id == "s_forest001"
    assert scope.workspace_id == "demo_workspace"
    assert scope.story_id == 1
    assert scope.lifecycle == models.SESSION_LIFECYCLE_READY
    assert scope.title == "北境森林主线"
    assert scope.player_character_id == 1

    provisioning = gateway.sessions.create_session(
        "demo_workspace",
        1,
        session_id="s_reference_provisioning",
        title="Provisioning reference",
        lifecycle=models.SESSION_LIFECYCLE_PROVISIONING,
    )
    assert provisioning is not None
    pending_scope = data.require_scope(
        _locator(session_id=provisioning.id)
    )
    assert pending_scope.lifecycle == models.SESSION_LIFECYCLE_PROVISIONING

    with pytest.raises(FileNotFoundError, match="Session reference scope"):
        data.require_scope(_locator(workspace_id="wrong_workspace"))
    with pytest.raises(FileNotFoundError, match="Session reference scope"):
        data.require_scope(_locator(story_id=2))
    with pytest.raises(FileNotFoundError, match="Session reference scope"):
        data.require_scope(_locator(session_id="missing_session"))


def test_character_reference_reads_are_lightweight_paginated_and_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "characters.sqlite3")
    data = gateway.session_reference
    locator = _locator()

    first_page = data.list_characters(locator, page=1, page_size=1)
    second_page = data.list_characters(locator, page=2, page_size=1)
    assert first_page.total == 2
    assert first_page.total_pages == 2
    assert [item.name for item in first_page.items] == ["Bob"]
    assert [item.name for item in second_page.items] == ["Alice"]
    assert first_page.items[0].details_count == 1

    character = data.get_character(locator, first_page.items[0].id)
    assert character == first_page.items[0]
    detail_statements: list[str] = []
    original_execute_sql = gateway.database.execute_sql

    def _track_detail_sql(sql: str, *args: object, **kwargs: object):
        detail_statements.append(sql)
        return original_execute_sql(sql, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(gateway.database, "execute_sql", _track_detail_sql)
        details = data.list_character_details(
            locator,
            character.id,
            page=1,
            page_size=8,
        )
    assert details.total == character.details_count
    assert not hasattr(details.items[0], "content")
    assert not hasattr(details.items[0], "tags_json")
    detail_queries = [
        sql
        for sql in detail_statements
        if "rpg_story_character_details" in sql
    ]
    assert detail_queries
    assert all('"content"' not in sql for sql in detail_queries)
    assert all('"tags_json"' not in sql for sql in detail_queries)

    detail = data.get_character_detail(
        locator,
        character.id,
        details.items[0].id,
    )
    assert detail is not None
    assert detail.content
    assert detail.tags_json.startswith("[")

    academy_character = data.list_characters(
        _locator(session_id="s_academy01", story_id=2),
        page=1,
        page_size=8,
    ).items[0]
    assert data.get_character(locator, academy_character.id) is None
    assert (
        data.get_character_detail(
            locator,
            academy_character.id,
            details.items[0].id,
        )
        is None
    )

    for index in range(12):
        created = gateway.character_management.create_detail(
            "demo_workspace",
            1,
            character.id,
            name=f"Extra {index}",
            content=f"detail body {index}",
        )
        assert created is not None
    statements: list[str] = []
    original_execute_sql = gateway.database.execute_sql

    def _tracked_execute_sql(sql: str, *args: object, **kwargs: object):
        statements.append(sql)
        return original_execute_sql(sql, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(gateway.database, "execute_sql", _tracked_execute_sql)
        expanded = data.list_characters(locator, page=1, page_size=8)
    assert expanded.items[0].details_count == 13
    assert sum(sql.lstrip().upper().startswith("SELECT") for sql in statements) == 3

    with pytest.raises(ValueError, match="page must be positive"):
        data.list_characters(locator, page=0, page_size=8)
    with pytest.raises(ValueError, match="page_size"):
        data.list_characters(locator, page=1, page_size=101)


def test_character_count_and_rows_share_one_read_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "character-snapshot.sqlite3"
    gateway = get_data_service_gateway(database_path)
    data = gateway.session_reference
    locator = _locator()
    writer = sqlite3.connect(database_path)
    writer.execute("PRAGMA foreign_keys = ON")
    writer.execute("PRAGMA journal_mode = WAL")
    original_execute_sql = gateway.database.execute_sql
    mutation_done = False

    def _mutate_after_count(
        sql: str,
        *args: object,
        **kwargs: object,
    ):
        nonlocal mutation_done
        cursor = original_execute_sql(sql, *args, **kwargs)
        if (
            not mutation_done
            and "COUNT" in sql.upper()
            and "rpg_story_characters" in sql
        ):
            mutation_done = True
            writer.execute(
                """
                DELETE FROM rpg_story_characters
                WHERE workspace_id = ? AND story_id = ? AND name = ?
                """,
                ("demo_workspace", 1, "Alice"),
            )
            writer.commit()
        return cursor

    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                gateway.database,
                "execute_sql",
                _mutate_after_count,
            )
            current = data.list_characters(
                locator,
                page=1,
                page_size=8,
            )
    finally:
        writer.close()

    assert mutation_done is True
    assert current.total == 2
    assert [item.name for item in current.items] == ["Bob", "Alice"]

    next_snapshot = data.list_characters(locator, page=1, page_size=8)
    assert next_snapshot.total == 1
    assert [item.name for item in next_snapshot.items] == ["Bob"]


def test_scope_lifecycle_is_stable_until_the_next_transaction(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "lifecycle-snapshot.sqlite3"
    gateway = get_data_service_gateway(database_path)
    data = gateway.session_reference
    locator = _locator()
    writer = sqlite3.connect(database_path)
    writer.execute("PRAGMA journal_mode = WAL")

    try:
        with data.transaction():
            assert data.require_scope(locator).lifecycle == "ready"
            writer.execute(
                "UPDATE rpg_sessions SET lifecycle = ? WHERE id = ?",
                ("provisioning", locator.session_id),
            )
            writer.commit()
            assert data.require_scope(locator).lifecycle == "ready"
    finally:
        writer.close()

    assert data.require_scope(locator).lifecycle == "provisioning"


def test_status_reference_reads_preserve_association_and_scope_document(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "statuses.sqlite3")
    data = gateway.session_reference
    alice = gateway.character_management.list_characters("demo_workspace", 1)
    assert alice is not None
    alice_row = next(item for item in alice if item.name == "Alice")
    bob_row = next(item for item in alice if item.name == "Bob")
    source = gateway.status.create_story_table(
        "demo_workspace",
        1,
        "Alice Reference",
        story_character_id=alice_row.id,
        document=models.StatusTableDocument.from_rows(
            rows=(models.StatusTableRow("心情", "平静"),),
        ),
        description="Alice current facts",
        sort_order=99,
    )
    bob_source = gateway.status.create_story_table(
        "demo_workspace",
        1,
        "Bob Reference",
        story_character_id=bob_row.id,
        document=models.StatusTableDocument.from_rows(
            rows=(models.StatusTableRow("装备", "重剑"),),
        ),
        sort_order=1,
    )
    unassociated_source = gateway.status.create_story_table(
        "demo_workspace",
        1,
        "World Reference",
        document=models.StatusTableDocument.from_rows(
            rows=(models.StatusTableRow("天气", "晴朗"),),
        ),
        sort_order=0,
    )
    scene_source = gateway.status.create_story_table(
        "demo_workspace",
        1,
        "Scene Reference",
        status_kind=models.STATUS_KIND_SCENE,
        document=models.StatusTableDocument.from_rows(
            rows=(models.StatusTableRow("地点", "石门"),),
        ),
        sort_order=100,
    )
    session = gateway.sessions.create_session(
        "demo_workspace",
        1,
        session_id="s_reference_status",
        title="Reference status",
    )
    assert session is not None
    copied = gateway.status.copy_story_status_tables_to_session(
        session.id,
        (source.id, bob_source.id, unassociated_source.id, scene_source.id),
    )
    copied_by_name = {item.name: item for item in copied}
    locator = _locator(session_id=session.id)

    page = data.list_status_tables(
        locator,
        page=1,
        page_size=8,
        character_id=alice_row.id,
    )
    assert page.total == 1
    assert page.items[0].id == copied_by_name["Alice Reference"].id
    assert page.items[0].associated_character_id == alice_row.id
    assert page.items[0].associated_character_name == "Alice"

    detail = data.get_status_table(
        locator,
        copied_by_name["Alice Reference"].id,
    )
    assert detail is not None
    assert detail.document.data_rows == (("心情", "平静"),)
    assert (
        data.get_status_table(
            _locator(),
            copied_by_name["Alice Reference"].id,
        )
        is None
    )

    assert data.list_character_order_ids(locator) == (bob_row.id, alice_row.id)
    assert gateway.character_management.delete_character(
        "demo_workspace",
        1,
        alice_row.id,
    )
    orphan_association = data.list_status_tables(
        locator,
        page=1,
        page_size=8,
        character_id=alice_row.id,
    )
    assert [item.name for item in orphan_association.items] == [
        "Alice Reference"
    ]
    assert data.list_character_order_ids(locator) == (bob_row.id,)
    custom_order = SessionReferenceStatusOrder(
        status_kind_order=("scene", "normal"),
        ordered_character_ids=(bob_row.id,),
        associated_first=True,
    )
    ordered = data.list_status_tables(
        locator,
        page=1,
        page_size=8,
        order=custom_order,
    )
    assert [item.name for item in ordered.items] == [
        "Scene Reference",
        "Bob Reference",
        "Alice Reference",
        "World Reference",
    ]


def test_summary_source_resolves_safe_path_and_stable_turn_ranges(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "summaries.sqlite3")
    data = gateway.session_reference
    locator = _locator()
    first = gateway.messages.append(
        locator.session_id,
        models.MESSAGE_ROLE_USER,
        "summary one",
        turn_id=90,
        seq_in_turn=1,
    )
    second = gateway.messages.append(
        locator.session_id,
        models.MESSAGE_ROLE_ASSISTANT,
        "summary two",
        turn_id=91,
        seq_in_turn=1,
    )
    assert gateway.messages.mark_summary_processed(
        locator.session_id,
        (first.id, second.id),
        batch_id=77,
    ) == 2

    source = data.get_summary_source(locator)
    assert source.runtime_dir == (
        tmp_path / "data/demo_workspace/stories/1/s_forest001"
    ).resolve()
    assert [
        (item.batch_id, item.turn_start, item.turn_end)
        for item in source.batch_turn_ranges
    ] == [(77, 90, 91)]


def test_scoped_story_and_persistent_memory_getters_do_not_cross_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "memory-scope.sqlite3")
    other = gateway.sessions.create_session(
        "demo_workspace",
        1,
        session_id="s_reference_other",
    )
    assert other is not None

    story_memory = gateway.story_memory.create(
        "s_forest001",
        models.StoryMemoryRowValues(
            turn_id=1,
            text="月蚀时石门开启。",
            memory_kind="world_fact",
            epistemic_status="confirmed",
            salience=0.8,
            source_turn_start=1,
            source_turn_end=1,
            dedupe_key="a" * 64,
            dream_processed=False,
            metadata_schema_version=1,
            metadata_json="{}",
            version=1,
        ),
    )
    assert (
        gateway.story_memory.get_for_session(
            "s_forest001",
            story_memory.id,
        )
        == story_memory
    )
    assert (
        gateway.story_memory.get_for_session(other.id, story_memory.id)
        is None
    )
    locator = _locator()
    with gateway.story_memory.transaction():
        gateway.story_memory.require_reference_scope(locator)
        story_page = gateway.story_memory.list_reference_page(
            locator,
            page=1,
            page_size=8,
            memory_kind=None,
            dream_processed=None,
        )
        assert story_page.items == (story_memory,)
        assert (
            gateway.story_memory.get_reference(locator, story_memory.id)
            == story_memory
        )
    wrong_story = _locator(story_id=2)
    with gateway.story_memory.transaction():
        with pytest.raises(FileNotFoundError):
            gateway.story_memory.require_reference_scope(wrong_story)
        assert (
            gateway.story_memory.get_reference(wrong_story, story_memory.id)
            is None
        )

    persistent = gateway.dream_memory.create_memory(
        models.PersistentMemoryCreateValues(
            id="reference-memory",
            session_id="s_forest001",
            dedupe_key="b" * 64,
            lifecycle="active",
            current_revision_number=1,
            superseded_by_memory_id=None,
            created_from_proposal_id=None,
        )
    )
    gateway.dream_memory.create_revision(
        models.PersistentMemoryRevisionCreateValues(
            memory_id=persistent.id,
            revision_number=1,
            text="石门在月蚀时开启。",
            memory_kind="world_fact",
            epistemic_status="confirmed",
            salience=0.8,
            source_proposal_id=None,
            evidence=(),
        )
    )
    gateway.dream_memory.create_revision(
        models.PersistentMemoryRevisionCreateValues(
            memory_id=persistent.id,
            revision_number=2,
            text="石门只在月蚀到达中天时开启。",
            memory_kind="world_fact",
            epistemic_status="confirmed",
            salience=0.9,
            source_proposal_id=None,
            evidence=(),
        )
    )
    gateway.dream_memory.update_memory(
        persistent.id,
        models.PersistentMemoryRowUpdate(
            lifecycle="active",
            current_revision_number=2,
            superseded_by_memory_id=None,
            version=2,
        ),
        expected_version=1,
    )

    statements: list[str] = []
    original_execute_sql = gateway.database.execute_sql

    def _tracked_execute_sql(sql: str, *args: object, **kwargs: object):
        statements.append(sql)
        return original_execute_sql(sql, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(gateway.database, "execute_sql", _tracked_execute_sql)
        current = gateway.dream_memory.list_current_memories(
            "s_forest001",
            lifecycle="active",
        )
    target = next(item for item in current if item.memory.id == persistent.id)
    assert target.current_revision.revision_number == 2
    assert [item.revision_number for item in target.revisions] == [2]
    assert sum(sql.lstrip().upper().startswith("SELECT") for sql in statements) == 3

    scoped = gateway.dream_memory.get_memory_for_session(
        "s_forest001",
        persistent.id,
    )
    assert scoped is not None
    assert [item.revision_number for item in scoped.revisions] == [1, 2]
    current_scoped = gateway.dream_memory.get_current_memory_for_session(
        "s_forest001",
        persistent.id,
    )
    assert current_scoped is not None
    assert current_scoped.current_revision.revision_number == 2
    assert [item.revision_number for item in current_scoped.revisions] == [2]
    assert gateway.dream_memory.get_for_session(other.id, persistent.id) is None
    assert (
        gateway.dream_memory.get_current_memory_for_session(
            other.id,
            persistent.id,
        )
        is None
    )
    with gateway.dream_memory.transaction():
        gateway.dream_memory.require_reference_scope(locator)
        reference_current = (
            gateway.dream_memory.list_current_reference_memories(
                locator,
                lifecycle="active",
            )
        )
        assert [item.memory.id for item in reference_current] == [
            persistent.id
        ]
        reference_detail = (
            gateway.dream_memory.get_current_reference_memory(
                locator,
                persistent.id,
            )
        )
        assert reference_detail is not None
        assert reference_detail.current_revision.revision_number == 2
    with gateway.dream_memory.transaction():
        with pytest.raises(FileNotFoundError):
            gateway.dream_memory.require_reference_scope(wrong_story)
        assert (
            gateway.dream_memory.get_current_reference_memory(
                wrong_story,
                persistent.id,
            )
            is None
        )


def test_memory_reference_scope_rejects_deleted_session_recreated_in_other_story(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "memory-recreated.sqlite3")
    old_locator = _locator()
    story_memory = gateway.story_memory.create(
        old_locator.session_id,
        models.StoryMemoryRowValues(
            turn_id=1,
            text="旧会话事实。",
            memory_kind="event",
            epistemic_status="confirmed",
            salience=0.5,
            source_turn_start=1,
            source_turn_end=1,
            dedupe_key="c" * 64,
            dream_processed=False,
            metadata_schema_version=1,
            metadata_json="{}",
            version=1,
        ),
    )
    persistent = gateway.dream_memory.create_memory(
        models.PersistentMemoryCreateValues(
            id="recreated-reference-memory",
            session_id=old_locator.session_id,
            dedupe_key="d" * 64,
            lifecycle="active",
            current_revision_number=1,
            superseded_by_memory_id=None,
            created_from_proposal_id=None,
        )
    )
    gateway.dream_memory.create_revision(
        models.PersistentMemoryRevisionCreateValues(
            memory_id=persistent.id,
            revision_number=1,
            text="旧会话长期事实。",
            memory_kind="world_fact",
            epistemic_status="confirmed",
            salience=0.7,
            source_proposal_id=None,
            evidence=(),
        )
    )

    assert gateway.sessions.delete_session(old_locator.session_id)
    recreated = gateway.sessions.create_session(
        "demo_workspace",
        2,
        session_id=old_locator.session_id,
        title="同 ID 新 Story",
    )
    assert recreated is not None
    new_locator = _locator(story_id=2)

    with gateway.story_memory.transaction():
        with pytest.raises(FileNotFoundError):
            gateway.story_memory.require_reference_scope(old_locator)
        assert (
            gateway.story_memory.get_reference(old_locator, story_memory.id)
            is None
        )
        gateway.story_memory.require_reference_scope(new_locator)
        assert (
            gateway.story_memory.list_reference_page(
                new_locator,
                page=1,
                page_size=8,
                memory_kind=None,
                dream_processed=None,
            ).items
            == ()
        )

    with gateway.dream_memory.transaction():
        with pytest.raises(FileNotFoundError):
            gateway.dream_memory.require_reference_scope(old_locator)
        assert (
            gateway.dream_memory.get_current_reference_memory(
                old_locator,
                persistent.id,
            )
            is None
        )
        gateway.dream_memory.require_reference_scope(new_locator)
        assert (
            gateway.dream_memory.list_current_reference_memories(
                new_locator,
                lifecycle="active",
            )
            == ()
        )
