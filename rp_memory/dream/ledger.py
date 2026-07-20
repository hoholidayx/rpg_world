"""Pure Persistent Memory Evidence and Context projection policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from rpg_data.model import memory as models
from rpg_data.model.session import SessionMessage
from rp_memory.dream.source_identity import evidence_matches
from rp_memory.dream.types import PersistentMemoryLifecycle
from rp_memory.memory_types import MemoryKind

_CONTEXT_KIND_ORDER = {kind.value: index for index, kind in enumerate(MemoryKind)}


@dataclass(frozen=True)
class PersistentMemoryProjection:
    """Domain projection of one persisted bundle and its Evidence validity."""

    bundle: models.PersistentMemoryBundle
    evidence_valid: bool

    @property
    def memory(self) -> models.PersistentMemory:
        return self.bundle.memory

    @property
    def current_revision(self) -> models.PersistentMemoryRevision:
        return self.bundle.current_revision

    @property
    def revisions(self) -> tuple[models.PersistentMemoryRevision, ...]:
        return self.bundle.revisions

    @property
    def text(self) -> str:
        return self.current_revision.text

    @property
    def memory_kind(self) -> str:
        return self.current_revision.memory_kind

    @property
    def epistemic_status(self) -> str:
        return self.current_revision.epistemic_status

    @property
    def salience(self) -> float:
        return self.current_revision.salience


def revision_evidence_valid(
    revision: models.PersistentMemoryRevision,
    messages_by_id: Mapping[int, SessionMessage],
) -> bool:
    if not revision.evidence:
        return False
    return all(
        evidence_matches(
            messages_by_id.get(item.message_id),
            message_id=item.message_id,
            turn_id=item.turn_id,
            message_version=item.message_version,
            expected_content_hash=item.content_hash,
        )
        for item in revision.evidence
    )


def project_evidence_validity(
    bundles: Sequence[models.PersistentMemoryBundle],
    messages: Sequence[SessionMessage],
) -> tuple[PersistentMemoryProjection, ...]:
    messages_by_id = {item.id: item for item in messages}
    return tuple(
        PersistentMemoryProjection(
            bundle=bundle,
            evidence_valid=revision_evidence_valid(
                bundle.current_revision,
                messages_by_id,
            ),
        )
        for bundle in bundles
    )


def project_context_memories(
    bundles: Sequence[PersistentMemoryProjection],
) -> tuple[PersistentMemoryProjection, ...]:
    projected = (
        replace(
            bundle,
            bundle=replace(
                bundle.bundle,
                revisions=(bundle.current_revision,),
            ),
        )
        for bundle in bundles
        if bundle.memory.lifecycle == PersistentMemoryLifecycle.ACTIVE.value
        and bundle.evidence_valid
    )
    return tuple(
        sorted(
            projected,
            key=lambda bundle: (
                _CONTEXT_KIND_ORDER.get(
                    bundle.current_revision.memory_kind,
                    len(_CONTEXT_KIND_ORDER),
                ),
                bundle.memory.id,
            ),
        )
    )
