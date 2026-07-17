"""Typed tool-call adapter for Dream Map/Reduce LLM operations."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from typing import Protocol, cast

from llm_client.manager import LLMClientManager
from llm_client.types import LLMProvider, LLMResponse

from rp_memory.dream.errors import DreamModelContractError
from rp_memory.dream.types import (
    DreamCandidate,
    DreamDepth,
    DreamEvidence,
    DreamFact,
    DreamLedgerMemory,
    DreamProposalAction,
    DreamProposalItemDraft,
    DreamRetirementPolicy,
    DreamSourceBatch,
    EPISTEMIC_STATUSES,
    MAX_DREAM_FACT_TEXT_CHARS,
    MAX_DREAM_ITEM_EVIDENCE,
    MAX_DREAM_PROPOSAL_ITEMS,
    MAX_DREAM_REASON_CHARS,
    MEMORY_KINDS,
    dream_fact_identity_key,
)

DREAM_SHALLOW_BIZ_KEY = "dream.shallow"
DREAM_DEEP_BIZ_KEY = "dream.deep"


class DreamModel(Protocol):
    async def map_candidates(
        self,
        batch: DreamSourceBatch,
        *,
        depth: DreamDepth,
    ) -> tuple[DreamCandidate, ...]: ...

    async def merge_candidates(
        self,
        candidates: Sequence[DreamCandidate],
        *,
        depth: DreamDepth,
    ) -> tuple[DreamCandidate, ...]: ...

    async def propose(
        self,
        candidates: Sequence[DreamCandidate],
        active_memories: Sequence[DreamLedgerMemory],
        *,
        depth: DreamDepth,
        retirement_policy: DreamRetirementPolicy,
        invalidated_memory_ids: frozenset[str],
    ) -> tuple[DreamProposalItemDraft, ...]: ...


ProviderResolver = Callable[[DreamDepth], Awaitable[LLMProvider]]


class LLMDreamModel:
    """Use the LLM service through its provider-neutral async client."""

    def __init__(self, provider_resolver: ProviderResolver | None = None) -> None:
        self._provider_resolver = provider_resolver or _resolve_provider

    async def map_candidates(
        self,
        batch: DreamSourceBatch,
        *,
        depth: DreamDepth,
    ) -> tuple[DreamCandidate, ...]:
        evidence = _evidence_by_id(
            item for segment in batch.segments for item in segment.evidence
        )
        payload = [
            {
                "sourceKind": segment.source_kind.value,
                "sourceId": segment.source_id,
                "turnStart": segment.turn_start,
                "turnEnd": segment.turn_end,
                "deleted": segment.deleted,
                "allowedEvidenceMessageIds": [
                    item.message_id for item in segment.evidence
                ],
                "content": segment.text,
            }
            for segment in batch.segments
        ]
        response = await self._chat(
            depth,
            system=_map_system_prompt(depth),
            payload={
                "playerCharacterName": batch.player_character_name,
                "sources": payload,
            },
            tool=_candidate_tool(),
        )
        raw = _tool_arguments(response, "submit_dream_candidates")
        return _parse_candidates(raw, evidence)

    async def merge_candidates(
        self,
        candidates: Sequence[DreamCandidate],
        *,
        depth: DreamDepth,
    ) -> tuple[DreamCandidate, ...]:
        evidence = _evidence_by_id(
            item for candidate in candidates for item in candidate.evidence
        )
        response = await self._chat(
            depth,
            system=(
                "Merge semantically duplicate RP memory facts without losing distinct facts, "
                "uncertainty, contradictions, or any supporting evidence. Return only through "
                "the supplied tool. Every output must cite evidence from the input candidates."
            ),
            payload={"candidates": [_candidate_wire(item) for item in candidates]},
            tool=_candidate_tool(),
        )
        raw = _tool_arguments(response, "submit_dream_candidates")
        return _parse_candidates(raw, evidence)

    async def propose(
        self,
        candidates: Sequence[DreamCandidate],
        active_memories: Sequence[DreamLedgerMemory],
        *,
        depth: DreamDepth,
        retirement_policy: DreamRetirementPolicy,
        invalidated_memory_ids: frozenset[str],
    ) -> tuple[DreamProposalItemDraft, ...]:
        evidence = _evidence_by_id(
            item for candidate in candidates for item in candidate.evidence
        )
        response = await self._chat(
            depth,
            system=_proposal_system_prompt(retirement_policy),
            payload={
                "retirementPolicy": retirement_policy.value,
                "invalidatedMemoryIds": sorted(invalidated_memory_ids),
                "candidates": [_candidate_wire(item) for item in candidates],
                "activeLedger": [_ledger_wire(item) for item in active_memories],
            },
            tool=_proposal_tool(),
        )
        raw = _tool_arguments(response, "submit_dream_proposal")
        return _parse_proposal_items(
            raw,
            evidence=evidence,
            active_memories={item.memory_id: item for item in active_memories},
            retirement_policy=retirement_policy,
            invalidated_memory_ids=invalidated_memory_ids,
        )

    async def _chat(
        self,
        depth: DreamDepth,
        *,
        system: str,
        payload: Mapping[str, object],
        tool: dict[str, object],
    ) -> LLMResponse:
        provider = await self._provider_resolver(depth)
        return await provider.chat(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            tools=[tool],
        )


async def _resolve_provider(depth: DreamDepth) -> LLMProvider:
    biz_key = (
        DREAM_SHALLOW_BIZ_KEY
        if depth == DreamDepth.SHALLOW
        else DREAM_DEEP_BIZ_KEY
    )
    return await LLMClientManager.get().get_provider(biz_key)


def _map_system_prompt(depth: DreamDepth) -> str:
    source_note = (
        "The input is derived story memory and sourced summary material."
        if depth == DreamDepth.SHALLOW
        else "The input is the current mutable main message history."
    )
    return (
        "You extract atomic, durable in-world RP facts for long-term memory. "
        f"{source_note} Include only characters, relationships, commitments, clues, "
        "world facts, key events, and lasting consequences. Exclude user preferences, "
        "OOC text, system/configuration facts, transient scene values, and status-table "
        "snapshots. Never invent evidence. Every fact must cite one or more allowed current "
        "message IDs. When playerCharacterName is non-empty, user-role IC messages are actions "
        "or speech by that player character. Preserve epistemic uncertainty and contradictions. Return only through "
        "the supplied tool."
    )


def _proposal_system_prompt(policy: DreamRetirementPolicy) -> str:
    if policy == DreamRetirementPolicy.CONTRADICTION_ONLY:
        retirement = (
            "Do not retire any ledger memory. Explicit contradictory evidence may revise or "
            "supersede it, but absence from partial sources proves nothing."
        )
    elif policy == DreamRetirementPolicy.INVALIDATED_EVIDENCE:
        retirement = (
            "Retire only a memory listed in invalidatedMemoryIds when its deleted or edited "
            "evidence no longer supports it. Do not infer retirement from local absence."
        )
    else:
        retirement = (
            "This is a full-history reconciliation. A ledger memory may be retired when the "
            "complete current history no longer supports it."
        )
    return (
        "Reconcile durable candidate facts against the active RP memory ledger. Use add for a "
        "new fact, revise for a corrected version of the same fact, supersede when a distinct "
        "new fact replaces an old one, and retire only under the stated policy. Avoid cosmetic "
        "rewrites and duplicates. Every non-retire action must cite current message evidence. "
        f"{retirement} Return only through the supplied tool."
    )


def _candidate_tool() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "submit_dream_candidates",
            "description": "Submit typed durable-memory candidates.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "candidates": {
                        "type": "array",
                        "maxItems": MAX_DREAM_PROPOSAL_ITEMS,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "candidateId": {"type": "string"},
                                "text": {
                                    "type": "string",
                                    "maxLength": MAX_DREAM_FACT_TEXT_CHARS,
                                },
                                "memoryKind": {
                                    "type": "string",
                                    "enum": sorted(MEMORY_KINDS),
                                },
                                "epistemicStatus": {
                                    "type": "string",
                                    "enum": sorted(EPISTEMIC_STATUSES),
                                },
                                "salience": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                                "dedupeKey": {"type": "string"},
                                "evidenceMessageIds": {
                                    "type": "array",
                                    "maxItems": MAX_DREAM_ITEM_EVIDENCE,
                                    "items": {"type": "integer", "minimum": 1},
                                },
                            },
                            "required": [
                                "candidateId",
                                "text",
                                "memoryKind",
                                "epistemicStatus",
                                "salience",
                                "dedupeKey",
                                "evidenceMessageIds",
                            ],
                        },
                    }
                },
                "required": ["candidates"],
            },
        },
    }


def _proposal_tool() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "submit_dream_proposal",
            "description": "Submit typed changes to the persistent-memory ledger.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "items": {
                        "type": "array",
                        "maxItems": MAX_DREAM_PROPOSAL_ITEMS,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": [item.value for item in DreamProposalAction],
                                },
                                "targetMemoryId": {"type": ["string", "null"]},
                                "text": {
                                    "type": ["string", "null"],
                                    "maxLength": MAX_DREAM_FACT_TEXT_CHARS,
                                },
                                "memoryKind": {
                                    "type": ["string", "null"],
                                    "enum": [*sorted(MEMORY_KINDS), None],
                                },
                                "epistemicStatus": {
                                    "type": ["string", "null"],
                                    "enum": [*sorted(EPISTEMIC_STATUSES), None],
                                },
                                "salience": {
                                    "type": ["number", "null"],
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                                "dedupeKey": {"type": ["string", "null"]},
                                "evidenceMessageIds": {
                                    "type": "array",
                                    "maxItems": MAX_DREAM_ITEM_EVIDENCE,
                                    "items": {"type": "integer", "minimum": 1},
                                },
                                "reason": {
                                    "type": "string",
                                    "maxLength": MAX_DREAM_REASON_CHARS,
                                },
                            },
                            "required": [
                                "action",
                                "targetMemoryId",
                                "text",
                                "memoryKind",
                                "epistemicStatus",
                                "salience",
                                "dedupeKey",
                                "evidenceMessageIds",
                                "reason",
                            ],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    }


def _tool_arguments(response: LLMResponse, expected_name: str) -> Mapping[str, object]:
    calls = response.tool_calls
    if not isinstance(calls, list) or len(calls) != 1:
        raise DreamModelContractError(
            f"Dream model must return exactly one {expected_name} tool call"
        )
    call = calls[0]
    function = call.get("function") if isinstance(call, Mapping) else None
    if not isinstance(function, Mapping) or function.get("name") != expected_name:
        raise DreamModelContractError(
            f"Dream model returned an unexpected tool call; expected {expected_name}"
        )
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise DreamModelContractError("Dream tool arguments are not valid JSON") from exc
    if not isinstance(arguments, Mapping):
        raise DreamModelContractError("Dream tool arguments must be an object")
    return cast(Mapping[str, object], arguments)


def _parse_candidates(
    payload: Mapping[str, object],
    evidence: Mapping[int, DreamEvidence],
) -> tuple[DreamCandidate, ...]:
    raw_items = payload.get("candidates")
    if not isinstance(raw_items, list):
        raise DreamModelContractError("Dream candidates must be an array")
    if len(raw_items) > MAX_DREAM_PROPOSAL_ITEMS:
        raise DreamModelContractError(
            f"Dream candidate batch exceeds {MAX_DREAM_PROPOSAL_ITEMS} items"
        )
    result: list[DreamCandidate] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, Mapping):
            raise DreamModelContractError("Dream candidate must be an object")
        candidate_id = str(raw.get("candidateId") or f"candidate-{index + 1}").strip()
        if not candidate_id or candidate_id in seen_ids:
            raise DreamModelContractError("Dream candidate IDs must be non-empty and unique")
        seen_ids.add(candidate_id)
        fact = _fact_from_wire(raw)
        cited = _resolve_evidence(raw.get("evidenceMessageIds"), evidence)
        result.append(
            DreamCandidate(
                candidate_id=candidate_id,
                fact=fact,
                evidence=cited,
            )
        )
    return tuple(result)


def _parse_proposal_items(
    payload: Mapping[str, object],
    *,
    evidence: Mapping[int, DreamEvidence],
    active_memories: Mapping[str, DreamLedgerMemory],
    retirement_policy: DreamRetirementPolicy,
    invalidated_memory_ids: frozenset[str],
) -> tuple[DreamProposalItemDraft, ...]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise DreamModelContractError("Dream proposal items must be an array")
    if len(raw_items) > MAX_DREAM_PROPOSAL_ITEMS:
        raise DreamModelContractError(
            f"Dream proposal exceeds {MAX_DREAM_PROPOSAL_ITEMS} items"
        )
    result: list[DreamProposalItemDraft] = []
    affected_targets: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            raise DreamModelContractError("Dream proposal item must be an object")
        try:
            action = DreamProposalAction(str(raw.get("action") or ""))
        except ValueError as exc:
            raise DreamModelContractError("invalid Dream proposal action") from exc
        target = str(raw.get("targetMemoryId") or "").strip() or None
        if action != DreamProposalAction.ADD:
            if target not in active_memories:
                raise DreamModelContractError("Dream proposal targets a non-active memory")
            if cast(str, target) in affected_targets:
                raise DreamModelContractError(
                    "Dream proposal may change an active memory at most once"
                )
            affected_targets.add(cast(str, target))
        if action == DreamProposalAction.RETIRE:
            if retirement_policy == DreamRetirementPolicy.CONTRADICTION_ONLY:
                raise DreamModelContractError("shallow Dream cannot retire memories")
            if (
                retirement_policy == DreamRetirementPolicy.INVALIDATED_EVIDENCE
                and target not in invalidated_memory_ids
            ):
                raise DreamModelContractError(
                    "incremental Deep Dream may retire only invalidated evidence"
                )
            fact = None
            cited = active_memories[cast(str, target)].evidence
        else:
            fact = _fact_from_wire(raw)
            cited = _resolve_evidence(raw.get("evidenceMessageIds"), evidence)
        result.append(
            DreamProposalItemDraft(
                action=action,
                target_memory_id=target,
                fact=fact,
                evidence=cited,
                reason=str(raw.get("reason") or "").strip(),
            )
        )
    return tuple(result)


def _fact_from_wire(raw: Mapping[str, object]) -> DreamFact:
    try:
        salience = float(raw.get("salience", 0.0))
    except (TypeError, ValueError) as exc:
        raise DreamModelContractError("Dream fact salience must be numeric") from exc
    try:
        text = str(raw.get("text") or "").strip()
        memory_kind = str(raw.get("memoryKind") or "")
        epistemic_status = str(raw.get("epistemicStatus") or "")
        return DreamFact(
            text=text,
            memory_kind=memory_kind,
            epistemic_status=epistemic_status,
            salience=salience,
            # Provider keys are semantic hints only. Persisted identity is
            # always derived locally so malformed keys cannot merge facts or
            # create a delayed SQL uniqueness failure.
            dedupe_key=dream_fact_identity_key(
                text,
                memory_kind,
                epistemic_status,
            ),
        )
    except ValueError as exc:
        raise DreamModelContractError(str(exc)) from exc


def _resolve_evidence(
    raw_ids: object,
    allowed: Mapping[int, DreamEvidence],
) -> tuple[DreamEvidence, ...]:
    if not isinstance(raw_ids, list) or not raw_ids:
        raise DreamModelContractError("Dream fact must cite evidence message IDs")
    result: list[DreamEvidence] = []
    seen: set[int] = set()
    for raw_id in raw_ids:
        if isinstance(raw_id, bool):
            raise DreamModelContractError("Dream evidence message ID must be an integer")
        try:
            message_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise DreamModelContractError(
                "Dream evidence message ID must be an integer"
            ) from exc
        if message_id not in allowed:
            raise DreamModelContractError(
                f"Dream model cited unavailable evidence message {message_id}"
            )
        if message_id not in seen:
            result.append(allowed[message_id])
            seen.add(message_id)
    return tuple(result)


def _evidence_by_id(items: Iterable[DreamEvidence]) -> dict[int, DreamEvidence]:
    result: dict[int, DreamEvidence] = {}
    for evidence in items:
        previous = result.get(evidence.message_id)
        if previous is not None and previous != evidence:
            raise DreamModelContractError(
                f"conflicting evidence snapshots for message {evidence.message_id}"
            )
        result[evidence.message_id] = evidence
    return result


def _candidate_wire(candidate: DreamCandidate) -> dict[str, object]:
    return {
        "candidateId": candidate.candidate_id,
        "text": candidate.fact.text,
        "memoryKind": candidate.fact.memory_kind,
        "epistemicStatus": candidate.fact.epistemic_status,
        "salience": candidate.fact.salience,
        "dedupeKey": candidate.fact.dedupe_key,
        "evidenceMessageIds": [item.message_id for item in candidate.evidence],
    }


def _ledger_wire(memory: DreamLedgerMemory) -> dict[str, object]:
    return {
        "memoryId": memory.memory_id,
        "text": memory.fact.text,
        "memoryKind": memory.fact.memory_kind,
        "epistemicStatus": memory.fact.epistemic_status,
        "salience": memory.fact.salience,
        "dedupeKey": memory.fact.dedupe_key,
        "evidenceMessageIds": [item.message_id for item in memory.evidence],
    }
