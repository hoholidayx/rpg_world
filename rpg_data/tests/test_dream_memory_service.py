from __future__ import annotations

import hashlib

import pytest

from commons.text_identity import stable_text_identity_key
from rpg_data import models
from rpg_data.services import (
    DreamActiveMemoryLimitError,
    DreamEvidenceInvalidError,
    DreamMemoryService,
    DreamProposalConflictError,
    DreamProposalStaleError,
    get_data_service_gateway,
    reset_data_service_gateways,
)
from rpg_data.services.dream_source_identity import story_memory_source_identity


@pytest.fixture(autouse=True)
def _reset_gateways(tmp_path, monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path / "workspaces"))
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def _evidence(message: models.SessionMessage) -> models.DreamEvidenceDraft:
    return models.DreamEvidenceDraft(
        message_id=message.id,
        turn_id=message.turn_id,
        message_version=message.version,
        content_hash=hashlib.sha256(message.content.encode("utf-8")).hexdigest(),
    )


def _create_ready(
    dream: DreamMemoryService,
    session_id: str,
    items: tuple[models.DreamProposalItemDraft, ...],
    *,
    source_fingerprint: str = "f" * 64,
    manifests: bool = False,
) -> models.DreamProposal:
    snapshot = dream.build_source_snapshot(session_id)
    proposal = dream.create_proposal(
        session_id,
        depth=models.DREAM_DEPTH_SHALLOW,
        scope=models.DREAM_SCOPE_INCREMENTAL,
        history_fingerprint=snapshot.history_fingerprint,
        source_fingerprint=source_fingerprint,
        next_messages_manifest_json={"message": 1} if manifests else {},
        next_story_memories_manifest_json={"story": 2} if manifests else {},
        next_summary_batches_manifest_json={"summary": 3} if manifests else {},
    )
    return dream.set_proposal_ready(proposal.id, items)


def test_snapshot_proposal_apply_and_context_evidence_guard(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream.sqlite3")
    dream = gateway.dream
    snapshot = dream.build_source_snapshot("s_forest001")
    message = snapshot.messages[0]

    proposal = dream.create_proposal(
        "s_forest001",
        depth="shallow",
        scope="incremental",
        history_fingerprint=snapshot.history_fingerprint,
        source_fingerprint="f" * 64,
        next_messages_manifest_json={"message": 1},
        next_story_memories_manifest_json={"story": 2},
        next_summary_batches_manifest_json={"summary": 3},
    )
    with pytest.raises(DreamProposalConflictError):
        dream.create_proposal(
            "s_forest001",
            depth="deep",
            scope="full",
            history_fingerprint=snapshot.history_fingerprint,
            source_fingerprint="e" * 64,
        )

    ready = dream.set_proposal_ready(
        proposal.id,
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="a" * 64,
                text="Alice 确认封印仍然完整。",
                memory_kind="world_fact",
                epistemic_status="confirmed",
                salience=0.8,
                evidence=(_evidence(message),),
            ),
        ),
    )
    original_key = ready.items[0].dedupe_key
    assert original_key == stable_text_identity_key(
        "world_fact",
        "confirmed",
        "Alice 确认封印仍然完整。",
    )
    patched = dream.update_proposal_items(
        ready.id,
        (
            models.DreamProposalItemPatch(
                item_id=ready.items[0].id,
                text="Alice 确认石林封印仍然完整。",
                salience=0.9,
            ),
        ),
    )
    assert patched.items[0].dedupe_key == stable_text_identity_key(
        "world_fact",
        "confirmed",
        "Alice 确认石林封印仍然完整。",
    )
    assert patched.items[0].dedupe_key != original_key
    result = dream.apply_proposal(
        patched.id,
        history_fingerprint=snapshot.history_fingerprint,
        source_fingerprint="f" * 64,
    )

    assert result.proposal.status == models.DREAM_PROPOSAL_STATUS_APPLIED
    assert result.active_memory_count == 1
    assert result.ledger_revision == 1
    assert len(result.created_memory_ids) == 1
    context = dream.list_context_memories("s_forest001")
    assert [(item.text, item.memory_kind, item.salience) for item in context] == [
        ("Alice 确认石林封印仍然完整。", "world_fact", 0.9)
    ]
    assert context[0].evidence_valid
    assert dream.get_state("s_forest001").messages_manifest_json == '{"message":1}'

    gateway.messages.update(message.id, content=f"{message.content}（已编辑）")

    assert dream.list_context_memories("s_forest001") == []
    all_rows = dream.list_memories("s_forest001")
    assert len(all_rows) == 1
    assert not all_rows[0].evidence_valid


def test_revision_retire_restore_and_supersede_preserve_history(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-lifecycle.sqlite3")
    dream = gateway.dream
    message = dream.build_source_snapshot("s_forest001").messages[0]
    evidence = (_evidence(message),)
    first = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="a" * 64,
                text="最初事实",
                evidence=evidence,
            ),
        ),
    )
    added = dream.apply_proposal(
        first.id,
        history_fingerprint=first.history_fingerprint,
        source_fingerprint=first.source_fingerprint,
    )
    memory_id = added.created_memory_ids[0]

    revise = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="revise",
                target_memory_id=memory_id,
                base_revision_number=1,
                dedupe_key="a" * 64,
                text="修订事实",
                memory_kind="clue",
                evidence=evidence,
            ),
        ),
    )
    dream.apply_proposal(
        revise.id,
        history_fingerprint=revise.history_fingerprint,
        source_fingerprint=revise.source_fingerprint,
    )
    revised = dream.list_memories("s_forest001")[0]
    assert revised.text == "修订事实"
    assert [item.revision_number for item in revised.revisions] == [1, 2]

    retire = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="retire",
                target_memory_id=memory_id,
                base_revision_number=2,
                dedupe_key="a" * 64,
            ),
        ),
    )
    dream.apply_proposal(
        retire.id,
        history_fingerprint=retire.history_fingerprint,
        source_fingerprint=retire.source_fingerprint,
    )
    assert dream.list_context_memories("s_forest001") == []
    restored = dream.restore_memory("s_forest001", memory_id)
    assert restored.memory.lifecycle == models.DREAM_LIFECYCLE_ACTIVE

    supersede = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="supersede",
                target_memory_id=memory_id,
                base_revision_number=2,
                dedupe_key="b" * 64,
                text="替代事实",
                memory_kind="event",
                evidence=evidence,
            ),
        ),
    )
    result = dream.apply_proposal(
        supersede.id,
        history_fingerprint=supersede.history_fingerprint,
        source_fingerprint=supersede.source_fingerprint,
    )
    rows = dream.list_memories("s_forest001")
    old = next(item for item in rows if item.memory.id == memory_id)
    new = next(item for item in rows if item.memory.id != memory_id)
    assert old.memory.lifecycle == models.DREAM_LIFECYCLE_SUPERSEDED
    assert old.memory.superseded_by_memory_id == new.memory.id
    assert result.active_memory_count == 1
    assert [item.text for item in dream.list_context_memories("s_forest001")] == [
        "替代事实"
    ]


def test_add_revives_retired_memory_with_new_revision_and_evidence(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-revive.sqlite3")
    dream = gateway.dream
    original_message = dream.build_source_snapshot("s_forest001").messages[0]
    fact_text = "封印的石门只会在月蚀时开启。"
    first = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="ignored-by-normalization",
                text=fact_text,
                memory_kind="world_fact",
                evidence=(_evidence(original_message),),
            ),
        ),
    )
    added = dream.apply_proposal(
        first.id,
        history_fingerprint=first.history_fingerprint,
        source_fingerprint=first.source_fingerprint,
    )
    memory_id = added.created_memory_ids[0]
    dedupe_key = stable_text_identity_key("world_fact", "confirmed", fact_text)

    gateway.messages.update(
        original_message.id,
        content=f"{original_message.content}（旧证据已被修订）",
    )
    retire = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="retire",
                target_memory_id=memory_id,
                base_revision_number=1,
                dedupe_key=dedupe_key,
            ),
        ),
    )
    dream.apply_proposal(
        retire.id,
        history_fingerprint=retire.history_fingerprint,
        source_fingerprint=retire.source_fingerprint,
    )
    with pytest.raises(DreamEvidenceInvalidError):
        dream.restore_memory("s_forest001", memory_id)

    new_message = gateway.messages.append(
        "s_forest001",
        models.MESSAGE_ROLE_ASSISTANT,
        fact_text,
        mode=models.TURN_MODE_IC,
        turn_id=99,
        seq_in_turn=1,
    )
    revive = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="also-ignored-by-normalization",
                text=fact_text,
                memory_kind="world_fact",
                evidence=(_evidence(new_message),),
            ),
        ),
    )
    result = dream.apply_proposal(
        revive.id,
        history_fingerprint=revive.history_fingerprint,
        source_fingerprint=revive.source_fingerprint,
    )

    assert result.created_memory_ids == ()
    assert result.revised_memory_ids == (memory_id,)
    assert result.active_memory_count == 1
    assert dream.get_state("s_forest001").ledger_revision == 3
    memories = dream.list_memories("s_forest001")
    assert len(memories) == 1
    revived = memories[0]
    assert revived.memory.id == memory_id
    assert revived.memory.lifecycle == models.DREAM_LIFECYCLE_ACTIVE
    assert revived.memory.current_revision_number == 2
    assert [revision.revision_number for revision in revived.revisions] == [1, 2]
    assert revived.revisions[0].evidence[0].message_id == original_message.id
    assert revived.revisions[1].evidence[0].message_id == new_message.id
    assert revived.evidence_valid


def test_revive_counts_against_active_memory_limit(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-revive-limit.sqlite3")
    dream = DreamMemoryService(gateway.database, max_active_memories=1)
    message = dream.build_source_snapshot("s_forest001").messages[0]
    retired_text = "月蚀会开启石门。"
    first = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="ignored",
                text=retired_text,
                evidence=(_evidence(message),),
            ),
        ),
    )
    memory_id = dream.apply_proposal(
        first.id,
        history_fingerprint=first.history_fingerprint,
        source_fingerprint=first.source_fingerprint,
    ).created_memory_ids[0]
    retire = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="retire",
                target_memory_id=memory_id,
                base_revision_number=1,
                dedupe_key=stable_text_identity_key(
                    "event",
                    "confirmed",
                    retired_text,
                ),
            ),
        ),
    )
    dream.apply_proposal(
        retire.id,
        history_fingerprint=retire.history_fingerprint,
        source_fingerprint=retire.source_fingerprint,
    )
    replacement = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="ignored",
                text="守卫持有唯一的铜钥匙。",
                evidence=(_evidence(message),),
            ),
        ),
    )
    dream.apply_proposal(
        replacement.id,
        history_fingerprint=replacement.history_fingerprint,
        source_fingerprint=replacement.source_fingerprint,
    )
    revive = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="ignored",
                text=retired_text,
                evidence=(_evidence(message),),
            ),
        ),
    )

    with pytest.raises(DreamActiveMemoryLimitError):
        dream.apply_proposal(
            revive.id,
            history_fingerprint=revive.history_fingerprint,
            source_fingerprint=revive.source_fingerprint,
        )

    retired = next(
        item for item in dream.list_memories("s_forest001")
        if item.memory.id == memory_id
    )
    assert retired.memory.lifecycle == models.DREAM_LIFECYCLE_RETIRED
    assert retired.memory.current_revision_number == 1
    assert dream.get_state("s_forest001").ledger_revision == 3
    assert dream.get_proposal(revive.id).status == models.DREAM_PROPOSAL_STATUS_READY


def test_evidence_becomes_invalid_when_message_leaves_in_world_source(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-mode-evidence.sqlite3")
    dream = gateway.dream
    message = dream.build_source_snapshot("s_forest001").messages[0]
    proposal = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="a" * 64,
                text="Alice 确认石林封印仍然完整。",
                evidence=(_evidence(message),),
            ),
        ),
    )
    dream.apply_proposal(
        proposal.id,
        history_fingerprint=proposal.history_fingerprint,
        source_fingerprint=proposal.source_fingerprint,
    )

    updated = gateway.messages.update(message.id, mode=models.TURN_MODE_OOC)

    assert updated is not None
    assert updated.version == message.version + 1
    assert dream.list_context_memories("s_forest001") == []
    assert not dream.list_memories("s_forest001")[0].evidence_valid


def test_context_projection_uses_batched_current_revision_queries(
    tmp_path,
    monkeypatch,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-context-query.sqlite3")
    dream = gateway.dream
    message = dream.build_source_snapshot("s_forest001").messages[0]
    proposal = _create_ready(
        dream,
        "s_forest001",
        tuple(
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key=hashlib.sha256(f"fact-{index}".encode()).hexdigest(),
                text=f"长期事实 {index}",
                evidence=(_evidence(message),),
            )
            for index in range(3)
        ),
    )
    dream.apply_proposal(
        proposal.id,
        history_fingerprint=proposal.history_fingerprint,
        source_fingerprint=proposal.source_fingerprint,
    )

    select_count = 0
    execute_sql = gateway.database.execute_sql

    def counted_execute_sql(sql, params=None):  # noqa: ANN001, ANN202
        nonlocal select_count
        if str(sql).lstrip().upper().startswith("SELECT"):
            select_count += 1
        return execute_sql(sql, params)

    monkeypatch.setattr(gateway.database, "execute_sql", counted_execute_sql)

    context = dream.list_context_memories("s_forest001")

    assert len(context) == 3
    assert select_count == 4
    assert all(len(bundle.revisions) == 1 for bundle in context)


def test_ledger_guard_stales_second_ready_proposal(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-stale.sqlite3")
    dream = gateway.dream
    message = dream.build_source_snapshot("s_forest001").messages[0]
    first = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="a" * 64,
                text="事实 A",
                evidence=(_evidence(message),),
            ),
        ),
    )
    second = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="b" * 64,
                text="事实 B",
                evidence=(_evidence(message),),
            ),
        ),
    )
    dream.apply_proposal(
        first.id,
        history_fingerprint=first.history_fingerprint,
        source_fingerprint=first.source_fingerprint,
    )

    with pytest.raises(DreamProposalStaleError, match="ledger changed"):
        dream.apply_proposal(
            second.id,
            history_fingerprint=second.history_fingerprint,
            source_fingerprint=second.source_fingerprint,
        )

    assert dream.get_proposal(second.id).status == models.DREAM_PROPOSAL_STATUS_STALE


def test_active_limit_and_reset_clear_all_dream_rows(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-limit.sqlite3")
    with pytest.raises(ValueError, match="between 1 and 64"):
        DreamMemoryService(
            gateway.database,
            max_active_memories=models.DREAM_MAX_ACTIVE_MEMORIES + 1,
        )
    dream = DreamMemoryService(gateway.database, max_active_memories=1)
    message = dream.build_source_snapshot("s_forest001").messages[0]
    first = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="a" * 64,
                text="事实 A",
                evidence=(_evidence(message),),
            ),
        ),
    )
    dream.apply_proposal(
        first.id,
        history_fingerprint=first.history_fingerprint,
        source_fingerprint=first.source_fingerprint,
    )
    second = _create_ready(
        dream,
        "s_forest001",
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="b" * 64,
                text="事实 B",
                evidence=(_evidence(message),),
            ),
        ),
    )
    with pytest.raises(DreamActiveMemoryLimitError):
        dream.apply_proposal(
            second.id,
            history_fingerprint=second.history_fingerprint,
            source_fingerprint=second.source_fingerprint,
        )

    result = gateway.session_reset.reset("s_forest001")

    assert result.dream_memories_cleared == 1
    assert result.dream_proposals_cleared == 2
    assert gateway.dream.list_memories("s_forest001") == []
    assert gateway.dream.list_proposals("s_forest001") == []
    assert gateway.dream.get_state("s_forest001").ledger_revision == 0


def test_proposal_payload_limits_are_enforced_at_data_boundary(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-limits.sqlite3")
    dream = gateway.dream
    message = dream.build_source_snapshot("s_forest001").messages[0]
    snapshot = dream.build_source_snapshot("s_forest001")
    proposal = dream.create_proposal(
        "s_forest001",
        depth="shallow",
        scope="full",
        history_fingerprint=snapshot.history_fingerprint,
        source_fingerprint="f" * 64,
    )

    with pytest.raises(ValueError, match="at most 1000 characters"):
        dream.set_proposal_ready(
            proposal.id,
            (
                models.DreamProposalItemDraft(
                    action="add",
                    dedupe_key="a" * 64,
                    text="x" * (models.DREAM_MAX_MEMORY_TEXT_CHARS + 1),
                    evidence=(_evidence(message),),
                ),
            ),
        )

    too_many_evidence = tuple(
        models.DreamEvidenceDraft(
            message_id=index,
            turn_id=1,
            message_version=1,
            content_hash="b" * 64,
        )
        for index in range(1, models.DREAM_MAX_EVIDENCE_PER_ITEM + 2)
    )
    with pytest.raises(ValueError, match="at most 64 evidence"):
        dream.set_proposal_ready(
            proposal.id,
            (
                models.DreamProposalItemDraft(
                    action="add",
                    dedupe_key="b" * 64,
                    text="bounded",
                    evidence=too_many_evidence,
                ),
            ),
        )


def test_apply_advances_story_memory_manifest_but_reject_does_not(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-checkpoint.sqlite3")
    dream = gateway.dream
    story_memory = gateway.story_memory.add_detail(
        "s_forest001",
        "封印发出蓝光",
        turn_id=1,
    )
    snapshot = dream.build_source_snapshot("s_forest001")
    message = snapshot.messages[0]
    story_identity = story_memory_source_identity(
        story_memory,
        {item.id: item for item in snapshot.messages},
    )
    proposal = dream.create_proposal(
        "s_forest001",
        depth="shallow",
        scope="incremental",
        history_fingerprint=snapshot.history_fingerprint,
        source_fingerprint="d" * 64,
        next_story_memories_manifest_json={
            str(story_memory.id): {
                "fingerprint": story_identity.fingerprint,
                "turnStart": story_memory.source_turn_start,
                "turnEnd": story_memory.source_turn_end,
            }
        },
        source_story_memory_ids=(story_memory.id,),
    )
    ready = dream.set_proposal_ready(
        proposal.id,
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="d" * 64,
                text="封印持续发出蓝光。",
                reason="长期有效的世界事实",
                evidence=(_evidence(message),),
            ),
        ),
    )
    dream.apply_proposal(
        ready.id,
        history_fingerprint=ready.history_fingerprint,
        source_fingerprint=ready.source_fingerprint,
    )

    assert gateway.story_memory.get(story_memory.id).dream_processed
    assert str(story_memory.id) in (
        dream.get_state("s_forest001").story_memories_manifest_json
    )
    assert dream.get_proposal(ready.id).items[0].reason == "长期有效的世界事实"

    next_snapshot = dream.build_source_snapshot("s_forest001")
    rejected = dream.create_proposal(
        "s_forest001",
        depth="deep",
        scope="full",
        history_fingerprint=next_snapshot.history_fingerprint,
        source_fingerprint="c" * 64,
    )
    rejected = dream.set_proposal_ready(rejected.id, ())
    dream.reject_proposal(rejected.id)

    assert dream.get_state("s_forest001").ledger_revision == 1
    generating = dream.create_proposal(
        "s_forest001",
        depth="shallow",
        scope="full",
        history_fingerprint=next_snapshot.history_fingerprint,
        source_fingerprint="b" * 64,
    )
    assert dream.interrupt_generating(
        "s_forest001",
        proposal_id="not-the-generating-proposal",
    ) == 0
    assert dream.get_proposal(generating.id).status == (
        models.DREAM_PROPOSAL_STATUS_GENERATING
    )
    assert dream.interrupt_generating(
        "s_forest001",
        proposal_id=generating.id,
    ) == 1
    assert dream.get_proposal(generating.id).status == (
        models.DREAM_PROPOSAL_STATUS_INTERRUPTED
    )


def test_story_memory_checkpoint_does_not_change_source_fingerprint(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-checkpoint-fingerprint.sqlite3")
    story_memory = gateway.story_memory.add_detail(
        "s_forest001",
        "封印发出蓝光",
        turn_id=1,
    )
    before = gateway.dream.build_source_snapshot("s_forest001")

    assert gateway.story_memory.set_dream_processed((story_memory.id,)) == 1

    after = gateway.dream.build_source_snapshot("s_forest001")
    assert gateway.story_memory.get(story_memory.id).dream_processed
    assert after.story_memory_fingerprint == before.story_memory_fingerprint


def test_apply_rechecks_story_memory_version_inside_transaction(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-story-stale.sqlite3")
    dream = gateway.dream
    story = gateway.story_memory.add_detail(
        "s_forest001",
        "封印发出蓝光",
        turn_id=1,
    )
    message = dream.build_source_snapshot("s_forest001").messages[0]
    snapshot = dream.build_source_snapshot("s_forest001")
    story_identity = story_memory_source_identity(
        story,
        {item.id: item for item in snapshot.messages},
    )
    proposal = dream.create_proposal(
        "s_forest001",
        depth="shallow",
        scope="full",
        history_fingerprint=snapshot.history_fingerprint,
        source_fingerprint="f" * 64,
        next_story_memories_manifest_json={
            str(story.id): {
                "fingerprint": story_identity.fingerprint,
                "turnStart": story.source_turn_start,
                "turnEnd": story.source_turn_end,
            }
        },
        source_story_memory_ids=(story.id,),
    )
    ready = dream.set_proposal_ready(
        proposal.id,
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="a" * 64,
                text="封印持续发出蓝光。",
                evidence=(_evidence(message),),
            ),
        ),
    )
    updated = gateway.story_memory.add_detail(
        "s_forest001",
        "封印发出蓝光",
        turn_id=2,
        source_turn_start=1,
        source_turn_end=2,
    )
    assert updated.version == story.version + 1

    with pytest.raises(DreamProposalStaleError, match="story-memory sources changed"):
        dream.apply_proposal(
            ready.id,
            history_fingerprint=ready.history_fingerprint,
            source_fingerprint=ready.source_fingerprint,
        )


def test_session_delete_cascades_dream_ledger_and_audit_rows(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-delete.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="Dream delete")
    message = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "需要被删除的历史",
        turn_id=1,
        seq_in_turn=1,
    )
    proposal = _create_ready(
        gateway.dream,
        session.id,
        (
            models.DreamProposalItemDraft(
                action="add",
                dedupe_key="a" * 64,
                text="需要被删除的事实",
                evidence=(_evidence(message),),
            ),
        ),
    )
    gateway.dream.apply_proposal(
        proposal.id,
        history_fingerprint=proposal.history_fingerprint,
        source_fingerprint=proposal.source_fingerprint,
    )

    result = gateway.session_deletion.delete(session.id)

    assert result is not None
    assert gateway.dream.get_proposal(proposal.id) is None
    for table in (
        "rpg_session_dream_proposals",
        "rpg_session_persistent_memories",
        "rpg_session_persistent_memory_revisions",
        "rpg_session_persistent_memory_evidence",
        "rpg_session_dream_states",
    ):
        count = gateway.database.execute_sql(
            f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - fixed test table names
        ).fetchone()[0]
        if table in {
            "rpg_session_persistent_memory_revisions",
            "rpg_session_persistent_memory_evidence",
        }:
            assert count == 0
        else:
            assert count == 0
