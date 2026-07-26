"""Narrow, read-only Persistent Memory projection for reference surfaces."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ContextManager, Protocol

from rpg_data.model import memory as models
from rpg_data.model.session import SessionMessage
from rpg_data.model.session_reference import SessionReferenceLocator
from rpg_data.transaction import DataTransactionMode
from rpg_memory.dream.types import PersistentMemoryLifecycle
from rpg_memory.persistent.ledger import (
    PersistentMemoryProjection,
    project_context_memories,
    project_evidence_validity,
)


@dataclass(frozen=True)
class PersistentMemoryEvidenceReference:
    turn_id: int
    message_id: int


@dataclass(frozen=True)
class PersistentMemoryReferenceItem:
    """Player-visible facts from one main-Agent-visible memory revision."""

    memory_id: str
    revision_number: int
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    evidence: tuple[PersistentMemoryEvidenceReference, ...]
    updated_at: str


class PersistentMemoryReferenceDataPort(Protocol):
    def transaction(
        self,
        mode: DataTransactionMode = DataTransactionMode.DEFERRED,
    ) -> ContextManager[None]: ...

    def require_reference_scope(
        self,
        locator: SessionReferenceLocator,
    ) -> None: ...

    def list_current_reference_memories(
        self,
        locator: SessionReferenceLocator,
        *,
        lifecycle: str | None = None,
    ) -> tuple[models.PersistentMemoryBundle, ...]: ...

    def get_current_reference_memory(
        self,
        locator: SessionReferenceLocator,
        memory_id: str,
    ) -> models.PersistentMemoryBundle | None: ...

    def list_reference_messages(
        self,
        locator: SessionReferenceLocator,
        *,
        message_ids: Sequence[int],
    ) -> tuple[SessionMessage, ...]: ...


class PersistentMemoryReferenceService:
    """Project only active, Evidence-valid current revisions in one snapshot."""

    def __init__(self, data: PersistentMemoryReferenceDataPort) -> None:
        self._data = data

    def list_memories(
        self,
        locator: SessionReferenceLocator,
    ) -> tuple[PersistentMemoryReferenceItem, ...]:
        with self._data.transaction():
            self._data.require_reference_scope(locator)
            bundles = self._data.list_current_reference_memories(
                locator,
                lifecycle=PersistentMemoryLifecycle.ACTIVE.value,
            )
            return _reference_items(
                _project_bundles(self._data, locator, bundles)
            )

    def get_memory(
        self,
        locator: SessionReferenceLocator,
        memory_id: str,
    ) -> PersistentMemoryReferenceItem | None:
        with self._data.transaction():
            self._data.require_reference_scope(locator)
            bundle = self._data.get_current_reference_memory(
                locator,
                str(memory_id),
            )
            if (
                bundle is None
                or bundle.memory.lifecycle
                != PersistentMemoryLifecycle.ACTIVE.value
            ):
                return None
            projected = _project_bundles(
                self._data,
                locator,
                (bundle,),
            )
            items = _reference_items(projected)
            return items[0] if items else None


def _project_bundles(
    data: PersistentMemoryReferenceDataPort,
    locator: SessionReferenceLocator,
    bundles: Sequence[models.PersistentMemoryBundle],
) -> tuple[PersistentMemoryProjection, ...]:
    message_ids = tuple(
        sorted({
            evidence.message_id
            for bundle in bundles
            for evidence in bundle.current_revision.evidence
        })
    )
    messages = (
        data.list_reference_messages(locator, message_ids=message_ids)
        if message_ids
        else ()
    )
    return project_context_memories(project_evidence_validity(bundles, messages))


def _reference_items(
    projected: Sequence[PersistentMemoryProjection],
) -> tuple[PersistentMemoryReferenceItem, ...]:
    return tuple(
        PersistentMemoryReferenceItem(
            memory_id=item.memory.id,
            revision_number=item.current_revision.revision_number,
            text=item.current_revision.text,
            memory_kind=item.current_revision.memory_kind,
            epistemic_status=item.current_revision.epistemic_status,
            salience=item.current_revision.salience,
            evidence=tuple(
                PersistentMemoryEvidenceReference(
                    turn_id=evidence.turn_id,
                    message_id=evidence.message_id,
                )
                for evidence in item.current_revision.evidence
            ),
            updated_at=item.memory.updated_at,
        )
        for item in projected
    )


__all__ = [
    "PersistentMemoryEvidenceReference",
    "PersistentMemoryReferenceDataPort",
    "PersistentMemoryReferenceItem",
    "PersistentMemoryReferenceService",
]
