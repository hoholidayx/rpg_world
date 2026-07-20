"""Pure Dream proposal normalization and selection policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from commons.text_identity import stable_text_identity_key
from rpg_data.model import memory as models
from rp_memory.dream.errors import DreamProposalStateError
from rp_memory.dream.types import (
    DreamProposalAction,
    DreamProposalStatus,
    DreamEvidence,
    MAX_DREAM_FACT_TEXT_CHARS,
    MAX_DREAM_ITEM_EVIDENCE,
    MAX_DREAM_PROPOSAL_ITEMS,
    MAX_DREAM_REASON_CHARS,
    PersistentMemoryLifecycle,
)
from rp_memory.memory_types import EpistemicStatus, MemoryKind


@dataclass(frozen=True)
class DreamProposalItemInput:
    """Typed item command accepted by the Dream proposal application layer."""

    action: DreamProposalAction
    dedupe_key: str
    text: str = ""
    memory_kind: MemoryKind = MemoryKind.EVENT
    epistemic_status: EpistemicStatus = EpistemicStatus.CONFIRMED
    salience: float = 0.5
    reason: str = ""
    target_memory_id: str | None = None
    base_revision_number: int | None = None
    selected: bool = True
    sort_order: int = 0
    evidence: tuple[DreamEvidence, ...] = ()


@dataclass(frozen=True)
class DreamProposalItemPatch:
    """User-editable fields for one ready proposal item."""

    item_id: str
    selected: bool | None = None
    text: str | None = None
    memory_kind: MemoryKind | None = None
    epistemic_status: EpistemicStatus | None = None
    salience: float | None = None


def require_proposal_status(
    proposal: models.DreamProposal,
    allowed: frozenset[DreamProposalStatus],
) -> DreamProposalStatus:
    try:
        status = DreamProposalStatus(proposal.status)
    except ValueError as exc:
        raise DreamProposalStateError(
            f"Dream proposal has unsupported status: {proposal.status}"
        ) from exc
    if status not in allowed:
        expected = sorted(item.value for item in allowed)
        raise DreamProposalStateError(
            f"Dream proposal {proposal.id} is {status.value}; expected {expected}"
        )
    return status


def normalize_item_drafts(
    items: Sequence[DreamProposalItemInput],
) -> tuple[DreamProposalItemInput, ...]:
    if len(items) > MAX_DREAM_PROPOSAL_ITEMS:
        raise ValueError(
            f"Dream proposal may contain at most {MAX_DREAM_PROPOSAL_ITEMS} items"
        )
    return tuple(normalize_item_draft(item) for item in items)


def normalize_item_draft(
    draft: DreamProposalItemInput,
) -> DreamProposalItemInput:
    if not isinstance(draft, DreamProposalItemInput):
        raise TypeError("Dream proposal items must be DreamProposalItemInput values")
    if not isinstance(draft.action, DreamProposalAction):
        raise TypeError("Dream proposal action must be DreamProposalAction")
    action = draft.action
    evidence = tuple(_normalize_evidence(item) for item in draft.evidence)
    if len(evidence) > MAX_DREAM_ITEM_EVIDENCE:
        raise ValueError(
            "Dream proposal item may cite at most "
            f"{MAX_DREAM_ITEM_EVIDENCE} evidence messages"
        )
    if len({item.message_id for item in evidence}) != len(evidence):
        raise ValueError("Dream proposal item evidence message IDs must be unique")
    if action is not DreamProposalAction.RETIRE and not evidence:
        raise ValueError(f"Dream {action.value} item must have evidence")
    text = _memory_text(
        draft.text,
        allow_empty=action is DreamProposalAction.RETIRE,
    )
    memory_kind = _memory_kind(draft.memory_kind)
    epistemic_status = _epistemic_status(draft.epistemic_status)
    dedupe_key = (
        stable_text_identity_key(
            memory_kind.value,
            epistemic_status.value,
            text,
        )
        if action in {DreamProposalAction.ADD, DreamProposalAction.SUPERSEDE}
        else _fingerprint(draft.dedupe_key, "dedupe_key")
    )
    return DreamProposalItemInput(
        action=action,
        target_memory_id=(
            str(draft.target_memory_id) if draft.target_memory_id else None
        ),
        base_revision_number=(
            _positive_int(draft.base_revision_number, "base_revision_number")
            if draft.base_revision_number is not None
            else None
        ),
        dedupe_key=dedupe_key,
        selected=bool(draft.selected),
        text=text,
        memory_kind=memory_kind,
        epistemic_status=epistemic_status,
        salience=_salience(draft.salience),
        reason=_bounded_text(
            draft.reason,
            name="Dream proposal reason",
            max_chars=MAX_DREAM_REASON_CHARS,
            allow_empty=True,
        ),
        sort_order=int(draft.sort_order),
        evidence=evidence,
    )


def normalize_item_patches(
    patches: Sequence[DreamProposalItemPatch],
) -> tuple[DreamProposalItemPatch, ...]:
    if len(patches) > MAX_DREAM_PROPOSAL_ITEMS:
        raise ValueError(
            "Dream proposal update may contain at most "
            f"{MAX_DREAM_PROPOSAL_ITEMS} items"
        )
    normalized = tuple(normalize_item_patch(item) for item in patches)
    if len({item.item_id for item in normalized}) != len(normalized):
        raise ValueError("Dream proposal item patches must have unique item_id values")
    return normalized


def normalize_item_patch(
    patch: DreamProposalItemPatch,
) -> DreamProposalItemPatch:
    if not isinstance(patch, DreamProposalItemPatch):
        raise TypeError("Dream item updates must be DreamProposalItemPatch values")
    item_id = str(patch.item_id)
    if not item_id:
        raise ValueError("Dream item patch item_id must not be empty")
    return DreamProposalItemPatch(
        item_id=item_id,
        selected=bool(patch.selected) if patch.selected is not None else None,
        text=patch.text,
        memory_kind=patch.memory_kind,
        epistemic_status=patch.epistemic_status,
        salience=patch.salience,
    )


def apply_item_patches(
    proposal: models.DreamProposal,
    patches: Sequence[DreamProposalItemPatch],
) -> tuple[models.DreamProposalItemRowValues, ...]:
    patch_by_id = {item.item_id: item for item in patches}
    item_by_id = {item.id: item for item in proposal.items}
    missing = tuple(item_id for item_id in patch_by_id if item_id not in item_by_id)
    if missing:
        raise FileNotFoundError(f"Dream proposal item not found: {missing[0]}")
    result: list[models.DreamProposalItemRowValues] = []
    for item in proposal.items:
        values = proposal_item_values(item)
        patch = patch_by_id.get(item.id)
        if patch is not None:
            action = DreamProposalAction(values.action)
            text = (
                _memory_text(
                    patch.text,
                    allow_empty=action is DreamProposalAction.RETIRE,
                )
                if patch.text is not None
                else values.text
            )
            memory_kind = (
                _memory_kind(patch.memory_kind).value
                if patch.memory_kind is not None
                else values.memory_kind
            )
            epistemic_status = (
                _epistemic_status(patch.epistemic_status).value
                if patch.epistemic_status is not None
                else values.epistemic_status
            )
            dedupe_key = values.dedupe_key
            if action in {DreamProposalAction.ADD, DreamProposalAction.SUPERSEDE}:
                dedupe_key = stable_text_identity_key(
                    memory_kind,
                    epistemic_status,
                    text,
                )
            values = replace(
                values,
                selected=(
                    patch.selected if patch.selected is not None else values.selected
                ),
                text=text,
                memory_kind=memory_kind,
                epistemic_status=epistemic_status,
                salience=(
                    _salience(patch.salience)
                    if patch.salience is not None
                    else values.salience
                ),
                dedupe_key=dedupe_key,
            )
        result.append(values)
    return tuple(result)


def proposal_item_values(
    item: models.DreamProposalItem,
) -> models.DreamProposalItemRowValues:
    return models.DreamProposalItemRowValues(
        id=item.id,
        action=item.action,
        dedupe_key=item.dedupe_key,
        selected=item.selected,
        text=item.text,
        memory_kind=item.memory_kind,
        epistemic_status=item.epistemic_status,
        salience=item.salience,
        reason=item.reason,
        target_memory_id=item.target_memory_id,
        base_revision_number=item.base_revision_number,
        sort_order=item.sort_order,
        evidence=tuple(
            models.MemoryEvidence(
                message_id=evidence.message_id,
                turn_id=evidence.turn_id,
                message_version=evidence.message_version,
                content_hash=evidence.content_hash,
            )
            for evidence in item.evidence
        ),
    )


def validate_selected_uniqueness(
    items: Sequence[models.DreamProposalItemRowValues],
    memories_by_key: Mapping[str, models.PersistentMemoryBundle],
) -> None:
    seen_targets: set[str] = set()
    seen_new_keys: set[str] = set()
    for item in items:
        if not item.selected:
            continue
        if item.target_memory_id is not None:
            if item.target_memory_id in seen_targets:
                raise DreamProposalStateError(
                    "A Dream proposal cannot apply multiple actions to memory: "
                    f"{item.target_memory_id}"
                )
            seen_targets.add(item.target_memory_id)
        action = DreamProposalAction(item.action)
        if action not in {DreamProposalAction.ADD, DreamProposalAction.SUPERSEDE}:
            continue
        if item.dedupe_key in seen_new_keys:
            raise DreamProposalStateError(
                f"Dream proposal creates duplicate memory key: {item.dedupe_key}"
            )
        seen_new_keys.add(item.dedupe_key)
        existing = memories_by_key.get(item.dedupe_key)
        if existing is not None and not (
            action is DreamProposalAction.ADD
            and existing.memory.lifecycle == PersistentMemoryLifecycle.RETIRED.value
        ):
            raise DreamProposalStateError(
                f"Persistent memory key already exists: {item.dedupe_key}"
            )


def _normalize_evidence(
    value: DreamEvidence,
) -> DreamEvidence:
    if not isinstance(value, DreamEvidence):
        raise TypeError("Dream evidence must be DreamEvidence")
    return DreamEvidence(
        message_id=_positive_int(value.message_id, "message_id"),
        turn_id=_positive_int(value.turn_id, "turn_id"),
        message_version=_positive_int(value.message_version, "message_version"),
        content_hash=_fingerprint(value.content_hash, "content_hash"),
    )


def _memory_kind(value: object) -> MemoryKind:
    if not isinstance(value, MemoryKind):
        raise TypeError("Dream proposal memory_kind must be MemoryKind")
    return value


def _epistemic_status(value: object) -> EpistemicStatus:
    if not isinstance(value, EpistemicStatus):
        raise TypeError(
            "Dream proposal epistemic_status must be EpistemicStatus"
        )
    return value


def _fingerprint(value: object, name: str) -> str:
    import re

    normalized = str(value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return normalized


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if normalized <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


def _salience(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("salience must be within [0, 1]")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("salience must be within [0, 1]") from exc
    if not 0.0 <= normalized <= 1.0:
        raise ValueError("salience must be within [0, 1]")
    return normalized


def _memory_text(value: object, *, allow_empty: bool) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized and not allow_empty:
        raise ValueError("persistent memory text must not be empty")
    if len(normalized) > MAX_DREAM_FACT_TEXT_CHARS:
        raise ValueError(
            "persistent memory text must contain at most "
            f"{MAX_DREAM_FACT_TEXT_CHARS} characters"
        )
    return normalized


def _bounded_text(
    value: object,
    *,
    name: str,
    max_chars: int,
    allow_empty: bool,
) -> str:
    normalized = str(value or "").strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > max_chars:
        raise ValueError(f"{name} must contain at most {max_chars} characters")
    return normalized
