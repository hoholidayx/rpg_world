from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from llm_client.types import LLMResponse
from rp_memory.dream.engine import DreamEngine
from rp_memory.dream.errors import DreamModelContractError
from rp_memory.dream.model import LLMDreamModel
from rp_memory.dream.source import DreamSourceSelector
from rp_memory.dream.types import (
    DreamCandidate,
    DreamDepth,
    DreamDerivedSource,
    DreamEvidence,
    DreamFact,
    DreamLedgerMemory,
    DreamManifestEntry,
    DreamMessageSource,
    DreamProposalAction,
    DreamProposalItemDraft,
    DreamRetirementPolicy,
    DreamScope,
    DreamSourceKind,
    DreamSourceSnapshot,
    dream_fact_identity_key,
)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _message(
    message_id: int,
    turn_id: int,
    content: str,
    *,
    role: str = "user",
    mode: str = "ic",
    version: int = 1,
    seq_in_turn: int = 1,
) -> DreamMessageSource:
    return DreamMessageSource(
        message_id=message_id,
        version=version,
        role=role,
        mode=mode,
        content=content,
        turn_id=turn_id,
        seq_in_turn=seq_in_turn,
        content_hash=_hash(content),
    )


def _derived(
    source_id: str,
    kind: DreamSourceKind,
    content: str,
    start: int,
    end: int,
    evidence: tuple[int, ...],
) -> DreamDerivedSource:
    return DreamDerivedSource(
        source_id=source_id,
        kind=kind,
        content=content,
        version=1,
        content_hash=_hash(content),
        source_turn_start=start,
        source_turn_end=end,
        evidence_message_ids=evidence,
    )


def _snapshot(**changes) -> DreamSourceSnapshot:  # noqa: ANN003, ANN202
    base = {
        "session_id": "session_1",
        "history_fingerprint": "a" * 64,
        "source_fingerprint": "b" * 64,
        "ledger_revision": 0,
        "messages": (
            _message(1, 1, "阿澈抵达港口"),
            _message(2, 2, "守卫交出铜钥匙", role="assistant"),
            _message(3, 3, "玩家讨论模型", mode="ooc"),
            _message(4, 4, "石门在月光下开启", role="assistant"),
        ),
        "story_memories": (
            _derived("10", DreamSourceKind.STORY_MEMORY, "得到铜钥匙", 2, 2, (2,)),
        ),
        "summary_batches": (
            _derived("1", DreamSourceKind.SUMMARY_BATCH, "抵达港口并开门", 1, 4, (1, 2, 4)),
        ),
    }
    base.update(changes)
    return DreamSourceSnapshot(**base)


def test_shallow_incremental_uses_changed_derived_sources_only() -> None:
    snapshot = _snapshot()
    story = snapshot.story_memories[0]
    selection = DreamSourceSelector().select(
        _snapshot(
            story_memory_manifest={
                "10": DreamManifestEntry("10", story.fingerprint, 2, 2)
            }
        ),
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
    )

    assert selection.retirement_policy == DreamRetirementPolicy.CONTRADICTION_ONLY
    assert [segment.source_kind for batch in selection.batches for segment in batch.segments] == [
        DreamSourceKind.SUMMARY_BATCH
    ]
    assert selection.source_story_memory_ids == ()


def test_shallow_incremental_reanalyzes_same_text_when_evidence_range_changes() -> None:
    story = _snapshot().story_memories[0]
    previous = DreamManifestEntry(
        story.source_id,
        f"{story.version}:{story.content_hash}:1:1",
        1,
        1,
    )

    selection = DreamSourceSelector().select(
        _snapshot(story_memory_manifest={story.source_id: previous}),
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
    )

    assert any(
        segment.source_id == story.source_id
        for batch in selection.batches
        for segment in batch.segments
    )


def test_shallow_full_uses_all_sourced_material_and_skips_unsourced() -> None:
    unsourced = _derived(
        "11",
        DreamSourceKind.STORY_MEMORY,
        "没有可追溯来源",
        99,
        99,
        (999,),
    )
    selection = DreamSourceSelector().select(
        _snapshot(story_memories=(*_snapshot().story_memories, unsourced)),
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.FULL,
    )

    segments = [segment for batch in selection.batches for segment in batch.segments]
    assert {segment.source_id for segment in segments} == {"10", "1"}
    assert selection.source_story_memory_ids == (10,)
    assert "11" not in selection.next_story_memory_manifest


def test_deep_incremental_detects_change_neighbors_deletion_and_excludes_ooc() -> None:
    messages = _snapshot().messages
    manifest = {
        message.source_id: DreamManifestEntry(
            message.source_id,
            "wrong" if message.message_id == 2 else message.fingerprint,
            message.turn_id,
            message.turn_id,
        )
        for message in messages
        if message.mode in {"ic", "gm"}
    }
    manifest["99"] = DreamManifestEntry("99", "old", 4, 4)
    selection = DreamSourceSelector().select(
        _snapshot(message_manifest=manifest),
        depth=DreamDepth.DEEP,
        scope=DreamScope.INCREMENTAL,
    )

    segments = [segment for batch in selection.batches for segment in batch.segments]
    assert selection.retirement_policy == DreamRetirementPolicy.INVALIDATED_EVIDENCE
    assert {item.source_id for item in segments if not item.deleted} == {"1", "2", "4"}
    assert [item.source_id for item in segments if item.deleted] == ["99"]
    assert all("玩家讨论模型" not in item.text for item in segments)


def test_deep_incremental_uses_nearest_current_turns_around_deleted_gap() -> None:
    messages = (
        _message(1, 1, "删除范围左侧"),
        _message(5, 5, "删除范围右侧", role="assistant"),
    )
    manifest = {
        message.source_id: DreamManifestEntry(
            message.source_id,
            message.fingerprint,
            message.turn_id,
            message.turn_id,
        )
        for message in messages
    }
    manifest["3"] = DreamManifestEntry("3", "deleted", 3, 3)

    selection = DreamSourceSelector().select(
        _snapshot(
            messages=messages,
            story_memories=(),
            summary_batches=(),
            message_manifest=manifest,
        ),
        depth=DreamDepth.DEEP,
        scope=DreamScope.INCREMENTAL,
    )

    segments = [segment for batch in selection.batches for segment in batch.segments]
    assert [segment.source_id for segment in segments] == ["1", "3", "5"]
    assert [segment.source_id for segment in segments if not segment.deleted] == [
        "1",
        "5",
    ]


def test_deep_full_uses_complete_current_ic_history() -> None:
    selection = DreamSourceSelector().select(
        _snapshot(),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    segments = [segment for batch in selection.batches for segment in batch.segments]
    assert selection.retirement_policy == DreamRetirementPolicy.FULL_RECONCILIATION
    assert [item.source_id for item in segments] == ["1", "2", "4"]


def test_shallow_and_deep_manifests_do_not_consume_each_others_sources() -> None:
    selector = DreamSourceSelector()
    initial = _snapshot()

    shallow = selector.select(
        initial,
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.FULL,
    )
    assert shallow.next_message_manifest == {}
    assert set(shallow.next_story_memory_manifest) == {"10"}
    assert set(shallow.next_summary_batch_manifest) == {"1"}

    after_shallow = _snapshot(
        message_manifest=shallow.next_message_manifest,
        story_memory_manifest=shallow.next_story_memory_manifest,
        summary_batch_manifest=shallow.next_summary_batch_manifest,
    )
    deep_incremental = selector.select(
        after_shallow,
        depth=DreamDepth.DEEP,
        scope=DreamScope.INCREMENTAL,
    )
    assert {
        segment.source_id
        for batch in deep_incremental.batches
        for segment in batch.segments
        if not segment.deleted
    } == {"1", "2", "4"}
    assert deep_incremental.next_story_memory_manifest == shallow.next_story_memory_manifest
    assert deep_incremental.next_summary_batch_manifest == shallow.next_summary_batch_manifest

    deep = selector.select(
        initial,
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    assert deep.next_story_memory_manifest == {}
    assert deep.next_summary_batch_manifest == {}
    after_deep = _snapshot(
        message_manifest=deep.next_message_manifest,
        story_memory_manifest=deep.next_story_memory_manifest,
        summary_batch_manifest=deep.next_summary_batch_manifest,
    )
    shallow_incremental = selector.select(
        after_deep,
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
    )
    assert {
        segment.source_id
        for batch in shallow_incremental.batches
        for segment in batch.segments
    } == {"10", "1"}


def test_deep_batches_preserve_turn_boundaries() -> None:
    messages = tuple(_message(index, index, f"turn {index}") for index in range(1, 6))
    selection = DreamSourceSelector(max_map_turns=2).select(
        _snapshot(messages=messages, story_memories=(), summary_batches=()),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    assert [[segment.turn_start for segment in batch.segments] for batch in selection.batches] == [
        [1, 2],
        [3, 4],
        [5],
    ]


def test_deep_preserves_explicit_sequence_inside_a_turn() -> None:
    messages = (
        _message(10, 1, "assistant", role="assistant", seq_in_turn=2),
        _message(9, 1, "user", seq_in_turn=1),
    )

    selection = DreamSourceSelector().select(
        _snapshot(messages=messages, story_memories=(), summary_batches=()),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )

    segments = [segment for batch in selection.batches for segment in batch.segments]
    assert [segment.source_id for segment in segments] == ["9", "10"]
    assert [segment.text.splitlines()[0] for segment in segments] == [
        "role=user mode=ic",
        "role=assistant mode=ic",
    ]


def test_char_budget_never_splits_a_normal_multi_message_turn() -> None:
    messages = (
        _message(1, 1, "u" * 600),
        _message(2, 1, "a" * 300, role="assistant"),
        _message(3, 2, "next" * 100),
    )
    selection = DreamSourceSelector(max_map_chars=1000).select(
        _snapshot(messages=messages, story_memories=(), summary_batches=()),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    assert [[segment.source_id for segment in batch.segments] for batch in selection.batches] == [
        ["1", "2"],
        ["3"],
    ]


def test_oversize_turn_uses_explicit_split_fallback_without_dropping_messages() -> None:
    messages = (
        _message(1, 1, "u" * 700),
        _message(2, 1, "a" * 700, role="assistant"),
    )
    selection = DreamSourceSelector(max_map_chars=1000).select(
        _snapshot(messages=messages, story_memories=(), summary_batches=()),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    source_ids = [
        segment.source_id
        for batch in selection.batches
        for segment in batch.segments
    ]
    assert len(selection.batches) == 2
    assert len(source_ids) == 2
    assert all("#turn-part-" in source_id for source_id in source_ids)


def test_dream_fact_and_evidence_bounds_are_enforced() -> None:
    with pytest.raises(ValueError, match="at most 1000"):
        DreamFact("x" * 1001, "event", "confirmed", 0.5)
    evidence = tuple(
        DreamEvidence(index, index, 1, _hash(str(index)))
        for index in range(1, 66)
    )
    with pytest.raises(ValueError, match="at most 64"):
        DreamCandidate(
            candidate_id="too-many",
            fact=DreamFact("fact", "event", "confirmed", 0.5),
            evidence=evidence,
        )


class _Provider:
    def __init__(self, arguments: dict[str, object]) -> None:
        self.arguments = arguments
        self.calls: list[tuple[list[dict], list[dict] | None]] = []

    async def chat(self, messages, tools=None):  # noqa: ANN001, ANN202
        self.calls.append((messages, tools))
        name = tools[0]["function"]["name"]
        return LLMResponse(
            content="ignored",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(self.arguments),
                    },
                }
            ],
            finish_reason="tool_calls",
        )


async def test_llm_dream_model_accepts_typed_tool_result() -> None:
    provider = _Provider(
        {
            "candidates": [
                {
                    "candidateId": "c1",
                    "text": "守卫把铜钥匙交给阿澈。",
                    "memoryKind": "event",
                    "epistemicStatus": "confirmed",
                    "salience": 0.8,
                    "dedupeKey": "key-transfer",
                    "evidenceMessageIds": [2],
                }
            ]
        }
    )

    async def resolve(_depth):  # noqa: ANN001, ANN202
        return provider

    selection = DreamSourceSelector().select(
        _snapshot(),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    result = await LLMDreamModel(resolve).map_candidates(
        selection.batches[0],
        depth=DreamDepth.DEEP,
    )
    assert result[0].fact.text == "守卫把铜钥匙交给阿澈。"
    assert result[0].fact.dedupe_key == dream_fact_identity_key(
        result[0].fact.text,
        result[0].fact.memory_kind,
        result[0].fact.epistemic_status,
    )
    assert result[0].evidence[0].message_id == 2
    assert provider.calls[0][1][0]["function"]["strict"] is True


async def test_llm_dream_model_rejects_hallucinated_evidence() -> None:
    provider = _Provider(
        {
            "candidates": [
                {
                    "candidateId": "c1",
                    "text": "虚构事实",
                    "memoryKind": "event",
                    "epistemicStatus": "confirmed",
                    "salience": 0.8,
                    "dedupeKey": "fake",
                    "evidenceMessageIds": [999],
                }
            ]
        }
    )

    async def resolve(_depth):  # noqa: ANN001, ANN202
        return provider

    selection = DreamSourceSelector().select(
        _snapshot(),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    with pytest.raises(DreamModelContractError, match="unavailable evidence"):
        await LLMDreamModel(resolve).map_candidates(
            selection.batches[0],
            depth=DreamDepth.DEEP,
        )


class _DreamModel:
    def __init__(self) -> None:
        self.map_calls = 0

    async def map_candidates(self, batch, *, depth):  # noqa: ANN001, ANN202
        self.map_calls += 1
        evidence = next(
            item
            for segment in batch.segments
            for item in segment.evidence
        )
        return (
            DreamCandidate(
                candidate_id=f"c{batch.index}",
                fact=DreamFact("持有铜钥匙", "clue", "confirmed", 0.8, "key"),
                evidence=(evidence,),
            ),
        )

    async def merge_candidates(self, candidates, *, depth):  # noqa: ANN001, ANN202
        return tuple(candidates)

    async def propose(
        self,
        candidates,
        active_memories,
        *,
        depth,
        retirement_policy,
        invalidated_memory_ids,
    ):  # noqa: ANN001, ANN202
        return tuple(
            DreamProposalItemDraft(
                action=DreamProposalAction.ADD,
                target_memory_id=None,
                fact=candidate.fact,
                evidence=candidate.evidence,
            )
            for candidate in candidates
        )


class _RepeatedEvidenceModel(_DreamModel):
    def __init__(self) -> None:
        super().__init__()
        self.proposed_evidence_ids: tuple[int, ...] = ()

    async def map_candidates(self, batch, *, depth):  # noqa: ANN001, ANN202
        evidence = tuple(
            item
            for segment in batch.segments
            for item in segment.evidence
        )
        return (
            DreamCandidate(
                candidate_id=f"candidate-{batch.index}",
                fact=DreamFact("重复事实", "event", "confirmed", 0.7, "same"),
                evidence=evidence,
            ),
        )

    async def propose(
        self,
        candidates,
        active_memories,
        *,
        depth,
        retirement_policy,
        invalidated_memory_ids,
    ):  # noqa: ANN001, ANN202
        assert len(candidates) == 1
        self.proposed_evidence_ids = tuple(
            evidence.message_id for evidence in candidates[0].evidence
        )
        return ()


class _DistinctSameProviderKeyModel(_DreamModel):
    def __init__(self) -> None:
        super().__init__()
        self.proposed: tuple[DreamCandidate, ...] = ()

    async def map_candidates(self, batch, *, depth):  # noqa: ANN001, ANN202
        evidence = next(
            item
            for segment in batch.segments
            for item in segment.evidence
        )
        return (
            DreamCandidate(
                candidate_id=f"distinct-{batch.index}",
                fact=DreamFact(
                    f"不同事实 {batch.index}",
                    "event",
                    "confirmed",
                    (batch.index + 1) / 10,
                    "provider-shared-key",
                ),
                evidence=(evidence,),
            ),
        )

    async def propose(
        self,
        candidates,
        active_memories,
        *,
        depth,
        retirement_policy,
        invalidated_memory_ids,
    ):  # noqa: ANN001, ANN202
        self.proposed = tuple(candidates)
        return ()


async def test_engine_exact_dedupe_ignores_provider_key_for_distinct_facts() -> None:
    model = _DistinctSameProviderKeyModel()
    engine = DreamEngine(
        model=model,
        selector=DreamSourceSelector(max_map_turns=1),
        reduce_candidate_batch_size=4,
    )
    selection = engine.prepare(
        _snapshot(
            messages=(
                _message(1, 1, "first"),
                _message(2, 2, "second"),
            ),
            story_memories=(),
            summary_batches=(),
        ),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )

    await engine.generate(selection)

    assert [item.candidate_id for item in model.proposed] == [
        "distinct-0",
        "distinct-1",
    ]


async def test_engine_bounds_non_converging_reduce_by_candidate_value() -> None:
    model = _DistinctSameProviderKeyModel()
    engine = DreamEngine(
        model=model,
        selector=DreamSourceSelector(max_map_turns=1),
        reduce_candidate_batch_size=2,
    )
    selection = engine.prepare(
        _snapshot(
            messages=tuple(
                _message(index, index, f"turn {index}")
                for index in range(1, 7)
            ),
            story_memories=(),
            summary_batches=(),
        ),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )

    result = await engine.generate(selection)

    assert result.candidate_count == 6
    assert [item.candidate_id for item in model.proposed] == [
        "distinct-5",
        "distinct-4",
    ]


async def test_engine_caps_exact_dedupe_evidence_deterministically() -> None:
    model = _RepeatedEvidenceModel()
    engine = DreamEngine(
        model=model,
        selector=DreamSourceSelector(max_map_turns=40),
    )
    selection = engine.prepare(
        _snapshot(
            messages=tuple(
                _message(index, index, f"turn {index}")
                for index in range(1, 81)
            ),
            story_memories=(),
            summary_batches=(),
        ),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )

    result = await engine.generate(selection)

    assert result.candidate_count == 2
    assert model.proposed_evidence_ids == tuple(range(1, 65))


async def test_engine_returns_noop_for_incremental_run_without_changed_sources() -> None:
    story = _snapshot().story_memories[0]
    summary = _snapshot().summary_batches[0]
    snapshot = _snapshot(
        story_memory_manifest={
            story.source_id: DreamManifestEntry(
                story.source_id,
                story.fingerprint,
                story.source_turn_start,
                story.source_turn_end,
            )
        },
        summary_batch_manifest={
            summary.source_id: DreamManifestEntry(
                summary.source_id,
                summary.fingerprint,
                summary.source_turn_start,
                summary.source_turn_end,
            )
        },
    )
    model = _DreamModel()
    engine = DreamEngine(model=model)
    selection = engine.prepare(
        snapshot,
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
    )
    result = await engine.generate(selection)
    assert result.items == ()
    assert model.map_calls == 0


class _InvalidatedModel(_DreamModel):
    def __init__(self) -> None:
        super().__init__()
        self.propose_calls = 0

    async def propose(
        self,
        candidates,
        active_memories,
        *,
        depth,
        retirement_policy,
        invalidated_memory_ids,
    ):  # noqa: ANN001, ANN202
        self.propose_calls += 1
        assert candidates == ()
        assert invalidated_memory_ids == frozenset({"memory-1"})
        return (
            DreamProposalItemDraft(
                action=DreamProposalAction.RETIRE,
                target_memory_id="memory-1",
                fact=None,
                evidence=(),
                reason="唯一证据已从当前历史删除。",
            ),
        )


async def test_deep_incremental_reconciles_invalidated_evidence_without_sources() -> None:
    evidence = DreamEvidence(9, 9, 1, _hash("deleted"))
    memory = DreamLedgerMemory(
        memory_id="memory-1",
        fact=DreamFact("旧事实", "event", "confirmed", 0.5, "old"),
        evidence=(evidence,),
    )
    model = _InvalidatedModel()
    engine = DreamEngine(model=model)
    selection = engine.prepare(
        _snapshot(
            messages=(),
            story_memories=(),
            summary_batches=(),
            active_memories=(memory,),
            message_manifest={},
        ),
        depth=DreamDepth.DEEP,
        scope=DreamScope.INCREMENTAL,
    )
    assert selection.batches == ()
    result = await engine.generate(selection)
    assert result.items[0].action == DreamProposalAction.RETIRE
    assert model.propose_calls == 1


class _FailingParallelModel(_DreamModel):
    def __init__(self) -> None:
        super().__init__()
        self.sibling_started = asyncio.Event()
        self.sibling_cancelled = asyncio.Event()

    async def map_candidates(self, batch, *, depth):  # noqa: ANN001, ANN202
        if batch.index == 0:
            await self.sibling_started.wait()
            raise RuntimeError("map failed")
        self.sibling_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.sibling_cancelled.set()


async def test_engine_cancels_and_drains_parallel_map_siblings_on_failure() -> None:
    model = _FailingParallelModel()
    engine = DreamEngine(
        model=model,
        selector=DreamSourceSelector(max_map_turns=1),
        map_concurrency=2,
    )
    selection = engine.prepare(
        _snapshot(
            messages=(
                _message(1, 1, "first"),
                _message(2, 2, "second"),
            ),
            story_memories=(),
            summary_batches=(),
        ),
        depth=DreamDepth.DEEP,
        scope=DreamScope.FULL,
    )
    with pytest.raises(RuntimeError, match="map failed"):
        await engine.generate(selection)
    assert model.sibling_cancelled.is_set()
