"""Map/Reduce orchestration for one immutable Dream selection."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from rp_memory.dream.model import DreamModel
from rp_memory.dream.source import DreamSourceSelector
from rp_memory.dream.types import (
    DreamCandidate,
    DreamDepth,
    DreamGenerationResult,
    DreamRetirementPolicy,
    DreamScope,
    DreamSelection,
    DreamSourceSnapshot,
    MAX_DREAM_ITEM_EVIDENCE,
    MAX_DREAM_PROPOSAL_ITEMS,
    dream_fact_identity_key,
)

_MAX_HIERARCHICAL_REDUCE_ROUNDS = 8


class DreamEngine:
    def __init__(
        self,
        *,
        model: DreamModel,
        selector: DreamSourceSelector | None = None,
        map_concurrency: int = 2,
        reduce_candidate_batch_size: int = 32,
    ) -> None:
        self._model = model
        self._selector = selector or DreamSourceSelector()
        self._map_concurrency = max(1, int(map_concurrency))
        self._reduce_candidate_batch_size = min(
            MAX_DREAM_PROPOSAL_ITEMS,
            max(2, int(reduce_candidate_batch_size)),
        )

    def prepare(
        self,
        snapshot: DreamSourceSnapshot,
        *,
        depth: DreamDepth,
        scope: DreamScope,
    ) -> DreamSelection:
        return self._selector.select(snapshot, depth=depth, scope=scope)

    async def generate(self, selection: DreamSelection) -> DreamGenerationResult:
        invalidated_ids = _invalidated_memory_ids(selection)
        if not selection.batches and not (
            selection.depth == DreamDepth.DEEP
            and (
                selection.scope == DreamScope.FULL
                or bool(invalidated_ids)
            )
        ):
            return DreamGenerationResult(
                items=(),
                analyzed_batch_count=0,
                candidate_count=0,
            )
        semaphore = asyncio.Semaphore(self._map_concurrency)

        async def map_one(index: int):
            async with semaphore:
                candidates = await self._model.map_candidates(
                    selection.batches[index],
                    depth=selection.depth,
                )
                return index, candidates

        mapped = await _gather_cancel_on_error(
            *(map_one(index) for index in range(len(selection.batches)))
        )
        candidates = tuple(
            candidate
            for _index, items in sorted(mapped, key=lambda item: item[0])
            for candidate in items
        )
        initial_candidate_count = len(candidates)
        candidates = _dedupe_exact_candidates(candidates)
        candidates = await self._hierarchical_merge(candidates, depth=selection.depth)

        items = await self._model.propose(
            candidates,
            selection.snapshot.active_memories,
            depth=selection.depth,
            retirement_policy=selection.retirement_policy,
            invalidated_memory_ids=invalidated_ids,
        )
        return DreamGenerationResult(
            items=items,
            analyzed_batch_count=len(selection.batches),
            candidate_count=initial_candidate_count,
        )

    async def _hierarchical_merge(
        self,
        candidates: tuple[DreamCandidate, ...],
        *,
        depth: DreamDepth,
    ) -> tuple[DreamCandidate, ...]:
        current = candidates
        round_count = 0
        while len(current) > self._reduce_candidate_batch_size:
            round_count += 1
            groups = [
                current[start : start + self._reduce_candidate_batch_size]
                for start in range(0, len(current), self._reduce_candidate_batch_size)
            ]
            merged_groups = await _gather_cancel_on_error(
                *(self._model.merge_candidates(group, depth=depth) for group in groups)
            )
            merged = _dedupe_exact_candidates(
                tuple(item for group in merged_groups for item in group)
            )
            if (
                len(merged) >= len(current)
                or round_count >= _MAX_HIERARCHICAL_REDUCE_ROUNDS
            ):
                return _select_high_value_candidates(
                    merged,
                    limit=self._reduce_candidate_batch_size,
                )
            current = merged
        return current


def _dedupe_exact_candidates(
    candidates: Sequence[DreamCandidate],
) -> tuple[DreamCandidate, ...]:
    merged: dict[str, DreamCandidate] = {}
    for candidate in candidates:
        key = dream_fact_identity_key(
            candidate.fact.text,
            candidate.fact.memory_kind,
            candidate.fact.epistemic_status,
        )
        previous = merged.get(key)
        if previous is None:
            merged[key] = candidate
            continue
        evidence = {item.message_id: item for item in previous.evidence}
        evidence.update({item.message_id: item for item in candidate.evidence})
        fact = (
            candidate.fact
            if candidate.fact.salience > previous.fact.salience
            else previous.fact
        )
        merged[key] = DreamCandidate(
            candidate_id=previous.candidate_id,
            fact=fact,
            evidence=tuple(
                evidence[message_id]
                for message_id in sorted(evidence)[:MAX_DREAM_ITEM_EVIDENCE]
            ),
        )
    return tuple(merged.values())


def _select_high_value_candidates(
    candidates: Sequence[DreamCandidate],
    *,
    limit: int,
) -> tuple[DreamCandidate, ...]:
    """Bound a non-converging Reduce result while preserving fact diversity."""

    if len(candidates) <= limit:
        return tuple(candidates)
    buckets: dict[tuple[str, str], list[DreamCandidate]] = {}
    for candidate in candidates:
        bucket = (
            candidate.fact.memory_kind,
            candidate.fact.epistemic_status,
        )
        buckets.setdefault(bucket, []).append(candidate)
    for bucket in buckets.values():
        bucket.sort(key=_candidate_value_key)
    ordered_buckets = sorted(
        buckets.items(),
        key=lambda item: (_candidate_value_key(item[1][0]), item[0]),
    )

    selected: list[DreamCandidate] = []
    offset = 0
    while len(selected) < limit:
        added = False
        for _bucket_key, bucket in ordered_buckets:
            if offset >= len(bucket):
                continue
            selected.append(bucket[offset])
            added = True
            if len(selected) == limit:
                break
        if not added:
            break
        offset += 1
    return tuple(selected)


def _candidate_value_key(
    candidate: DreamCandidate,
) -> tuple[float, int, int, str, str]:
    latest_turn = max((item.turn_id for item in candidate.evidence), default=0)
    identity = dream_fact_identity_key(
        candidate.fact.text,
        candidate.fact.memory_kind,
        candidate.fact.epistemic_status,
    )
    return (
        -float(candidate.fact.salience),
        -len(candidate.evidence),
        -latest_turn,
        identity,
        candidate.candidate_id,
    )


def _invalidated_memory_ids(selection: DreamSelection) -> frozenset[str]:
    if selection.retirement_policy != DreamRetirementPolicy.INVALIDATED_EVIDENCE:
        return frozenset()
    current_messages = {message.message_id for message in selection.snapshot.messages}
    current_by_id = {
        message.message_id: message for message in selection.snapshot.messages
    }
    invalidated: set[str] = set()
    for memory in selection.snapshot.active_memories:
        for evidence in memory.evidence:
            current = current_by_id.get(evidence.message_id)
            if evidence.message_id not in current_messages or current is None:
                invalidated.add(memory.memory_id)
                break
            if (
                current.version != evidence.message_version
                or current.content_hash != evidence.content_hash
            ):
                invalidated.add(memory.memory_id)
                break
    return frozenset(invalidated)


async def _gather_cancel_on_error(*coroutines):  # noqa: ANN002, ANN202
    """Cancel and drain sibling LLM calls when one branch fails or is cancelled."""

    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    if not tasks:
        return []
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
