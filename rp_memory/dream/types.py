"""Framework-free types shared by Dream source selection and generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from commons.text_identity import stable_text_identity_key


class DreamDepth(StrEnum):
    SHALLOW = "shallow"
    DEEP = "deep"


class DreamScope(StrEnum):
    INCREMENTAL = "incremental"
    FULL = "full"


class DreamSourceKind(StrEnum):
    MESSAGE = "message"
    STORY_MEMORY = "story_memory"
    SUMMARY_BATCH = "summary_batch"
    MESSAGE_TOMBSTONE = "message_tombstone"


class DreamProposalAction(StrEnum):
    ADD = "add"
    REVISE = "revise"
    SUPERSEDE = "supersede"
    RETIRE = "retire"


class DreamRetirementPolicy(StrEnum):
    """How aggressively the final reconciliation may retire ledger entries."""

    CONTRADICTION_ONLY = "contradiction_only"
    INVALIDATED_EVIDENCE = "invalidated_evidence"
    FULL_RECONCILIATION = "full_reconciliation"


MEMORY_KINDS = frozenset(
    {
        "character",
        "event",
        "relationship",
        "commitment",
        "clue",
        "world_fact",
        "state_change",
    }
)
EPISTEMIC_STATUSES = frozenset(
    {"confirmed", "reported", "inferred", "uncertain", "contradicted"}
)
MAX_DREAM_FACT_TEXT_CHARS = 1000
MAX_DREAM_REASON_CHARS = 1000
MAX_DREAM_ITEM_EVIDENCE = 64
MAX_DREAM_PROPOSAL_ITEMS = 128


def dream_fact_identity_key(
    text: str,
    memory_kind: str,
    epistemic_status: str,
) -> str:
    """Return the code-owned identity used for exact facts and new ledger rows."""

    return stable_text_identity_key(
        memory_kind,
        epistemic_status,
        text,
    )


@dataclass(frozen=True)
class DreamEvidence:
    message_id: int
    turn_id: int
    message_version: int
    content_hash: str

    def __post_init__(self) -> None:
        if self.message_id <= 0 or self.turn_id <= 0 or self.message_version <= 0:
            raise ValueError("Dream evidence identifiers and version must be positive")
        if not self.content_hash:
            raise ValueError("Dream evidence content hash is required")


@dataclass(frozen=True)
class DreamFact:
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    dedupe_key: str = ""

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Dream fact text is required")
        if len(self.text) > MAX_DREAM_FACT_TEXT_CHARS:
            raise ValueError(
                f"Dream fact text may contain at most {MAX_DREAM_FACT_TEXT_CHARS} characters"
            )
        if self.memory_kind not in MEMORY_KINDS:
            raise ValueError(f"invalid Dream memory kind: {self.memory_kind}")
        if self.epistemic_status not in EPISTEMIC_STATUSES:
            raise ValueError(
                f"invalid Dream epistemic status: {self.epistemic_status}"
            )
        if not 0.0 <= float(self.salience) <= 1.0:
            raise ValueError("Dream salience must be between 0 and 1")


@dataclass(frozen=True)
class DreamMessageSource:
    message_id: int
    version: int
    role: str
    mode: str
    content: str
    turn_id: int
    seq_in_turn: int
    content_hash: str

    def __post_init__(self) -> None:
        if self.message_id <= 0 or self.version <= 0:
            raise ValueError("Dream message id and version must be positive")
        if self.turn_id <= 0 or self.seq_in_turn <= 0:
            raise ValueError("Dream message turn metadata must be positive")
        if not self.content_hash:
            raise ValueError("Dream message content hash is required")

    @property
    def source_id(self) -> str:
        return str(self.message_id)

    @property
    def fingerprint(self) -> str:
        return f"{self.version}:{self.content_hash}"

    @property
    def evidence(self) -> DreamEvidence:
        return DreamEvidence(
            message_id=self.message_id,
            turn_id=self.turn_id,
            message_version=self.version,
            content_hash=self.content_hash,
        )


@dataclass(frozen=True)
class DreamDerivedSource:
    source_id: str
    kind: DreamSourceKind
    content: str
    version: int
    content_hash: str
    source_turn_start: int
    source_turn_end: int
    evidence_message_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {
            DreamSourceKind.STORY_MEMORY,
            DreamSourceKind.SUMMARY_BATCH,
        }:
            raise ValueError("derived Dream source must be story_memory or summary_batch")
        if not self.source_id or self.version <= 0 or not self.content_hash:
            raise ValueError("derived Dream source identity is incomplete")
        if self.source_turn_start <= 0 or self.source_turn_end < self.source_turn_start:
            raise ValueError("derived Dream source turn range is invalid")

    @property
    def fingerprint(self) -> str:
        return (
            f"{self.version}:{self.content_hash}:"
            f"{self.source_turn_start}:{self.source_turn_end}:"
            f"{','.join(str(item) for item in self.evidence_message_ids)}"
        )


@dataclass(frozen=True)
class DreamLedgerMemory:
    memory_id: str
    fact: DreamFact
    evidence: tuple[DreamEvidence, ...]
    lifecycle: str = "active"

    def __post_init__(self) -> None:
        if not self.memory_id:
            raise ValueError("Dream ledger memory id is required")


@dataclass(frozen=True)
class DreamManifestEntry:
    source_id: str
    fingerprint: str
    turn_start: int
    turn_end: int

    def __post_init__(self) -> None:
        if not self.source_id or not self.fingerprint:
            raise ValueError("Dream manifest entry identity is required")
        if self.turn_start <= 0 or self.turn_end < self.turn_start:
            raise ValueError("Dream manifest turn range is invalid")


def freeze_manifest(
    value: Mapping[str, DreamManifestEntry] | None,
) -> Mapping[str, DreamManifestEntry]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True)
class DreamSourceSnapshot:
    session_id: str
    history_fingerprint: str
    source_fingerprint: str
    ledger_revision: int
    messages: tuple[DreamMessageSource, ...] = ()
    story_memories: tuple[DreamDerivedSource, ...] = ()
    summary_batches: tuple[DreamDerivedSource, ...] = ()
    active_memories: tuple[DreamLedgerMemory, ...] = ()
    player_character_name: str = ""
    message_manifest: Mapping[str, DreamManifestEntry] = field(
        default_factory=lambda: MappingProxyType({})
    )
    story_memory_manifest: Mapping[str, DreamManifestEntry] = field(
        default_factory=lambda: MappingProxyType({})
    )
    summary_batch_manifest: Mapping[str, DreamManifestEntry] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("Dream session id is required")
        if not self.history_fingerprint or not self.source_fingerprint:
            raise ValueError("Dream source fingerprints are required")
        if self.ledger_revision < 0:
            raise ValueError("Dream ledger revision cannot be negative")
        object.__setattr__(self, "message_manifest", freeze_manifest(self.message_manifest))
        object.__setattr__(
            self,
            "story_memory_manifest",
            freeze_manifest(self.story_memory_manifest),
        )
        object.__setattr__(
            self,
            "summary_batch_manifest",
            freeze_manifest(self.summary_batch_manifest),
        )


@dataclass(frozen=True)
class DreamSourceSegment:
    source_kind: DreamSourceKind
    source_id: str
    text: str
    turn_start: int
    turn_end: int
    evidence: tuple[DreamEvidence, ...]
    deleted: bool = False


@dataclass(frozen=True)
class DreamSourceBatch:
    index: int
    segments: tuple[DreamSourceSegment, ...]
    player_character_name: str = ""


@dataclass(frozen=True)
class DreamSelection:
    snapshot: DreamSourceSnapshot
    depth: DreamDepth
    scope: DreamScope
    batches: tuple[DreamSourceBatch, ...]
    retirement_policy: DreamRetirementPolicy
    next_message_manifest: Mapping[str, DreamManifestEntry]
    next_story_memory_manifest: Mapping[str, DreamManifestEntry]
    next_summary_batch_manifest: Mapping[str, DreamManifestEntry]
    source_story_memory_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class DreamCandidate:
    candidate_id: str
    fact: DreamFact
    evidence: tuple[DreamEvidence, ...]

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("Dream candidate id is required")
        if not self.evidence:
            raise ValueError("Dream candidate must cite current message evidence")
        if len(self.evidence) > MAX_DREAM_ITEM_EVIDENCE:
            raise ValueError(
                f"Dream candidate may cite at most {MAX_DREAM_ITEM_EVIDENCE} messages"
            )


@dataclass(frozen=True)
class DreamProposalItemDraft:
    action: DreamProposalAction
    target_memory_id: str | None
    fact: DreamFact | None
    evidence: tuple[DreamEvidence, ...]
    reason: str = ""
    selected: bool = True

    def __post_init__(self) -> None:
        if self.action == DreamProposalAction.ADD:
            if self.target_memory_id is not None or self.fact is None:
                raise ValueError("Dream add requires a fact and no target memory")
        elif not self.target_memory_id:
            raise ValueError(f"Dream {self.action} requires a target memory")
        if self.action != DreamProposalAction.RETIRE and self.fact is None:
            raise ValueError(f"Dream {self.action} requires a fact")
        if self.action != DreamProposalAction.RETIRE and not self.evidence:
            raise ValueError(f"Dream {self.action} requires evidence")
        if len(self.evidence) > MAX_DREAM_ITEM_EVIDENCE:
            raise ValueError(
                f"Dream proposal item may cite at most {MAX_DREAM_ITEM_EVIDENCE} messages"
            )
        if len(self.reason) > MAX_DREAM_REASON_CHARS:
            raise ValueError(
                f"Dream proposal reason may contain at most {MAX_DREAM_REASON_CHARS} characters"
            )


@dataclass(frozen=True)
class DreamGenerationResult:
    items: tuple[DreamProposalItemDraft, ...]
    analyzed_batch_count: int
    candidate_count: int

    def __post_init__(self) -> None:
        if len(self.items) > MAX_DREAM_PROPOSAL_ITEMS:
            raise ValueError(
                f"Dream proposal may contain at most {MAX_DREAM_PROPOSAL_ITEMS} items"
            )
