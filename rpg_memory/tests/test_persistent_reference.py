from __future__ import annotations

from contextlib import contextmanager

import pytest

from rpg_data.model import memory as models
from rpg_data.model.session import SessionMessage
from rpg_data.model.session_reference import SessionReferenceLocator
from rpg_data.services import get_data_service_gateway
from rpg_memory.dream.source_identity import content_hash
from rpg_memory.persistent.reference import PersistentMemoryReferenceService


SESSION_ID = "s_reference"
LOCATOR = SessionReferenceLocator(
    session_id=SESSION_ID,
    workspace_id="workspace",
    story_id=7,
)


def _bundle(
    memory_id: str,
    *,
    message_id: int,
    text: str,
    kind: str,
    lifecycle: str = "active",
    digest: str,
) -> models.PersistentMemoryBundle:
    evidence = models.PersistentMemoryEvidence(
        id=message_id + 1000,
        revision_id=message_id + 2000,
        message_id=message_id,
        turn_id=message_id,
        message_version=1,
        content_hash=digest,
    )
    revision = models.PersistentMemoryRevision(
        id=message_id + 2000,
        memory_id=memory_id,
        revision_number=2,
        text=text,
        memory_kind=kind,
        epistemic_status="confirmed",
        salience=0.8,
        evidence=(evidence,),
    )
    return models.PersistentMemoryBundle(
        memory=models.PersistentMemory(
            id=memory_id,
            session_id=SESSION_ID,
            dedupe_key=memory_id,
            lifecycle=lifecycle,
            current_revision_number=2,
            updated_at=f"updated-{memory_id}",
        ),
        current_revision=revision,
        revisions=(
            models.PersistentMemoryRevision(
                id=message_id + 1999,
                memory_id=memory_id,
                revision_number=1,
                text="旧版本不得投影",
                memory_kind=kind,
                epistemic_status="confirmed",
                salience=0.5,
            ),
            revision,
        ),
    )


class FakePersistentData:
    def __init__(self) -> None:
        self.messages = {
            1: SessionMessage(
                id=1,
                session_id=SESSION_ID,
                role="assistant",
                mode="neutral",
                content="角色事实来源",
                turn_id=1,
                seq_in_turn=2,
                version=1,
            ),
            2: SessionMessage(
                id=2,
                session_id=SESSION_ID,
                role="assistant",
                mode="neutral",
                content="世界事实来源",
                turn_id=2,
                seq_in_turn=2,
                version=1,
            ),
        }
        self.bundles = (
            _bundle(
                "world",
                message_id=2,
                text="北境处于永夜。",
                kind="world_fact",
                digest=content_hash("世界事实来源"),
            ),
            _bundle(
                "character",
                message_id=1,
                text="林晚来自北境。",
                kind="character",
                digest=content_hash("角色事实来源"),
            ),
            _bundle(
                "invalid",
                message_id=3,
                text="证据已失效。",
                kind="event",
                digest="0" * 64,
            ),
        )
        self.requested_message_ids: list[tuple[int, ...]] = []
        self.transaction_entries = 0

    @contextmanager
    def transaction(self, _mode=None):  # noqa: ANN001, ANN201
        self.transaction_entries += 1
        yield

    def require_reference_scope(self, locator):  # noqa: ANN001, ANN201
        if locator != LOCATOR:
            raise FileNotFoundError

    def list_current_reference_memories(
        self,
        locator,
        *,
        lifecycle=None,
    ):  # noqa: ANN001, ANN201
        self.require_reference_scope(locator)
        return tuple(
            models.PersistentMemoryBundle(
                memory=item.memory,
                current_revision=item.current_revision,
                revisions=(item.current_revision,),
            )
            for item in self.bundles
            if item.memory.session_id == locator.session_id
            and (lifecycle is None or item.memory.lifecycle == lifecycle)
        )

    def get_current_reference_memory(
        self,
        locator,
        memory_id,
    ):  # noqa: ANN001, ANN201
        self.require_reference_scope(locator)
        item = next(
            (
                item
                for item in self.bundles
                if item.memory.session_id == locator.session_id
                and item.memory.id == memory_id
            ),
            None,
        )
        if item is None:
            return None
        return models.PersistentMemoryBundle(
            memory=item.memory,
            current_revision=item.current_revision,
            revisions=(item.current_revision,),
        )

    def list_reference_messages(
        self,
        locator,
        *,
        message_ids,
    ):  # noqa: ANN001, ANN201
        assert locator == LOCATOR
        requested = tuple(message_ids or ())
        self.requested_message_ids.append(requested)
        return tuple(
            self.messages[item]
            for item in requested
            if item in self.messages
        )


def test_persistent_reference_projects_active_valid_current_revisions_only() -> None:
    data = FakePersistentData()
    service = PersistentMemoryReferenceService(data)

    items = service.list_memories(LOCATOR)

    assert [item.memory_id for item in items] == ["character", "world"]
    assert [item.text for item in items] == [
        "林晚来自北境。",
        "北境处于永夜。",
    ]
    assert items[0].revision_number == 2
    assert items[0].evidence[0].message_id == 1
    assert data.requested_message_ids == [(1, 2, 3)]
    assert data.transaction_entries == 1


def test_persistent_reference_detail_is_scoped_and_loads_only_its_evidence() -> None:
    data = FakePersistentData()
    service = PersistentMemoryReferenceService(data)

    item = service.get_memory(LOCATOR, "world")

    assert item is not None
    assert item.text == "北境处于永夜。"
    assert data.requested_message_ids == [(2,)]
    with pytest.raises(FileNotFoundError):
        service.get_memory(
            SessionReferenceLocator(
                session_id=SESSION_ID,
                workspace_id="other",
                story_id=LOCATOR.story_id,
            ),
            "world",
        )
    assert service.get_memory(LOCATOR, "invalid") is None


def test_persistent_reference_real_snapshot_is_scoped_batched_and_fixed_query(
    tmp_path,
    monkeypatch,
) -> None:  # noqa: ANN001
    gateway = get_data_service_gateway(tmp_path / "persistent-reference.sqlite3")
    session = gateway.sessions.create_session(
        "demo_workspace",
        1,
        session_id=SESSION_ID,
        title="Reference snapshot",
    )
    assert session is not None
    locator = SessionReferenceLocator(
        session_id=session.id,
        workspace_id=session.workspace_id,
        story_id=session.story_id,
    )
    sources = tuple(
        gateway.messages.append(
            session.id,
            "assistant",
            content,
            turn_id=index,
            seq_in_turn=1,
        )
        for index, content in enumerate(
            ("角色事实来源", "世界事实来源"),
            start=1,
        )
    )
    for index, source in enumerate(sources, start=1):
        memory_id = f"reference-{index}"
        gateway.dream_memory.create_memory(
            models.PersistentMemoryCreateValues(
                id=memory_id,
                session_id=session.id,
                dedupe_key=str(index) * 64,
                lifecycle="active",
                current_revision_number=1,
                superseded_by_memory_id=None,
                created_from_proposal_id=None,
            )
        )
        gateway.dream_memory.create_revision(
            models.PersistentMemoryRevisionCreateValues(
                memory_id=memory_id,
                revision_number=1,
                text="旧版本不得读取",
                memory_kind="event",
                epistemic_status="confirmed",
                salience=0.4,
                source_proposal_id=None,
                evidence=(),
            )
        )
        gateway.dream_memory.create_revision(
            models.PersistentMemoryRevisionCreateValues(
                memory_id=memory_id,
                revision_number=2,
                text=f"当前事实 {index}",
                memory_kind="character" if index == 1 else "world_fact",
                epistemic_status="confirmed",
                salience=0.8,
                source_proposal_id=None,
                evidence=(
                    models.MemoryEvidence(
                        message_id=source.id,
                        turn_id=source.turn_id,
                        message_version=source.version,
                        content_hash=content_hash(source.content),
                    ),
                ),
            )
        )
        gateway.dream_memory.update_memory(
            memory_id,
            models.PersistentMemoryRowUpdate(
                lifecycle="active",
                current_revision_number=2,
                superseded_by_memory_id=None,
                version=2,
            ),
            expected_version=1,
        )

    data = gateway.dream_memory
    transaction_entries = 0
    requested_message_ids: list[tuple[int, ...]] = []
    original_transaction = data.transaction
    original_list_messages = data.list_reference_messages
    original_execute_sql = gateway.database.execute_sql
    select_statements: list[str] = []

    @contextmanager
    def tracked_transaction(mode=None):  # noqa: ANN001, ANN202
        nonlocal transaction_entries
        transaction_entries += 1
        if mode is None:
            with original_transaction():
                yield
        else:
            with original_transaction(mode):
                yield

    def tracked_list_messages(locator_arg, *, message_ids):  # noqa: ANN001, ANN202
        requested_message_ids.append(tuple(message_ids))
        return original_list_messages(locator_arg, message_ids=message_ids)

    def tracked_execute_sql(sql, *args, **kwargs):  # noqa: ANN001, ANN202
        if str(sql).lstrip().upper().startswith("SELECT"):
            select_statements.append(str(sql))
        return original_execute_sql(sql, *args, **kwargs)

    monkeypatch.setattr(data, "transaction", tracked_transaction)
    monkeypatch.setattr(data, "list_reference_messages", tracked_list_messages)
    monkeypatch.setattr(gateway.database, "execute_sql", tracked_execute_sql)

    service = PersistentMemoryReferenceService(data)
    items = service.list_memories(locator)

    assert [item.text for item in items] == ["当前事实 1", "当前事实 2"]
    assert all(item.revision_number == 2 for item in items)
    assert requested_message_ids == [
        tuple(sorted(source.id for source in sources))
    ]
    assert transaction_entries == 1
    assert len(select_statements) == 5

    requested_message_ids.clear()
    select_statements.clear()
    detail = service.get_memory(locator, "reference-2")
    assert detail is not None
    assert detail.text == "当前事实 2"
    assert requested_message_ids == [(sources[1].id,)]
    assert transaction_entries == 2
    assert len(select_statements) == 5

    with pytest.raises(FileNotFoundError):
        service.list_memories(
            SessionReferenceLocator(
                session_id=session.id,
                workspace_id="other_workspace",
                story_id=session.story_id,
            )
        )
