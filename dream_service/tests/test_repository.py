from __future__ import annotations

import pytest

from dream_service.repository import RPGDataDreamRepository
from rpg_data import models
from rpg_data.services.dream_memory import DreamProposalStaleError
from rpg_data.services.gateway import get_data_service_gateway, reset_data_service_gateways
from rp_memory.dream.source import DreamSourceSelector
from rp_memory.dream.types import (
    DreamDepth,
    DreamFact,
    DreamProposalAction,
    DreamProposalItemDraft,
    DreamScope,
)


def test_repository_snapshot_proposal_apply_boundary(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream.sqlite3")
    workspace_root = tmp_path / "workspace"
    gateway.database.execute_sql(
        "UPDATE rpg_workspaces SET root_path = ? WHERE id = 'demo_workspace'",
        (str(workspace_root),),
    )
    session = gateway.catalog.create_session("demo_workspace", 1, title="dream")
    assert session is not None
    first = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "阿澈抵达月光港。",
        turn_id=1,
        seq_in_turn=1,
    )
    second = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        "守卫把铜钥匙交给阿澈。",
        turn_id=1,
        seq_in_turn=2,
    )
    gateway.messages.mark_summary_processed(
        session.id,
        (first.id, second.id),
        batch_id=0,
    )
    story_memory = gateway.story_memory.add_details_and_mark_processed(
        session.id,
        ({
            "text": "阿澈得到守卫交付的铜钥匙。",
            "turn_id": 1,
            "source_turn_start": 1,
            "source_turn_end": 1,
            "memory_kind": "clue",
            "salience": 0.8,
            "evidence_message_ids": [second.id],
        },),
        message_ids=(first.id, second.id),
    )[0]
    role = gateway.session_roles.list_options(session.id)[0]
    gateway.session_roles.bind_player_character(
        session.id,
        role.snapshot.character_id,
    )
    summary_dir = gateway.catalog.resolve_session_runtime_dir(session.id) / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "000-arrival.md").write_text(
        "---\nbatch_id: 0\nsource_turn_start: 1\nsource_turn_end: 1\n"
        f"source_message_ids:\n  - {first.id}\n  - {second.id}\n---\n\n"
        "阿澈抵达港口并取得铜钥匙。\n",
        encoding="utf-8",
    )

    repository = RPGDataDreamRepository(gateway)
    snapshot = repository.build_source_snapshot(session.id)
    selection = DreamSourceSelector().select(
        snapshot,
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.FULL,
    )
    assert selection.source_story_memory_ids == (story_memory.id,)
    story_source = snapshot.story_memories[0]
    assert story_source.evidence_message_ids == (second.id,)
    assert story_source.fingerprint.endswith(f":{second.id}")
    assert snapshot.player_character_name == role.snapshot.name
    assert selection.batches[0].player_character_name == role.snapshot.name
    assert {source.source_id for source in snapshot.summary_batches} == {"0"}
    summary_source = snapshot.summary_batches[0]
    assert (summary_source.source_turn_start, summary_source.source_turn_end) == (1, 1)
    assert summary_source.evidence_message_ids == (first.id, second.id)

    proposal = repository.create_proposal(selection)
    assert proposal.status == "generating"
    assert repository.list_proposals(session.id).items[0].proposal_id == proposal.proposal_id
    ready = repository.set_proposal_ready(
        proposal.proposal_id,
        (
            DreamProposalItemDraft(
                action=DreamProposalAction.ADD,
                target_memory_id=None,
                fact=DreamFact(
                    text="守卫把铜钥匙交给阿澈。",
                    memory_kind="clue",
                    epistemic_status="confirmed",
                    salience=0.8,
                    dedupe_key="guard-key-transfer",
                ),
                evidence=(
                    next(
                        message.evidence
                        for message in snapshot.messages
                        if message.message_id == second.id
                    ),
                ),
                reason="这是会持续影响后续探索的关键线索。",
            ),
        ),
    )
    assert ready.status == "ready"
    assert ready.items[0].reason == "这是会持续影响后续探索的关键线索。"

    applied = repository.apply_proposal(session.id, proposal.proposal_id)
    memories = repository.list_memories(session.id)
    assert applied.status == "applied"
    assert repository.list_proposals(session.id).items[0].status == "applied"
    assert memories.active_count == 1
    assert memories.active_limit == gateway.dream.max_active_memories
    assert memories.items[0].current_revision.text == "守卫把铜钥匙交给阿澈。"
    assert memories.items[0].evidence[0].message_id == second.id
    assert gateway.story_memory.get(story_memory.id).dream_processed is True

    gateway.close()
    reset_data_service_gateways()


def test_apply_rolls_back_and_marks_stale_when_source_changes_during_apply(
    tmp_path,
    monkeypatch,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream.sqlite3")
    workspace_root = tmp_path / "workspace"
    gateway.database.execute_sql(
        "UPDATE rpg_workspaces SET root_path = ? WHERE id = 'demo_workspace'",
        (str(workspace_root),),
    )
    session = gateway.catalog.create_session("demo_workspace", 1, title="dream")
    assert session is not None
    user = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "阿澈抵达月光港。",
        turn_id=1,
        seq_in_turn=1,
    )
    assistant = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        "守卫把铜钥匙交给阿澈。",
        turn_id=1,
        seq_in_turn=2,
    )
    gateway.messages.mark_summary_processed(
        session.id,
        (user.id, assistant.id),
        batch_id=0,
    )
    summary_dir = gateway.catalog.resolve_session_runtime_dir(session.id) / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / "000-arrival.md"

    def write_summary(body: str) -> None:
        summary_path.write_text(
            "---\nbatch_id: 0\nsource_turn_start: 1\nsource_turn_end: 1\n"
            f"source_message_ids:\n  - {user.id}\n  - {assistant.id}\n---\n\n"
            f"{body}\n",
            encoding="utf-8",
        )

    write_summary("阿澈抵达港口并取得铜钥匙。")
    repository = RPGDataDreamRepository(gateway)
    snapshot = repository.build_source_snapshot(session.id)
    selection = DreamSourceSelector().select(
        snapshot,
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.FULL,
    )
    proposal = repository.create_proposal(selection)
    repository.set_proposal_ready(
        proposal.proposal_id,
        (
            DreamProposalItemDraft(
                action=DreamProposalAction.ADD,
                target_memory_id=None,
                fact=DreamFact(
                    text="守卫把铜钥匙交给阿澈。",
                    memory_kind="clue",
                    epistemic_status="confirmed",
                    salience=0.8,
                ),
                evidence=(
                    next(
                        message.evidence
                        for message in snapshot.messages
                        if message.message_id == assistant.id
                    ),
                ),
                reason="关键线索。",
            ),
        ),
    )

    original_build = repository.build_source_snapshot
    apply_snapshot_calls = 0

    def build_with_concurrent_source_change(session_id: str):  # noqa: ANN202
        nonlocal apply_snapshot_calls
        apply_snapshot_calls += 1
        if apply_snapshot_calls == 2:
            write_summary("阿澈抵达港口并取得一把已生锈的铜钥匙。")
        return original_build(session_id)

    monkeypatch.setattr(
        repository,
        "build_source_snapshot",
        build_with_concurrent_source_change,
    )
    with pytest.raises(
        DreamProposalStaleError,
        match="sources changed during proposal apply",
    ):
        repository.apply_proposal(session.id, proposal.proposal_id)

    stored = repository.get_proposal(session.id, proposal.proposal_id)
    assert stored is not None
    assert stored.status == "stale"
    assert repository.list_memories(session.id).active_count == 0
    assert apply_snapshot_calls == 2

    gateway.close()
    reset_data_service_gateways()


def test_repository_filters_ooc_and_unsourced_old_summary(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="dream")
    assert session is not None
    gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "模型配置怎么改？",
        mode=models.TURN_MODE_OOC,
        turn_id=1,
        seq_in_turn=1,
    )
    runtime = gateway.catalog.resolve_session_runtime_dir(session.id)
    summary_dir = runtime / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "000-legacy.md").write_text(
        "---\nbatch_id: 0\n---\n\n没有来源范围的旧摘要。\n",
        encoding="utf-8",
    )

    snapshot = RPGDataDreamRepository(gateway).build_source_snapshot(session.id)
    selection = DreamSourceSelector().select(
        snapshot,
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.FULL,
    )
    assert snapshot.summary_batches == ()
    assert selection.batches == ()

    gateway.close()
    reset_data_service_gateways()


def test_repository_rejects_legacy_summary_after_partial_batch_edit(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="dream")
    assert session is not None
    original_user = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "阿澈抵达旧港。",
        turn_id=1,
        seq_in_turn=1,
    )
    original_assistant = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        "守卫交出旧钥匙。",
        turn_id=1,
        seq_in_turn=2,
    )
    gateway.messages.mark_summary_processed(
        session.id,
        (original_user.id, original_assistant.id),
        batch_id=0,
    )
    summary_dir = gateway.catalog.resolve_session_runtime_dir(session.id) / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "000-stale.md").write_text(
        "---\nbatch_id: 0\nsource_turn_start: 1\nsource_turn_end: 1\n---\n\n"
        "阿澈取得旧钥匙。\n",
        encoding="utf-8",
    )

    edited = gateway.messages.update(original_user.id, content="阿澈抵达新港。")
    assert edited is not None
    assert edited.summary_batch_id is None
    assert gateway.messages.get(original_assistant.id).summary_batch_id == 0

    snapshot = RPGDataDreamRepository(gateway).build_source_snapshot(session.id)
    assert snapshot.summary_batches == ()

    gateway.close()
    reset_data_service_gateways()


def test_repository_preserves_valid_evidence_without_rebinding_replacement(
    tmp_path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="dream")
    assert session is not None
    original_user = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "阿澈抵达旧港。",
        turn_id=1,
        seq_in_turn=1,
    )
    assistant = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        "守卫交出旧钥匙。",
        turn_id=1,
        seq_in_turn=2,
    )
    story_memory = gateway.story_memory.add_details_and_mark_processed(
        session.id,
        ({
            "text": "阿澈取得旧钥匙。",
            "turn_id": 1,
            "evidence_message_ids": [original_user.id, assistant.id],
        },),
        message_ids=(original_user.id, assistant.id),
    )[0]
    repository = RPGDataDreamRepository(gateway)
    before = repository.build_source_snapshot(session.id)
    assert before.story_memories[0].evidence_message_ids == (
        original_user.id,
        assistant.id,
    )

    assert gateway.messages.delete(original_user.id)
    replacement = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "阿澈抵达新港。",
        turn_id=1,
        seq_in_turn=1,
    )
    after = repository.build_source_snapshot(session.id)
    source = next(
        item for item in after.story_memories if item.source_id == str(story_memory.id)
    )
    assert replacement.id != original_user.id
    assert source.evidence_message_ids == (assistant.id,)
    selection = DreamSourceSelector().select(
        after,
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.FULL,
    )
    assert selection.source_story_memory_ids == (story_memory.id,)
    assert selection.batches
    proposal = repository.create_proposal(selection)
    repository.set_proposal_ready(
        proposal.proposal_id,
        (
            DreamProposalItemDraft(
                action=DreamProposalAction.ADD,
                target_memory_id=None,
                fact=DreamFact(
                    text="守卫交出的旧钥匙仍由阿澈持有。",
                    memory_kind="clue",
                    epistemic_status="confirmed",
                    salience=0.7,
                ),
                evidence=(
                    next(
                        message.evidence
                        for message in after.messages
                        if message.message_id == assistant.id
                    ),
                ),
            ),
        ),
    )

    refreshed_story_memory = gateway.story_memory.add_details_and_mark_processed(
        session.id,
        ({
            "text": "阿澈取得旧钥匙。",
            "turn_id": 1,
            "evidence_message_ids": [replacement.id, assistant.id],
        },),
        message_ids=(replacement.id, assistant.id),
    )[0]
    refreshed = repository.build_source_snapshot(session.id)
    refreshed_source = next(
        item
        for item in refreshed.story_memories
        if item.source_id == str(story_memory.id)
    )
    assert refreshed_story_memory.id == story_memory.id
    assert refreshed_story_memory.version == story_memory.version + 1
    assert refreshed_source.evidence_message_ids == (replacement.id, assistant.id)
    with pytest.raises(DreamProposalStaleError):
        repository.apply_proposal(session.id, proposal.proposal_id)

    gateway.close()
    reset_data_service_gateways()
