from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from rpg_data import models
from rpg_data.errors import DataConditionalWriteError, DataIntegrityError
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways
from rpg_data.transaction import DataTransactionMode


@pytest.fixture(autouse=True)
def _reset_gateways(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setenv(
        "RPG_WORLD_WORKSPACE_ROOT_BASE",
        str(tmp_path / "workspaces"),
    )
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _story_values(
    *,
    dedupe_key: str,
    text: str = "石门在月蚀时开启。",
    version: int = 1,
) -> models.StoryMemoryRowValues:
    return models.StoryMemoryRowValues(
        turn_id=1,
        text=text,
        memory_kind="world_fact",
        epistemic_status="confirmed",
        salience=0.8,
        source_turn_start=1,
        source_turn_end=1,
        dedupe_key=dedupe_key,
        dream_processed=False,
        metadata_schema_version=1,
        metadata_json='{"source":"test"}',
        version=version,
    )


def _proposal_values(
    proposal_id: str,
    *,
    status: str = "generating",
) -> models.DreamProposalCreateValues:
    return models.DreamProposalCreateValues(
        id=proposal_id,
        session_id="s_forest001",
        depth="shallow",
        scope="incremental",
        status=status,
        history_fingerprint="a" * 64,
        source_fingerprint="b" * 64,
        ledger_revision=0,
        next_messages_manifest_json="{}",
        next_story_memories_manifest_json="{}",
        next_summary_batches_manifest_json="{}",
        source_story_memory_ids=(),
    )


def test_story_memory_crud_evidence_progress_and_rollback(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "story-memory-data.sqlite3")
    data = gateway.story_memory
    source = gateway.messages.append(
        "s_forest001",
        models.MESSAGE_ROLE_ASSISTANT,
        "石门只会在月蚀时开启。",
        mode=models.TURN_MODE_IC,
        turn_id=50,
        seq_in_turn=1,
    )
    evidence = models.MemoryEvidence(
        message_id=source.id,
        turn_id=source.turn_id,
        message_version=source.version,
        content_hash=_content_hash(source.content),
    )
    key = "1" * 64

    created = data.create("s_forest001", _story_values(dedupe_key=key))
    with data.transaction(DataTransactionMode.IMMEDIATE):
        data.replace_evidence(created.id, (evidence,))
        assert data.mark_messages_processed("s_forest001", (source.id,)) == 1

    loaded = data.get(created.id)
    assert loaded is not None
    assert loaded.evidence == (evidence,)
    assert gateway.messages.get(source.id).story_memory_processed is True

    updated = data.update(
        created.id,
        _story_values(
            dedupe_key=key,
            text="石门会在月蚀到达中天时开启。",
            version=2,
        ),
        expected_version=1,
    )
    assert updated.version == 2
    assert data.list_page(
        "s_forest001",
        page=1,
        page_size=10,
        memory_kind="world_fact",
        dream_processed=False,
    ).items == (updated,)
    with pytest.raises(DataConditionalWriteError):
        data.update(
            created.id,
            _story_values(dedupe_key=key, version=3),
            expected_version=1,
        )

    rollback_source = gateway.messages.append(
        "s_forest001",
        models.MESSAGE_ROLE_USER,
        "我记下了石门开启条件。",
        mode=models.TURN_MODE_IC,
        turn_id=51,
        seq_in_turn=1,
    )
    rollback_key = "2" * 64
    with pytest.raises(RuntimeError, match="rollback"):
        with data.transaction(DataTransactionMode.IMMEDIATE):
            row = data.create(
                "s_forest001",
                _story_values(dedupe_key=rollback_key),
            )
            data.replace_evidence(
                row.id,
                (
                    models.MemoryEvidence(
                        message_id=rollback_source.id,
                        turn_id=rollback_source.turn_id,
                        message_version=rollback_source.version,
                        content_hash=_content_hash(rollback_source.content),
                    ),
                ),
            )
            data.mark_messages_processed(
                "s_forest001",
                (rollback_source.id,),
            )
            raise RuntimeError("rollback")

    assert data.get_by_dedupe_key("s_forest001", rollback_key) is None
    assert gateway.messages.get(rollback_source.id).story_memory_processed is False


def test_dream_proposal_item_state_crud_and_conditional_updates(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-proposal-data.sqlite3")
    data = gateway.dream_memory
    source = gateway.messages.list("s_forest001")[0]
    evidence = models.MemoryEvidence(
        message_id=source.id,
        turn_id=source.turn_id,
        message_version=source.version,
        content_hash=_content_hash(source.content),
    )

    proposal = data.create_proposal(_proposal_values("proposal-a"))
    with pytest.raises(DataIntegrityError):
        data.create_proposal(_proposal_values("proposal-b"))

    data.replace_proposal_items(
        proposal.id,
        (
            models.DreamProposalItemRowValues(
                id="item-a",
                action="add",
                dedupe_key="3" * 64,
                selected=True,
                text="Alice 持有铜钥匙。",
                memory_kind="clue",
                epistemic_status="confirmed",
                salience=0.7,
                reason="",
                target_memory_id=None,
                base_revision_number=None,
                sort_order=0,
                evidence=(evidence,),
            ),
        ),
    )
    loaded = data.get_proposal(proposal.id)
    assert loaded is not None
    assert loaded.items[0].evidence[0].message_id == source.id

    ready = data.update_proposal(
        proposal.id,
        models.DreamProposalRowUpdate(
            status="ready",
            error_code="",
            error_message="",
            version=2,
            set_finished_at=True,
        ),
        expected_status="generating",
        expected_version=1,
    )
    assert ready.status == "ready"
    assert ready.version == 2
    with pytest.raises(DataConditionalWriteError):
        data.update_proposal(
            proposal.id,
            models.DreamProposalRowUpdate(
                status="failed",
                error_code="test",
                error_message="stale write",
                version=3,
            ),
            expected_status="generating",
            expected_version=1,
        )

    state = data.get_or_create_state("s_forest001")
    changed_state = data.update_state(
        "s_forest001",
        models.DreamStateRowValues(
            ledger_revision=1,
            messages_manifest_json='{"m":1}',
            story_memories_manifest_json="{}",
            summary_batches_manifest_json="{}",
            version=2,
        ),
        expected_version=state.version,
    )
    assert changed_state.ledger_revision == 1
    with pytest.raises(DataConditionalWriteError):
        data.update_state(
            "s_forest001",
            models.DreamStateRowValues(
                ledger_revision=2,
                messages_manifest_json="{}",
                story_memories_manifest_json="{}",
                summary_batches_manifest_json="{}",
                version=3,
            ),
            expected_version=state.version,
        )


def test_persistent_memory_data_crud_uniqueness_and_audit_evidence(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "persistent-memory-data.sqlite3")
    data = gateway.dream_memory
    source = gateway.messages.append(
        "s_forest001",
        models.MESSAGE_ROLE_ASSISTANT,
        "Alice 接过铜钥匙。",
        mode=models.TURN_MODE_IC,
        turn_id=60,
        seq_in_turn=1,
    )
    evidence = models.MemoryEvidence(
        message_id=source.id,
        turn_id=source.turn_id,
        message_version=source.version,
        content_hash=_content_hash(source.content),
    )
    key = "4" * 64
    memory = data.create_memory(
        models.PersistentMemoryCreateValues(
            id="memory-a",
            session_id="s_forest001",
            dedupe_key=key,
            lifecycle="active",
            current_revision_number=1,
            superseded_by_memory_id=None,
            created_from_proposal_id=None,
        )
    )
    revision = data.create_revision(
        models.PersistentMemoryRevisionCreateValues(
            memory_id=memory.id,
            revision_number=1,
            text="Alice 持有铜钥匙。",
            memory_kind="clue",
            epistemic_status="confirmed",
            salience=0.8,
            source_proposal_id=None,
            evidence=(evidence,),
        )
    )
    assert revision.evidence[0].message_id == source.id
    bundle = data.get_memory(memory.id)
    assert bundle is not None
    assert bundle.current_revision == revision
    assert data.get_memory_by_dedupe_key("s_forest001", key) == bundle

    with pytest.raises(DataIntegrityError):
        data.create_memory(
            models.PersistentMemoryCreateValues(
                id="memory-duplicate",
                session_id="s_forest001",
                dedupe_key=key,
                lifecycle="retired",
                current_revision_number=1,
                superseded_by_memory_id=None,
                created_from_proposal_id=None,
            )
        )
    with pytest.raises(DataIntegrityError):
        data.create_revision(
            models.PersistentMemoryRevisionCreateValues(
                memory_id=memory.id,
                revision_number=1,
                text="重复 revision。",
                memory_kind="event",
                epistemic_status="confirmed",
                salience=0.5,
                source_proposal_id=None,
                evidence=(evidence,),
            )
        )

    retired = data.update_memory(
        memory.id,
        models.PersistentMemoryRowUpdate(
            lifecycle="retired",
            current_revision_number=1,
            superseded_by_memory_id=None,
            version=2,
        ),
        expected_version=1,
    )
    assert retired.lifecycle == "retired"
    with pytest.raises(DataConditionalWriteError):
        data.update_memory(
            memory.id,
            models.PersistentMemoryRowUpdate(
                lifecycle="active",
                current_revision_number=1,
                superseded_by_memory_id=None,
                version=3,
            ),
            expected_version=1,
        )

    assert gateway.messages.delete(source.id) is True
    audited = data.get_memory(memory.id)
    assert audited is not None
    assert audited.current_revision.evidence[0].message_id == source.id


def test_dream_rows_rollback_clear_and_session_delete_cascade(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-cleanup-data.sqlite3")
    data = gateway.dream_memory

    with pytest.raises(RuntimeError, match="rollback"):
        with data.transaction(DataTransactionMode.IMMEDIATE):
            data.create_proposal(
                _proposal_values("rolled-back", status="failed")
            )
            raise RuntimeError("rollback")
    assert data.get_proposal("rolled-back") is None

    data.create_proposal(_proposal_values("clear-me", status="failed"))
    data.get_or_create_state("s_forest001")
    cleared = data.clear("s_forest001")
    assert cleared.proposals_cleared == 1
    assert cleared.states_cleared == 1
    assert data.list_proposals("s_forest001") == ()

    session = gateway.catalog.create_session(
        "demo_workspace",
        1,
        title="Dream cascade",
    )
    assert session is not None
    proposal_values = _proposal_values("cascade-proposal", status="failed")
    data.create_proposal(replace(proposal_values, session_id=session.id))
    data.get_or_create_state(session.id)

    assert gateway.sessions.delete_session(session.id) is True
    assert data.get_proposal("cascade-proposal") is None
    assert data.get_state(session.id) is None
