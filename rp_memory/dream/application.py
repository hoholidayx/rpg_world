"""Dream Proposal and Persistent Memory application service."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import ContextManager, Protocol
from uuid import uuid4

from rpg_data import models
from rpg_data.errors import (
    DataConditionalWriteError,
    DataIntegrityError,
)
from rpg_data.transaction import DataTransactionMode
from rp_memory.dream.errors import (
    DreamActiveMemoryLimitError,
    DreamEvidenceInvalidError,
    DreamProposalConflictError,
    DreamProposalStaleError,
    DreamProposalStateError,
)
from rp_memory.dream.ledger import (
    PersistentMemoryProjection,
    project_context_memories,
    project_evidence_validity,
)
from rp_memory.dream.proposal import (
    DreamProposalItemInput,
    DreamProposalItemPatch,
    apply_item_patches,
    normalize_item_drafts,
    normalize_item_patches,
    proposal_item_values,
    require_proposal_status,
    validate_selected_uniqueness,
)
from rp_memory.dream.source_identity import (
    evidence_matches,
    history_fingerprint,
    story_memory_fingerprint,
    story_memory_source_identity,
)
from rp_memory.dream.types import (
    DreamDepth,
    DreamFailureCode,
    DreamProposalAction,
    DreamProposalStatus,
    DreamScope,
    DreamSourceSnapshot,
    MAX_ACTIVE_MEMORIES,
    PersistentMemoryLifecycle,
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class DreamDataPort(Protocol):
    def transaction(
        self,
        mode: DataTransactionMode = DataTransactionMode.DEFERRED,
    ) -> ContextManager[None]: ...

    def require_session(self, session_id: str) -> None: ...

    def list_messages(
        self,
        session_id: str,
        *,
        message_ids: Sequence[int] | None = None,
    ) -> tuple[models.SessionMessage, ...]: ...

    def list_story_memories(
        self,
        session_id: str,
    ) -> tuple[models.SessionStoryMemory, ...]: ...

    def create_proposal(
        self,
        values: models.DreamProposalCreateValues,
    ) -> models.DreamProposal: ...

    def get_proposal(self, proposal_id: str) -> models.DreamProposal | None: ...

    def list_proposals(self, session_id: str) -> tuple[models.DreamProposal, ...]: ...

    def has_proposal_with_status(self, session_id: str, status: str) -> bool: ...

    def replace_proposal_items(
        self,
        proposal_id: str,
        items: Sequence[models.DreamProposalItemRowValues],
    ) -> None: ...

    def update_proposal_items(
        self,
        proposal_id: str,
        items: Sequence[models.DreamProposalItemRowValues],
    ) -> None: ...

    def update_proposal(
        self,
        proposal_id: str,
        values: models.DreamProposalRowUpdate,
        *,
        expected_status: str,
        expected_version: int,
    ) -> models.DreamProposal: ...

    def transition_matching_proposals(
        self,
        *,
        expected_status: str,
        status: str,
        error_code: str,
        session_id: str | None = None,
        proposal_id: str | None = None,
    ) -> tuple[models.DreamProposal, ...]: ...

    def get_state(self, session_id: str) -> models.DreamState | None: ...

    def get_or_create_state(self, session_id: str) -> models.DreamState: ...

    def update_state(
        self,
        session_id: str,
        values: models.DreamStateRowValues,
        *,
        expected_version: int,
    ) -> models.DreamState: ...

    def list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | None = None,
    ) -> tuple[models.PersistentMemoryBundle, ...]: ...

    def get_memory(self, memory_id: str) -> models.PersistentMemoryBundle | None: ...

    def get_memory_by_dedupe_key(
        self,
        session_id: str,
        dedupe_key: str,
    ) -> models.PersistentMemoryBundle | None: ...

    def create_memory(
        self,
        values: models.PersistentMemoryCreateValues,
    ) -> models.PersistentMemory: ...

    def update_memory(
        self,
        memory_id: str,
        values: models.PersistentMemoryRowUpdate,
        *,
        expected_version: int,
    ) -> models.PersistentMemory: ...

    def create_revision(
        self,
        values: models.PersistentMemoryRevisionCreateValues,
    ) -> models.PersistentMemoryRevision: ...

    def mark_story_memories_processed(
        self,
        session_id: str,
        memory_ids: Sequence[int],
    ) -> int: ...

    def clear(self, session_id: str) -> models.DreamResetResult: ...


class DreamSourceSnapshotProvider(Protocol):
    def build_source_snapshot(self, session_id: str) -> DreamSourceSnapshot: ...


@dataclass(frozen=True)
class _ApplyFailure:
    error: DreamProposalStaleError | DreamEvidenceInvalidError


@dataclass(frozen=True)
class DreamApplyResult:
    proposal: models.DreamProposal
    ledger_revision: int
    active_memory_count: int
    created_memory_ids: tuple[str, ...] = ()
    revised_memory_ids: tuple[str, ...] = ()
    retired_memory_ids: tuple[str, ...] = ()
    superseded_memory_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DreamLedgerSourceSnapshot:
    session_id: str
    messages: tuple[models.SessionMessage, ...]
    story_memories: tuple[models.SessionStoryMemory, ...]
    active_memories: tuple[PersistentMemoryProjection, ...]
    state: models.DreamState
    history_fingerprint: str
    story_memory_fingerprint: str


class _SourceChangedDuringApply(RuntimeError):
    pass


class DreamApplicationService:
    """Own proposal state, ledger actions, Evidence, staleness, and Context policy."""

    def __init__(
        self,
        data: DreamDataPort,
        *,
        max_active_memories: int = MAX_ACTIVE_MEMORIES,
    ) -> None:
        if isinstance(max_active_memories, bool):
            raise ValueError(
                "max_active_memories must be an integer between 1 and "
                f"{MAX_ACTIVE_MEMORIES}"
            )
        normalized_limit = int(max_active_memories)
        if not 1 <= normalized_limit <= MAX_ACTIVE_MEMORIES:
            raise ValueError(
                "max_active_memories must be an integer between 1 and "
                f"{MAX_ACTIVE_MEMORIES}"
            )
        self._data = data
        self._max_active_memories = normalized_limit

    @property
    def max_active_memories(self) -> int:
        return self._max_active_memories

    def create_proposal(
        self,
        session_id: str,
        *,
        depth: str | DreamDepth,
        scope: str | DreamScope,
        history_fingerprint: str,
        source_fingerprint: str,
        next_messages_manifest_json: str | Mapping[str, object] = "{}",
        next_story_memories_manifest_json: str | Mapping[str, object] = "{}",
        next_summary_batches_manifest_json: str | Mapping[str, object] = "{}",
        source_story_memory_ids: Iterable[int] = (),
        proposal_id: str | None = None,
    ) -> models.DreamProposal:
        normalized_session_id = str(session_id)
        normalized_depth = _depth(depth)
        normalized_scope = _scope(scope)
        normalized_history = _fingerprint(
            history_fingerprint,
            "history_fingerprint",
        )
        normalized_source = _fingerprint(
            source_fingerprint,
            "source_fingerprint",
        )
        source_ids = _positive_ids(source_story_memory_ids, "story_memory_id")
        normalized_proposal_id = str(proposal_id or uuid4())
        if not normalized_proposal_id:
            raise ValueError("proposal_id must not be empty")

        with self._data.transaction():
            self._data.require_session(normalized_session_id)
            actual_history = history_fingerprint_for_messages(
                self._data.list_messages(normalized_session_id)
            )
            if actual_history != normalized_history:
                raise DreamProposalStaleError(
                    "Dream proposal history fingerprint does not match current history"
                )
            story_memories = {
                item.id for item in self._data.list_story_memories(normalized_session_id)
            }
            if not set(source_ids).issubset(story_memories):
                raise ValueError(
                    "Dream source story memories must belong to the Session"
                )
            state = self._data.get_or_create_state(normalized_session_id)
            if self._data.has_proposal_with_status(
                normalized_session_id,
                DreamProposalStatus.GENERATING.value,
            ):
                raise DreamProposalConflictError(
                    "Session already has a generating Dream proposal: "
                    f"{normalized_session_id}"
                )
            try:
                return self._data.create_proposal(
                    models.DreamProposalCreateValues(
                        id=normalized_proposal_id,
                        session_id=normalized_session_id,
                        depth=normalized_depth.value,
                        scope=normalized_scope.value,
                        status=DreamProposalStatus.GENERATING.value,
                        history_fingerprint=normalized_history,
                        source_fingerprint=normalized_source,
                        ledger_revision=state.ledger_revision,
                        next_messages_manifest_json=_canonical_json_object(
                            next_messages_manifest_json,
                            "next_messages_manifest_json",
                        ),
                        next_story_memories_manifest_json=_canonical_json_object(
                            next_story_memories_manifest_json,
                            "next_story_memories_manifest_json",
                        ),
                        next_summary_batches_manifest_json=_canonical_json_object(
                            next_summary_batches_manifest_json,
                            "next_summary_batches_manifest_json",
                        ),
                        source_story_memory_ids=source_ids,
                    )
                )
            except DataIntegrityError as exc:
                raise DreamProposalConflictError(
                    "Unable to create Dream proposal for Session: "
                    f"{normalized_session_id}"
                ) from exc

    def get_proposal(self, proposal_id: str) -> models.DreamProposal | None:
        return self._data.get_proposal(proposal_id)

    def list_proposals(self, session_id: str) -> list[models.DreamProposal]:
        return list(self._data.list_proposals(session_id))

    def set_proposal_ready(
        self,
        proposal_id: str,
        items: Sequence[DreamProposalItemInput],
    ) -> models.DreamProposal:
        drafts = normalize_item_drafts(items)
        with self._data.transaction():
            proposal = self._require_proposal(proposal_id)
            require_proposal_status(
                proposal,
                frozenset({DreamProposalStatus.GENERATING}),
            )
            memories = self._data.list_memories(proposal.session_id)
            memories_by_id = {item.memory.id: item for item in memories}
            item_values: list[models.DreamProposalItemRowValues] = []
            for draft in drafts:
                action = DreamProposalAction(draft.action)
                target = self._validate_draft_target(
                    proposal,
                    draft,
                    memories_by_id,
                )
                item_values.append(
                    models.DreamProposalItemRowValues(
                        id=str(uuid4()),
                        action=action.value,
                        dedupe_key=(
                            target.memory.dedupe_key
                            if target is not None
                            and action
                            in {
                                DreamProposalAction.REVISE,
                                DreamProposalAction.RETIRE,
                            }
                            else draft.dedupe_key
                        ),
                        selected=draft.selected,
                        text=draft.text,
                        memory_kind=draft.memory_kind.value,
                        epistemic_status=draft.epistemic_status.value,
                        salience=draft.salience,
                        reason=draft.reason,
                        target_memory_id=draft.target_memory_id,
                        base_revision_number=draft.base_revision_number,
                        sort_order=draft.sort_order,
                        evidence=tuple(
                            models.MemoryEvidence(
                                message_id=evidence.message_id,
                                turn_id=evidence.turn_id,
                                message_version=evidence.message_version,
                                content_hash=evidence.content_hash,
                            )
                            for evidence in draft.evidence
                        ),
                    )
                )
            validate_selected_uniqueness(
                item_values,
                {item.memory.dedupe_key: item for item in memories},
            )
            self._data.replace_proposal_items(proposal.id, item_values)
            return self._transition_proposal(
                proposal,
                DreamProposalStatus.READY,
                set_finished_at=True,
            )

    def set_proposal_failed(
        self,
        proposal_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.DreamProposal:
        with self._data.transaction():
            proposal = self._require_proposal(proposal_id)
            require_proposal_status(
                proposal,
                frozenset({DreamProposalStatus.GENERATING}),
            )
            return self._transition_proposal(
                proposal,
                DreamProposalStatus.FAILED,
                error_code=str(
                    error_code or DreamFailureCode.GENERATION_FAILED.value
                ),
                error_message=str(error_message or ""),
                set_finished_at=True,
            )

    def interrupt_generating(
        self,
        session_id: str | None = None,
        *,
        proposal_id: str | None = None,
    ) -> int:
        return len(
            self.interrupt_generating_proposals(
                session_id,
                proposal_id=proposal_id,
            )
        )

    def interrupt_generating_proposals(
        self,
        session_id: str | None = None,
        *,
        proposal_id: str | None = None,
    ) -> tuple[models.DreamProposal, ...]:
        with self._data.transaction(DataTransactionMode.IMMEDIATE):
            return self._data.transition_matching_proposals(
                expected_status=DreamProposalStatus.GENERATING.value,
                status=DreamProposalStatus.INTERRUPTED.value,
                error_code=DreamFailureCode.GENERATION_INTERRUPTED.value,
                session_id=session_id,
                proposal_id=proposal_id,
            )

    def update_proposal_items(
        self,
        proposal_id: str,
        patches: Sequence[DreamProposalItemPatch],
    ) -> models.DreamProposal:
        normalized = normalize_item_patches(patches)
        with self._data.transaction():
            proposal = self._require_proposal(proposal_id)
            require_proposal_status(
                proposal,
                frozenset({DreamProposalStatus.READY}),
            )
            all_values = apply_item_patches(proposal, normalized)
            memories = self._data.list_memories(proposal.session_id)
            validate_selected_uniqueness(
                all_values,
                {item.memory.dedupe_key: item for item in memories},
            )
            patched_ids = {item.item_id for item in normalized}
            self._data.update_proposal_items(
                proposal.id,
                tuple(item for item in all_values if item.id in patched_ids),
            )
            return self._transition_proposal(
                proposal,
                DreamProposalStatus.READY,
            )

    def reject_proposal(self, proposal_id: str) -> models.DreamProposal:
        with self._data.transaction():
            proposal = self._require_proposal(proposal_id)
            require_proposal_status(
                proposal,
                frozenset({DreamProposalStatus.READY}),
            )
            return self._transition_proposal(
                proposal,
                DreamProposalStatus.REJECTED,
                set_rejected_at=True,
                set_finished_at=True,
            )

    def apply_proposal(
        self,
        proposal_id: str,
        *,
        history_fingerprint: str | None = None,
        source_fingerprint: str | None = None,
        source_provider: DreamSourceSnapshotProvider | None = None,
    ) -> DreamApplyResult:
        current_source: DreamSourceSnapshot | None = None
        failure: _ApplyFailure | None = None
        result: DreamApplyResult | None = None
        try:
            with self._data.transaction(DataTransactionMode.IMMEDIATE):
                proposal = self._require_proposal(proposal_id)
                if source_provider is not None:
                    current_source = source_provider.build_source_snapshot(
                        proposal.session_id
                    )
                    supplied_history = current_source.history_fingerprint
                    supplied_source = current_source.source_fingerprint
                else:
                    if history_fingerprint is None or source_fingerprint is None:
                        raise ValueError(
                            "Dream apply requires fingerprints or a source provider"
                        )
                    supplied_history = _fingerprint(
                        history_fingerprint,
                        "history_fingerprint",
                    )
                    supplied_source = _fingerprint(
                        source_fingerprint,
                        "source_fingerprint",
                    )
                outcome = self._apply_inside_transaction(
                    proposal,
                    supplied_history=supplied_history,
                    supplied_source=supplied_source,
                )
                if isinstance(outcome, _ApplyFailure):
                    failure = outcome
                else:
                    result = outcome
                    if source_provider is not None and current_source is not None:
                        confirmed = source_provider.build_source_snapshot(
                            proposal.session_id
                        )
                        if (
                            confirmed.history_fingerprint
                            != current_source.history_fingerprint
                            or confirmed.source_fingerprint
                            != current_source.source_fingerprint
                        ):
                            raise _SourceChangedDuringApply
        except _SourceChangedDuringApply:
            self._mark_ready_proposal_stale(
                proposal_id,
                "Dream sources changed during proposal apply",
            )
            raise DreamProposalStaleError(
                "Dream sources changed during proposal apply"
            ) from None
        if failure is not None:
            raise failure.error
        if result is None:
            raise RuntimeError("Dream apply completed without a result")
        return result

    def list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | PersistentMemoryLifecycle | None = None,
        include_invalid_evidence: bool = True,
    ) -> list[PersistentMemoryProjection]:
        normalized_lifecycle = (
            _lifecycle(lifecycle).value if lifecycle is not None else None
        )
        with self._data.transaction():
            bundles = self._data.list_memories(
                session_id,
                lifecycle=normalized_lifecycle,
            )
            projected = project_evidence_validity(
                bundles,
                self._data.list_messages(session_id),
            )
            if include_invalid_evidence:
                return list(projected)
            return [item for item in projected if item.evidence_valid]

    def list_context_memories(
        self,
        session_id: str,
    ) -> list[PersistentMemoryProjection]:
        with self._data.transaction():
            bundles = self._data.list_memories(
                session_id,
                lifecycle=PersistentMemoryLifecycle.ACTIVE.value,
            )
            projected = project_evidence_validity(
                bundles,
                self._data.list_messages(session_id),
            )
            return list(project_context_memories(projected))

    def restore_memory(
        self,
        session_id: str,
        memory_id: str,
    ) -> PersistentMemoryProjection:
        normalized_session_id = str(session_id)
        with self._data.transaction(DataTransactionMode.IMMEDIATE):
            bundle = self._data.get_memory(memory_id)
            if bundle is None or bundle.memory.session_id != normalized_session_id:
                raise FileNotFoundError(f"Persistent memory not found: {memory_id}")
            if (
                _lifecycle(bundle.memory.lifecycle)
                is not PersistentMemoryLifecycle.RETIRED
            ):
                raise DreamProposalStateError(
                    "Only retired persistent memories can be restored"
                )
            projected = project_evidence_validity(
                (bundle,),
                self._data.list_messages(normalized_session_id),
            )[0]
            if not projected.evidence_valid:
                raise DreamEvidenceInvalidError(
                    "Retired persistent memory evidence no longer matches current history"
                )
            active_count = len(
                self._data.list_memories(
                    normalized_session_id,
                    lifecycle=PersistentMemoryLifecycle.ACTIVE.value,
                )
            )
            if active_count >= self._max_active_memories:
                raise DreamActiveMemoryLimitError(
                    f"Session may have at most {self._max_active_memories} active memories"
                )
            memory = bundle.memory
            self._data.update_memory(
                memory.id,
                models.PersistentMemoryRowUpdate(
                    lifecycle=PersistentMemoryLifecycle.ACTIVE.value,
                    current_revision_number=memory.current_revision_number,
                    superseded_by_memory_id=memory.superseded_by_memory_id,
                    version=memory.version + 1,
                ),
                expected_version=memory.version,
            )
            state = self._data.get_or_create_state(normalized_session_id)
            self._data.update_state(
                normalized_session_id,
                models.DreamStateRowValues(
                    ledger_revision=state.ledger_revision + 1,
                    messages_manifest_json=state.messages_manifest_json,
                    story_memories_manifest_json=state.story_memories_manifest_json,
                    summary_batches_manifest_json=state.summary_batches_manifest_json,
                    version=state.version + 1,
                ),
                expected_version=state.version,
            )
        restored = self._data.get_memory(memory_id)
        if restored is None:
            raise RuntimeError("Persistent Memory disappeared after restore")
        return project_evidence_validity(
            (restored,),
            self._data.list_messages(normalized_session_id),
        )[0]

    def get_state(self, session_id: str) -> models.DreamState:
        normalized_session_id = str(session_id)
        self._data.require_session(normalized_session_id)
        return self._data.get_state(normalized_session_id) or models.DreamState(
            session_id=normalized_session_id
        )

    def build_source_snapshot(self, session_id: str) -> DreamLedgerSourceSnapshot:
        normalized_session_id = str(session_id)
        with self._data.transaction():
            self._data.require_session(normalized_session_id)
            messages = self._data.list_messages(normalized_session_id)
            story_memories = self._data.list_story_memories(normalized_session_id)
            active = self._data.list_memories(
                normalized_session_id,
                lifecycle=PersistentMemoryLifecycle.ACTIVE.value,
            )
            return DreamLedgerSourceSnapshot(
                session_id=normalized_session_id,
                messages=messages,
                story_memories=story_memories,
                active_memories=project_evidence_validity(active, messages),
                state=self._data.get_state(normalized_session_id)
                or models.DreamState(session_id=normalized_session_id),
                history_fingerprint=history_fingerprint_for_messages(messages),
                story_memory_fingerprint=story_memory_fingerprint(story_memories),
            )

    def clear(self, session_id: str) -> models.DreamResetResult:
        return self._data.clear(session_id)

    def _apply_inside_transaction(
        self,
        proposal: models.DreamProposal,
        *,
        supplied_history: str,
        supplied_source: str,
    ) -> DreamApplyResult | _ApplyFailure:
        require_proposal_status(
            proposal,
            frozenset({DreamProposalStatus.READY}),
        )
        state = self._data.get_or_create_state(proposal.session_id)
        actual_messages = self._data.list_messages(proposal.session_id)
        actual_history = history_fingerprint_for_messages(actual_messages)
        stale_reason = ""
        if (
            supplied_history != proposal.history_fingerprint
            or actual_history != proposal.history_fingerprint
        ):
            stale_reason = "Dream history changed after proposal generation"
        elif supplied_source != proposal.source_fingerprint:
            stale_reason = "Dream derived sources changed after proposal generation"
        elif state.ledger_revision != proposal.ledger_revision:
            stale_reason = (
                "Persistent-memory ledger changed after proposal generation"
            )
        elif not self._proposal_story_memory_sources_match(
            proposal,
            actual_messages,
        ):
            stale_reason = (
                "Dream story-memory sources changed after proposal generation"
            )

        items = tuple(item for item in proposal.items if item.selected)
        evidence_error = (
            "" if stale_reason else self._first_invalid_evidence(items, actual_messages)
        )
        if stale_reason or evidence_error:
            error_code = (
                DreamFailureCode.EVIDENCE_INVALID
                if evidence_error
                else DreamFailureCode.PROPOSAL_STALE
            )
            self._transition_proposal(
                proposal,
                DreamProposalStatus.STALE,
                error_code=error_code.value,
                error_message=evidence_error or stale_reason,
                set_finished_at=True,
            )
            return _ApplyFailure(
                DreamEvidenceInvalidError(evidence_error)
                if evidence_error
                else DreamProposalStaleError(stale_reason)
            )

        memories = self._data.list_memories(proposal.session_id)
        active_count = self._validate_apply_and_project_active_count(
            proposal,
            items,
            memories,
        )
        created_ids: list[str] = []
        revised_ids: list[str] = []
        retired_ids: list[str] = []
        superseded_ids: list[str] = []
        memory_by_id = {item.memory.id: item for item in memories}
        memory_by_key = {item.memory.dedupe_key: item for item in memories}
        for item in items:
            action = DreamProposalAction(item.action)
            if action is DreamProposalAction.ADD:
                existing = memory_by_key.get(item.dedupe_key)
                if existing is None:
                    created_ids.append(self._create_memory(proposal, item))
                else:
                    revised_ids.append(
                        self._revive_memory(proposal, item, existing)
                    )
            elif action is DreamProposalAction.REVISE:
                target = _required_target(item, memory_by_id)
                revised_ids.append(self._revise_memory(proposal, item, target))
            elif action is DreamProposalAction.SUPERSEDE:
                target = _required_target(item, memory_by_id)
                new_id = self._create_memory(proposal, item)
                self._data.update_memory(
                    target.memory.id,
                    models.PersistentMemoryRowUpdate(
                        lifecycle=PersistentMemoryLifecycle.SUPERSEDED.value,
                        current_revision_number=(
                            target.memory.current_revision_number
                        ),
                        superseded_by_memory_id=new_id,
                        version=target.memory.version + 1,
                    ),
                    expected_version=target.memory.version,
                )
                superseded_ids.append(target.memory.id)
                created_ids.append(new_id)
            elif action is DreamProposalAction.RETIRE:
                target = _required_target(item, memory_by_id)
                self._data.update_memory(
                    target.memory.id,
                    models.PersistentMemoryRowUpdate(
                        lifecycle=PersistentMemoryLifecycle.RETIRED.value,
                        current_revision_number=(
                            target.memory.current_revision_number
                        ),
                        superseded_by_memory_id=(
                            target.memory.superseded_by_memory_id
                        ),
                        version=target.memory.version + 1,
                    ),
                    expected_version=target.memory.version,
                )
                retired_ids.append(target.memory.id)

        next_ledger_revision = state.ledger_revision + 1
        self._data.update_state(
            proposal.session_id,
            models.DreamStateRowValues(
                ledger_revision=next_ledger_revision,
                messages_manifest_json=proposal.next_messages_manifest_json,
                story_memories_manifest_json=(
                    proposal.next_story_memories_manifest_json
                ),
                summary_batches_manifest_json=(
                    proposal.next_summary_batches_manifest_json
                ),
                version=state.version + 1,
            ),
            expected_version=state.version,
        )
        self._data.mark_story_memories_processed(
            proposal.session_id,
            proposal.source_story_memory_ids,
        )
        applied = self._transition_proposal(
            proposal,
            DreamProposalStatus.APPLIED,
            set_applied_at=True,
            set_finished_at=True,
        )
        return DreamApplyResult(
            proposal=applied,
            ledger_revision=next_ledger_revision,
            active_memory_count=active_count,
            created_memory_ids=tuple(created_ids),
            revised_memory_ids=tuple(revised_ids),
            retired_memory_ids=tuple(retired_ids),
            superseded_memory_ids=tuple(superseded_ids),
        )

    def _validate_draft_target(
        self,
        proposal: models.DreamProposal,
        draft: DreamProposalItemInput,
        memories_by_id: Mapping[str, models.PersistentMemoryBundle],
    ) -> models.PersistentMemoryBundle | None:
        action = DreamProposalAction(draft.action)
        if action is DreamProposalAction.ADD:
            if draft.target_memory_id is not None or draft.base_revision_number is not None:
                raise ValueError("Dream add items cannot have a target memory")
            return None
        if draft.target_memory_id is None:
            raise ValueError(f"Dream {action.value} item requires target_memory_id")
        target = memories_by_id.get(draft.target_memory_id)
        if target is None or target.memory.session_id != proposal.session_id:
            raise FileNotFoundError(
                f"Dream target memory not found: {draft.target_memory_id}"
            )
        if draft.base_revision_number != target.memory.current_revision_number:
            raise DreamProposalStaleError(
                f"Dream target memory revision changed: {draft.target_memory_id}"
            )
        return target

    def _validate_apply_and_project_active_count(
        self,
        proposal: models.DreamProposal,
        items: Sequence[models.DreamProposalItem],
        memories: Sequence[models.PersistentMemoryBundle],
    ) -> int:
        active_count = sum(
            item.memory.lifecycle == PersistentMemoryLifecycle.ACTIVE.value
            for item in memories
        )
        memory_by_id = {item.memory.id: item for item in memories}
        memory_by_key = {item.memory.dedupe_key: item for item in memories}
        targeted: set[str] = set()
        new_keys: set[str] = set()
        for item in items:
            action = DreamProposalAction(item.action)
            if item.target_memory_id is not None:
                if item.target_memory_id in targeted:
                    raise DreamProposalStateError(
                        "Proposal targets memory more than once: "
                        f"{item.target_memory_id}"
                    )
                targeted.add(item.target_memory_id)
                target = memory_by_id.get(item.target_memory_id)
                if target is None or target.memory.session_id != proposal.session_id:
                    raise DreamProposalStaleError(
                        "Dream target memory no longer exists: "
                        f"{item.target_memory_id}"
                    )
                if (
                    target.memory.lifecycle
                    != PersistentMemoryLifecycle.ACTIVE.value
                ):
                    raise DreamProposalStaleError(
                        "Dream target memory is no longer active: "
                        f"{item.target_memory_id}"
                    )
                if (
                    target.memory.current_revision_number
                    != (item.base_revision_number or 0)
                ):
                    raise DreamProposalStaleError(
                        "Dream target memory revision changed: "
                        f"{item.target_memory_id}"
                    )
            if action in {DreamProposalAction.ADD, DreamProposalAction.SUPERSEDE}:
                if item.dedupe_key in new_keys:
                    raise DreamProposalStateError(
                        "Proposal creates duplicate memory key: "
                        f"{item.dedupe_key}"
                    )
                new_keys.add(item.dedupe_key)
                existing = memory_by_key.get(item.dedupe_key)
                if existing is not None and not (
                    action is DreamProposalAction.ADD
                    and existing.memory.lifecycle
                    == PersistentMemoryLifecycle.RETIRED.value
                ):
                    raise DreamProposalStateError(
                        f"Persistent memory key already exists: {item.dedupe_key}"
                    )
            if action is DreamProposalAction.ADD:
                active_count += 1
            elif action is DreamProposalAction.RETIRE:
                active_count -= 1
        if active_count > self._max_active_memories:
            raise DreamActiveMemoryLimitError(
                f"Session may have at most {self._max_active_memories} active memories; "
                f"proposal would create {active_count}"
            )
        return active_count

    def _first_invalid_evidence(
        self,
        items: Sequence[models.DreamProposalItem],
        messages: Sequence[models.SessionMessage],
    ) -> str:
        messages_by_id = {item.id: item for item in messages}
        for item in items:
            if DreamProposalAction(item.action) is DreamProposalAction.RETIRE:
                continue
            if not item.evidence:
                return f"Dream proposal item has no evidence: {item.id}"
            for evidence in item.evidence:
                if not evidence_matches(
                    messages_by_id.get(evidence.message_id),
                    message_id=evidence.message_id,
                    turn_id=evidence.turn_id,
                    message_version=evidence.message_version,
                    expected_content_hash=evidence.content_hash,
                ):
                    return (
                        "Dream evidence no longer matches current history: "
                        f"item={item.id}, message={evidence.message_id}"
                    )
        return ""

    def _proposal_story_memory_sources_match(
        self,
        proposal: models.DreamProposal,
        messages: Sequence[models.SessionMessage],
    ) -> bool:
        if not proposal.source_story_memory_ids:
            return True
        source_ids = set(proposal.source_story_memory_ids)
        memories = tuple(
            item
            for item in self._data.list_story_memories(proposal.session_id)
            if item.id in source_ids
        )
        if len(memories) != len(source_ids):
            return False
        try:
            manifest = json.loads(
                proposal.next_story_memories_manifest_json or "{}"
            )
        except json.JSONDecodeError:
            return False
        if not isinstance(manifest, dict):
            return False
        messages_by_id = {item.id: item for item in messages}
        for memory in memories:
            entry = manifest.get(str(memory.id))
            if not isinstance(entry, dict):
                return False
            expected = str(entry.get("fingerprint") or "")
            if (
                story_memory_source_identity(memory, messages_by_id).fingerprint
                != expected
            ):
                return False
        return True

    def _create_memory(
        self,
        proposal: models.DreamProposal,
        item: models.DreamProposalItem,
    ) -> str:
        memory_id = str(uuid4())
        self._data.create_memory(
            models.PersistentMemoryCreateValues(
                id=memory_id,
                session_id=proposal.session_id,
                dedupe_key=item.dedupe_key,
                lifecycle=PersistentMemoryLifecycle.ACTIVE.value,
                current_revision_number=1,
                superseded_by_memory_id=None,
                created_from_proposal_id=proposal.id,
            )
        )
        self._create_revision(proposal, item, memory_id, 1)
        return memory_id

    def _revive_memory(
        self,
        proposal: models.DreamProposal,
        item: models.DreamProposalItem,
        existing: models.PersistentMemoryBundle,
    ) -> str:
        if (
            existing.memory.lifecycle
            != PersistentMemoryLifecycle.RETIRED.value
        ):
            raise DreamProposalStaleError(
                f"Persistent memory key is no longer retired: {item.dedupe_key}"
            )
        revision_number = existing.memory.current_revision_number + 1
        self._create_revision(
            proposal,
            item,
            existing.memory.id,
            revision_number,
        )
        self._data.update_memory(
            existing.memory.id,
            models.PersistentMemoryRowUpdate(
                lifecycle=PersistentMemoryLifecycle.ACTIVE.value,
                current_revision_number=revision_number,
                superseded_by_memory_id=None,
                version=existing.memory.version + 1,
            ),
            expected_version=existing.memory.version,
        )
        return existing.memory.id

    def _revise_memory(
        self,
        proposal: models.DreamProposal,
        item: models.DreamProposalItem,
        target: models.PersistentMemoryBundle,
    ) -> str:
        revision_number = target.memory.current_revision_number + 1
        self._create_revision(
            proposal,
            item,
            target.memory.id,
            revision_number,
        )
        self._data.update_memory(
            target.memory.id,
            models.PersistentMemoryRowUpdate(
                lifecycle=target.memory.lifecycle,
                current_revision_number=revision_number,
                superseded_by_memory_id=target.memory.superseded_by_memory_id,
                version=target.memory.version + 1,
            ),
            expected_version=target.memory.version,
        )
        return target.memory.id

    def _create_revision(
        self,
        proposal: models.DreamProposal,
        item: models.DreamProposalItem,
        memory_id: str,
        revision_number: int,
    ) -> None:
        self._data.create_revision(
            models.PersistentMemoryRevisionCreateValues(
                memory_id=memory_id,
                revision_number=revision_number,
                text=item.text,
                memory_kind=item.memory_kind,
                epistemic_status=item.epistemic_status,
                salience=item.salience,
                source_proposal_id=proposal.id,
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
        )

    def _transition_proposal(
        self,
        proposal: models.DreamProposal,
        status: DreamProposalStatus,
        *,
        error_code: str = "",
        error_message: str = "",
        set_applied_at: bool = False,
        set_rejected_at: bool = False,
        set_finished_at: bool = False,
    ) -> models.DreamProposal:
        try:
            return self._data.update_proposal(
                proposal.id,
                models.DreamProposalRowUpdate(
                    status=status.value,
                    error_code=error_code,
                    error_message=error_message,
                    version=proposal.version + 1,
                    set_applied_at=set_applied_at,
                    set_rejected_at=set_rejected_at,
                    set_finished_at=set_finished_at,
                ),
                expected_status=proposal.status,
                expected_version=proposal.version,
            )
        except DataConditionalWriteError as exc:
            raise DreamProposalStateError(
                f"Dream proposal changed during transition: {proposal.id}"
            ) from exc

    def _mark_ready_proposal_stale(self, proposal_id: str, reason: str) -> None:
        with self._data.transaction(DataTransactionMode.IMMEDIATE):
            proposal = self._require_proposal(proposal_id)
            require_proposal_status(
                proposal,
                frozenset({DreamProposalStatus.READY}),
            )
            self._transition_proposal(
                proposal,
                DreamProposalStatus.STALE,
                error_code=DreamFailureCode.PROPOSAL_STALE.value,
                error_message=reason,
                set_finished_at=True,
            )

    def _require_proposal(self, proposal_id: str) -> models.DreamProposal:
        proposal = self._data.get_proposal(proposal_id)
        if proposal is None:
            raise FileNotFoundError(f"Dream proposal not found: {proposal_id}")
        return proposal


def _required_target(
    item: models.DreamProposalItem,
    memories_by_id: Mapping[str, models.PersistentMemoryBundle],
) -> models.PersistentMemoryBundle:
    target = memories_by_id.get(item.target_memory_id or "")
    if target is None:
        raise DreamProposalStaleError(
            f"Dream target memory no longer exists: {item.target_memory_id}"
        )
    return target


def history_fingerprint_for_messages(
    messages: Sequence[models.SessionMessage],
) -> str:
    return history_fingerprint(messages)


def _depth(value: str | DreamDepth) -> DreamDepth:
    try:
        return value if isinstance(value, DreamDepth) else DreamDepth(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"Unsupported Dream depth: {value}") from exc


def _scope(value: str | DreamScope) -> DreamScope:
    try:
        return value if isinstance(value, DreamScope) else DreamScope(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"Unsupported Dream scope: {value}") from exc


def _lifecycle(
    value: str | PersistentMemoryLifecycle,
) -> PersistentMemoryLifecycle:
    try:
        return (
            value
            if isinstance(value, PersistentMemoryLifecycle)
            else PersistentMemoryLifecycle(str(value).strip().lower())
        )
    except ValueError as exc:
        raise ValueError(f"Unsupported Dream lifecycle: {value}") from exc


def _fingerprint(value: object, name: str) -> str:
    normalized = str(value or "").strip().lower()
    if _SHA256_RE.fullmatch(normalized) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return normalized


def _positive_ids(values: Iterable[int], name: str) -> tuple[int, ...]:
    normalized: set[int] = set()
    for value in values:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a positive integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
        if parsed <= 0:
            raise ValueError(f"{name} must be a positive integer")
        normalized.add(parsed)
    return tuple(sorted(normalized))


def _canonical_json_object(
    value: str | Mapping[str, object],
    name: str,
) -> str:
    if isinstance(value, str):
        try:
            decoded = json.loads(value or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name} must be a JSON object") from exc
    else:
        decoded = dict(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"{name} must be a JSON object")
    return json.dumps(
        decoded,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
