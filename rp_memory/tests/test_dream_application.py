from __future__ import annotations

import hashlib

import pytest

from commons.text_identity import stable_text_identity_key
from rpg_core.session.reset import SessionResetService
from rpg_data import models
from rpg_data.services import (
    get_data_service_gateway,
    reset_data_service_gateways,
)
from rp_memory.dream.application import DreamApplicationService
from rp_memory.dream.errors import (
    DreamActiveMemoryLimitError,
    DreamEvidenceInvalidError,
    DreamProposalConflictError,
    DreamProposalStaleError,
)
from rp_memory.dream.source_identity import story_memory_source_identity
from rp_memory.dream.proposal import (
    DreamProposalItemInput,
    DreamProposalItemPatch,
)
from rp_memory.dream.types import (
    DreamDepth,
    DreamEvidence,
    DreamProposalAction,
    DreamProposalStatus,
    DreamScope,
    MAX_ACTIVE_MEMORIES,
    MAX_DREAM_FACT_TEXT_CHARS,
    MAX_DREAM_ITEM_EVIDENCE,
    PersistentMemoryLifecycle,
)
from rp_memory.memory_types import EpistemicStatus, MemoryKind
from rp_memory.story_memory_service import StoryMemoryApplicationService


@pytest.fixture(autouse=True)
def _reset_gateways(tmp_path, monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path / "workspaces"))
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def _evidence(message: models.SessionMessage) -> DreamEvidence:
    return DreamEvidence(
        message_id=message.id,
        turn_id=message.turn_id,
        message_version=message.version,
        content_hash=hashlib.sha256(message.content.encode("utf-8")).hexdigest(),
    )


def _create_ready(
    dream: DreamApplicationService,
    session_id: str,
    items: tuple[DreamProposalItemInput, ...],
    *,
    source_fingerprint: str = "f" * 64,
    manifests: bool = False,
) -> models.DreamProposal:
    snapshot = dream.build_source_snapshot(session_id)
    proposal = dream.create_proposal(
        session_id,
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
        history_fingerprint=snapshot.history_fingerprint,
        source_fingerprint=source_fingerprint,
        next_messages_manifest_json={"message": 1} if manifests else {},
        next_story_memories_manifest_json={"story": 2} if manifests else {},
        next_summary_batches_manifest_json={"summary": 3} if manifests else {},
    )
    return dream.set_proposal_ready(proposal.id, items)


def _dream(gateway, *, max_active_memories=MAX_ACTIVE_MEMORIES):  # noqa: ANN001, ANN202
    return DreamApplicationService(
        gateway.dream_data,
        max_active_memories=max_active_memories,
    )


def _story_memory(gateway):  # noqa: ANN001, ANN202
    return StoryMemoryApplicationService(gateway.story_memory_data)


def test_snapshot_proposal_apply_and_context_evidence_guard(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream.sqlite3")
    dream = _dream(gateway)
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
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
                dedupe_key="a" * 64,
                text="Alice 确认封印仍然完整。",
                memory_kind=MemoryKind.WORLD_FACT,
                epistemic_status=EpistemicStatus.CONFIRMED,
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
            DreamProposalItemPatch(
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

    assert result.proposal.status == DreamProposalStatus.APPLIED.value
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
    dream = _dream(gateway)
    message = dream.build_source_snapshot("s_forest001").messages[0]
    evidence = (_evidence(message),)
    first = _create_ready(
        dream,
        "s_forest001",
        (
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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
            DreamProposalItemInput(
                action=DreamProposalAction.REVISE,
                target_memory_id=memory_id,
                base_revision_number=1,
                dedupe_key="a" * 64,
                text="修订事实",
                memory_kind=MemoryKind.CLUE,
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
            DreamProposalItemInput(
                action=DreamProposalAction.RETIRE,
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
    assert restored.memory.lifecycle == PersistentMemoryLifecycle.ACTIVE.value

    supersede = _create_ready(
        dream,
        "s_forest001",
        (
            DreamProposalItemInput(
                action=DreamProposalAction.SUPERSEDE,
                target_memory_id=memory_id,
                base_revision_number=2,
                dedupe_key="b" * 64,
                text="替代事实",
                memory_kind=MemoryKind.EVENT,
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
    assert old.memory.lifecycle == PersistentMemoryLifecycle.SUPERSEDED.value
    assert old.memory.superseded_by_memory_id == new.memory.id
    assert result.active_memory_count == 1
    assert [item.text for item in dream.list_context_memories("s_forest001")] == [
        "替代事实"
    ]


def test_add_revives_retired_memory_with_new_revision_and_evidence(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-revive.sqlite3")
    dream = _dream(gateway)
    original_message = dream.build_source_snapshot("s_forest001").messages[0]
    fact_text = "封印的石门只会在月蚀时开启。"
    first = _create_ready(
        dream,
        "s_forest001",
        (
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
                dedupe_key="ignored-by-normalization",
                text=fact_text,
                memory_kind=MemoryKind.WORLD_FACT,
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
            DreamProposalItemInput(
                action=DreamProposalAction.RETIRE,
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
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
                dedupe_key="also-ignored-by-normalization",
                text=fact_text,
                memory_kind=MemoryKind.WORLD_FACT,
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
    assert revived.memory.lifecycle == PersistentMemoryLifecycle.ACTIVE.value
    assert revived.memory.current_revision_number == 2
    assert [revision.revision_number for revision in revived.revisions] == [1, 2]
    assert revived.revisions[0].evidence[0].message_id == original_message.id
    assert revived.revisions[1].evidence[0].message_id == new_message.id
    assert revived.evidence_valid


def test_revive_counts_against_active_memory_limit(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-revive-limit.sqlite3")
    dream = _dream(gateway, max_active_memories=1)
    message = dream.build_source_snapshot("s_forest001").messages[0]
    retired_text = "月蚀会开启石门。"
    first = _create_ready(
        dream,
        "s_forest001",
        (
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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
            DreamProposalItemInput(
                action=DreamProposalAction.RETIRE,
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
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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
    assert retired.memory.lifecycle == PersistentMemoryLifecycle.RETIRED.value
    assert retired.memory.current_revision_number == 1
    assert dream.get_state("s_forest001").ledger_revision == 3
    assert dream.get_proposal(revive.id).status == DreamProposalStatus.READY.value


def test_evidence_becomes_invalid_when_message_leaves_in_world_source(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-mode-evidence.sqlite3")
    dream = _dream(gateway)
    message = dream.build_source_snapshot("s_forest001").messages[0]
    proposal = _create_ready(
        dream,
        "s_forest001",
        (
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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
    dream = _dream(gateway)
    message = dream.build_source_snapshot("s_forest001").messages[0]
    proposal = _create_ready(
        dream,
        "s_forest001",
        tuple(
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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
    dream = _dream(gateway)
    message = dream.build_source_snapshot("s_forest001").messages[0]
    first = _create_ready(
        dream,
        "s_forest001",
        (
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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

    assert dream.get_proposal(second.id).status == DreamProposalStatus.STALE.value


def test_active_limit_and_reset_clear_all_dream_rows(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-limit.sqlite3")
    with pytest.raises(ValueError, match="between 1 and 64"):
        DreamApplicationService(
            gateway.dream_data,
            max_active_memories=MAX_ACTIVE_MEMORIES + 1,
        )
    dream = _dream(gateway, max_active_memories=1)
    message = dream.build_source_snapshot("s_forest001").messages[0]
    first = _create_ready(
        dream,
        "s_forest001",
        (
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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

    result = SessionResetService(gateway).reset("s_forest001")

    assert result.dream_memories_cleared == 1
    assert result.dream_proposals_cleared == 2
    assert _dream(gateway).list_memories("s_forest001") == []
    assert _dream(gateway).list_proposals("s_forest001") == []
    assert _dream(gateway).get_state("s_forest001").ledger_revision == 0


def test_proposal_payload_limits_are_enforced_at_data_boundary(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-limits.sqlite3")
    dream = _dream(gateway)
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
                DreamProposalItemInput(
                    action=DreamProposalAction.ADD,
                    dedupe_key="a" * 64,
                    text="x" * (MAX_DREAM_FACT_TEXT_CHARS + 1),
                    evidence=(_evidence(message),),
                ),
            ),
        )

    too_many_evidence = tuple(
        DreamEvidence(
            message_id=index,
            turn_id=1,
            message_version=1,
            content_hash="b" * 64,
        )
        for index in range(1, MAX_DREAM_ITEM_EVIDENCE + 2)
    )
    with pytest.raises(ValueError, match="at most 64 evidence"):
        dream.set_proposal_ready(
            proposal.id,
            (
                DreamProposalItemInput(
                    action=DreamProposalAction.ADD,
                    dedupe_key="b" * 64,
                    text="bounded",
                    evidence=too_many_evidence,
                ),
            ),
        )


def test_apply_advances_story_memory_manifest_but_reject_does_not(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-checkpoint.sqlite3")
    dream = _dream(gateway)
    story_memory = _story_memory(gateway).add_detail(
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
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
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

    assert _story_memory(gateway).get(story_memory.id).dream_processed
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
        DreamProposalStatus.GENERATING.value
    )
    interrupted = dream.interrupt_generating_proposals(
        "s_forest001",
        proposal_id=generating.id,
    )
    assert len(interrupted) == 1
    assert interrupted[0].id == generating.id
    assert interrupted[0].status == DreamProposalStatus.INTERRUPTED.value
    assert interrupted[0].finished_at
    assert dream.get_proposal(generating.id).status == (
        DreamProposalStatus.INTERRUPTED.value
    )


def test_story_memory_checkpoint_does_not_change_source_fingerprint(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-checkpoint-fingerprint.sqlite3")
    story_memory = _story_memory(gateway).add_detail(
        "s_forest001",
        "封印发出蓝光",
        turn_id=1,
    )
    before = _dream(gateway).build_source_snapshot("s_forest001")

    assert _story_memory(gateway).set_dream_processed((story_memory.id,)) == 1

    after = _dream(gateway).build_source_snapshot("s_forest001")
    assert _story_memory(gateway).get(story_memory.id).dream_processed
    assert after.story_memory_fingerprint == before.story_memory_fingerprint


def test_apply_rechecks_story_memory_version_inside_transaction(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "dream-story-stale.sqlite3")
    dream = _dream(gateway)
    story = _story_memory(gateway).add_detail(
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
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
                dedupe_key="a" * 64,
                text="封印持续发出蓝光。",
                evidence=(_evidence(message),),
            ),
        ),
    )
    updated = _story_memory(gateway).add_detail(
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
