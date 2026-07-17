"""Adapter from the Dream process contracts to public ``rpg_data`` services."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Mapping

import yaml

from rpg_data import models
from rpg_data.services.dream_memory import (
    DreamEvidenceInvalidError,
    DreamProposalStaleError,
)
from rpg_data.services.dream_source_identity import story_memory_source_identity
from rpg_data.services.gateway import DataServiceGateway, get_data_service_gateway
from rpg_data.services.session_role import SessionPlayerCharacterState

from dream_service.contracts import (
    DreamEvidenceView,
    DreamMemoryListView,
    DreamMemoryView,
    DreamProposalItemUpdate,
    DreamProposalItemView,
    DreamProposalListView,
    DreamProposalView,
    DreamRepository,
    DreamRevisionView,
)
from rp_memory.dream.source import combine_source_fingerprint
from rp_memory.dream.types import (
    DreamDerivedSource,
    DreamEvidence,
    DreamFact,
    DreamLedgerMemory,
    DreamManifestEntry,
    DreamMessageSource,
    DreamProposalAction,
    DreamProposalItemDraft,
    DreamSelection,
    DreamSourceKind,
    DreamSourceSnapshot,
    dream_fact_identity_key,
)

_FRONT_MATTER = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|\Z)", re.DOTALL)


class _SourceChangedDuringApply(RuntimeError):
    pass


class RPGDataDreamRepository(DreamRepository):
    """Translate only through public rpg_data models and service methods."""

    def __init__(self, gateway: DataServiceGateway | None = None) -> None:
        self.gateway = gateway or get_data_service_gateway()

    def build_source_snapshot(self, session_id: str) -> DreamSourceSnapshot:
        source = self.gateway.dream.build_source_snapshot(session_id)
        messages = tuple(_message_source(item) for item in source.messages)
        source_message_by_id = {item.id: item for item in source.messages}
        messages_by_turn: dict[int, tuple[int, ...]] = {}
        eligible_messages_by_id: dict[int, models.SessionMessage] = {}
        summary_message_ids: dict[int, tuple[int, ...]] = {}
        summary_turn_ranges: dict[int, tuple[int, int]] = {}
        for message in messages:
            if (
                message.role not in {"user", "assistant"}
                or message.mode not in {"ic", "gm"}
            ):
                continue
            messages_by_turn[message.turn_id] = (
                *messages_by_turn.get(message.turn_id, ()),
                message.message_id,
            )
            source_message = source_message_by_id[message.message_id]
            eligible_messages_by_id[message.message_id] = source_message
            if (
                not source_message.summary_processed
                or source_message.summary_batch_id is None
            ):
                continue
            batch_id = int(source_message.summary_batch_id)
            summary_message_ids[batch_id] = (
                *summary_message_ids.get(batch_id, ()),
                message.message_id,
            )
            previous_range = summary_turn_ranges.get(batch_id)
            summary_turn_ranges[batch_id] = (
                min(previous_range[0], message.turn_id)
                if previous_range is not None
                else message.turn_id,
                max(previous_range[1], message.turn_id)
                if previous_range is not None
                else message.turn_id,
            )
        story_memories = tuple(
            _story_memory_source(item, eligible_messages_by_id)
            for item in source.story_memories
        )
        summary_batches = _load_summary_sources(
            self.gateway.catalog.resolve_session_runtime_dir(session_id),
            messages_by_turn,
            summary_message_ids=summary_message_ids,
            summary_turn_ranges=summary_turn_ranges,
        )
        player_state = self.gateway.session_roles.get_state(session_id)
        player_character_name = (
            player_state.player.name
            if player_state.status == models.PLAYER_CHARACTER_STATUS_BOUND
            and player_state.player is not None
            else ""
        )
        player_character_fingerprint = _player_character_fingerprint(player_state)
        source_fingerprint = combine_source_fingerprint(
            source.story_memory_fingerprint,
            summary_batches,
            player_character_fingerprint=player_character_fingerprint,
        )
        return DreamSourceSnapshot(
            session_id=source.session_id,
            history_fingerprint=source.history_fingerprint,
            source_fingerprint=source_fingerprint,
            ledger_revision=source.state.ledger_revision,
            messages=messages,
            story_memories=story_memories,
            summary_batches=summary_batches,
            active_memories=tuple(
                _ledger_memory(bundle) for bundle in source.active_memories
            ),
            player_character_name=player_character_name,
            message_manifest=_parse_manifest(source.state.messages_manifest_json),
            story_memory_manifest=_parse_manifest(
                source.state.story_memories_manifest_json
            ),
            summary_batch_manifest=_parse_manifest(
                source.state.summary_batches_manifest_json
            ),
        )

    def create_proposal(self, selection: DreamSelection) -> DreamProposalView:
        proposal = self.gateway.dream.create_proposal(
            selection.snapshot.session_id,
            depth=selection.depth.value,
            scope=selection.scope.value,
            history_fingerprint=selection.snapshot.history_fingerprint,
            source_fingerprint=selection.snapshot.source_fingerprint,
            next_messages_manifest_json=_manifest_json(
                selection.next_message_manifest
            ),
            next_story_memories_manifest_json=_manifest_json(
                selection.next_story_memory_manifest
            ),
            next_summary_batches_manifest_json=_manifest_json(
                selection.next_summary_batch_manifest
            ),
            source_story_memory_ids=selection.source_story_memory_ids,
        )
        return _proposal_view(proposal)

    def get_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView | None:
        proposal = self.gateway.dream.get_proposal(proposal_id)
        if proposal is None or proposal.session_id != session_id:
            return None
        return _proposal_view(proposal)

    def list_proposals(self, session_id: str) -> DreamProposalListView:
        return DreamProposalListView(
            items=tuple(
                _proposal_view(proposal)
                for proposal in self.gateway.dream.list_proposals(session_id)
            )
        )

    def set_proposal_ready(
        self,
        proposal_id: str,
        items: tuple[DreamProposalItemDraft, ...],
    ) -> DreamProposalView:
        proposal = self.gateway.dream.get_proposal(proposal_id)
        if proposal is None:
            raise FileNotFoundError(f"Dream proposal not found: {proposal_id}")
        targets = {
            bundle.memory.id: bundle
            for bundle in self.gateway.dream.list_memories(
                proposal.session_id,
                lifecycle=models.DREAM_LIFECYCLE_ACTIVE,
            )
        }
        drafts = tuple(
            _data_item_draft(item, index=index, targets=targets)
            for index, item in enumerate(items)
        )
        return _proposal_view(
            self.gateway.dream.set_proposal_ready(proposal_id, drafts)
        )

    def set_proposal_failed(
        self,
        proposal_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> DreamProposalView:
        return _proposal_view(
            self.gateway.dream.set_proposal_failed(
                proposal_id,
                error_code=error_code,
                error_message=error_message,
            )
        )

    def interrupt_generating(self) -> int:
        return self.gateway.dream.interrupt_generating()

    def update_proposal_items(
        self,
        session_id: str,
        proposal_id: str,
        updates: tuple[DreamProposalItemUpdate, ...],
    ) -> DreamProposalView:
        self._require_proposal(session_id, proposal_id)
        patches = tuple(
            models.DreamProposalItemPatch(
                item_id=item.item_id,
                selected=item.selected,
                text=item.text,
                memory_kind=item.memory_kind,
                epistemic_status=item.epistemic_status,
                salience=item.salience,
            )
            for item in updates
        )
        return _proposal_view(
            self.gateway.dream.update_proposal_items(proposal_id, patches)
        )

    def reject_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView:
        self._require_proposal(session_id, proposal_id)
        return _proposal_view(self.gateway.dream.reject_proposal(proposal_id))

    def apply_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView:
        deferred_error: DreamProposalStaleError | DreamEvidenceInvalidError | None = None
        try:
            with self.gateway.database.atomic("IMMEDIATE"):
                self._require_proposal(session_id, proposal_id)
                current = self.build_source_snapshot(session_id)
                try:
                    result = self.gateway.dream.apply_proposal(
                        proposal_id,
                        history_fingerprint=current.history_fingerprint,
                        source_fingerprint=current.source_fingerprint,
                    )
                except (DreamProposalStaleError, DreamEvidenceInvalidError) as exc:
                    # rpg_data records the terminal stale state before raising.
                    # Keep that nested transaction committed by deferring the
                    # public exception until the outer IMMEDIATE transaction ends.
                    deferred_error = exc
                    result = None
                if deferred_error is None:
                    confirmed = self.build_source_snapshot(session_id)
                    if (
                        confirmed.history_fingerprint != current.history_fingerprint
                        or confirmed.source_fingerprint != current.source_fingerprint
                    ):
                        raise _SourceChangedDuringApply
        except _SourceChangedDuringApply:
            # The successful nested Apply was rolled back with the outer
            # transaction. Re-enter the public data boundary with a deliberately
            # stale history fingerprint so the proposal itself becomes stale.
            try:
                forced_stale_history = (
                    ("0" if current.history_fingerprint[0] != "0" else "1")
                    + current.history_fingerprint[1:]
                )
                self.gateway.dream.apply_proposal(
                    proposal_id,
                    history_fingerprint=forced_stale_history,
                    source_fingerprint=current.source_fingerprint,
                )
            except DreamProposalStaleError:
                pass
            raise DreamProposalStaleError(
                "Dream sources changed during proposal apply"
            ) from None
        if deferred_error is not None:
            raise deferred_error
        assert result is not None
        return _proposal_view(result.proposal)

    def list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | None = None,
    ) -> DreamMemoryListView:
        if lifecycle is not None and lifecycle not in models.DREAM_LIFECYCLES:
            raise ValueError(f"Unsupported Dream lifecycle: {lifecycle}")
        all_bundles = self.gateway.dream.list_memories(session_id)
        bundles = tuple(
            item
            for item in all_bundles
            if lifecycle is None or item.memory.lifecycle == lifecycle
        )
        return DreamMemoryListView(
            items=tuple(_memory_view(item) for item in bundles),
            active_count=sum(
                item.memory.lifecycle == models.DREAM_LIFECYCLE_ACTIVE
                for item in all_bundles
            ),
            active_limit=self.gateway.dream.max_active_memories,
        )

    def restore_memory(
        self,
        session_id: str,
        memory_id: str,
    ) -> DreamMemoryView:
        return _memory_view(
            self.gateway.dream.restore_memory(session_id, memory_id)
        )

    def close(self) -> None:
        self.gateway.close()

    def _require_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> models.DreamProposal:
        proposal = self.gateway.dream.get_proposal(proposal_id)
        if proposal is None or proposal.session_id != session_id:
            raise FileNotFoundError(f"Dream proposal not found: {proposal_id}")
        return proposal


def _message_source(message: models.SessionMessage) -> DreamMessageSource:
    return DreamMessageSource(
        message_id=message.id,
        version=message.version,
        role=message.role,
        mode=message.mode,
        content=message.content,
        turn_id=message.turn_id,
        seq_in_turn=message.seq_in_turn,
        content_hash=_content_hash(message.content),
    )


def _story_memory_source(
    memory: models.SessionStoryMemory,
    messages_by_id: Mapping[int, models.SessionMessage],
) -> DreamDerivedSource:
    identity = story_memory_source_identity(memory, messages_by_id)
    return DreamDerivedSource(
        source_id=str(memory.id),
        kind=DreamSourceKind.STORY_MEMORY,
        content=memory.text,
        version=memory.version,
        content_hash=_content_hash(memory.text),
        source_turn_start=memory.source_turn_start,
        source_turn_end=memory.source_turn_end,
        evidence_message_ids=identity.evidence_message_ids,
    )


def _load_summary_sources(
    session_runtime_dir: Path,
    messages_by_turn: Mapping[int, tuple[int, ...]],
    *,
    summary_message_ids: Mapping[int, tuple[int, ...]],
    summary_turn_ranges: Mapping[int, tuple[int, int]],
) -> tuple[DreamDerivedSource, ...]:
    summary_dir = session_runtime_dir / "summaries"
    if not summary_dir.is_dir():
        return ()
    result: list[DreamDerivedSource] = []
    seen_ids: set[str] = set()
    for path in sorted(summary_dir.glob("*.md")):
        if path.name == "overall.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = _FRONT_MATTER.match(text)
        if match is None:
            continue
        try:
            metadata = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(metadata, dict):
            continue
        batch_id = _optional_positive_int(metadata.get("batch_id"), allow_zero=True)
        declared_message_ids = _optional_positive_ints(
            metadata.get("source_message_ids")
        )
        if "source_message_ids" in metadata and not declared_message_ids:
            continue
        declared_start = _optional_positive_int(metadata.get("source_turn_start"))
        declared_end = _optional_positive_int(metadata.get("source_turn_end"))
        body = text[match.end() :].strip()
        if batch_id is None or not body:
            continue
        evidence_message_ids = summary_message_ids.get(batch_id)
        evidence_turn_range = summary_turn_ranges.get(batch_id)
        if not evidence_message_ids or evidence_turn_range is None:
            continue
        if declared_message_ids is not None and (
            tuple(sorted(declared_message_ids))
            != tuple(sorted(evidence_message_ids))
        ):
            continue
        if declared_start is not None or declared_end is not None:
            if (
                declared_start is None
                or declared_end is None
                or declared_end < declared_start
            ):
                continue
            start, end = declared_start, declared_end
        else:
            start, end = evidence_turn_range
        range_message_ids = _evidence_ids_for_range(messages_by_turn, start, end)
        if tuple(sorted(range_message_ids)) != tuple(sorted(evidence_message_ids)):
            continue
        source_id = str(batch_id)
        if source_id in seen_ids:
            continue
        seen_ids.add(source_id)
        result.append(
            DreamDerivedSource(
                source_id=source_id,
                kind=DreamSourceKind.SUMMARY_BATCH,
                content=body,
                version=1,
                content_hash=_content_hash(text),
                source_turn_start=start,
                source_turn_end=end,
                evidence_message_ids=evidence_message_ids,
            )
        )
    return tuple(result)


def _evidence_ids_for_range(
    messages_by_turn: Mapping[int, tuple[int, ...]],
    start: int,
    end: int,
) -> tuple[int, ...]:
    return tuple(
        message_id
        for turn_id in range(start, end + 1)
        for message_id in messages_by_turn.get(turn_id, ())
    )


def _optional_positive_ints(value: object) -> tuple[int, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return ()
    result: list[int] = []
    for item in value:
        parsed = _optional_positive_int(item)
        if parsed is None:
            return ()
        if parsed not in result:
            result.append(parsed)
    return tuple(result)


def _ledger_memory(bundle: models.PersistentMemoryBundle) -> DreamLedgerMemory:
    revision = bundle.current_revision
    return DreamLedgerMemory(
        memory_id=bundle.memory.id,
        lifecycle=bundle.memory.lifecycle,
        fact=DreamFact(
            text=revision.text,
            memory_kind=revision.memory_kind,
            epistemic_status=revision.epistemic_status,
            salience=revision.salience,
            dedupe_key=bundle.memory.dedupe_key,
        ),
        evidence=tuple(
            DreamEvidence(
                message_id=item.message_id,
                turn_id=item.turn_id,
                message_version=item.message_version,
                content_hash=item.content_hash,
            )
            for item in revision.evidence
        ),
    )


def _data_item_draft(
    item: DreamProposalItemDraft,
    *,
    index: int,
    targets: Mapping[str, models.PersistentMemoryBundle],
) -> models.DreamProposalItemDraft:
    target = targets.get(item.target_memory_id or "")
    if item.action != DreamProposalAction.ADD and target is None:
        raise FileNotFoundError(
            f"Dream target memory not found: {item.target_memory_id}"
        )
    if item.action == DreamProposalAction.RETIRE:
        assert target is not None
        fact = target.current_revision
        dedupe_key = target.memory.dedupe_key
        text = ""
    else:
        if item.fact is None:
            raise ValueError(f"Dream {item.action.value} item is missing a fact")
        fact = item.fact
        text = fact.text
        if item.action == DreamProposalAction.REVISE:
            assert target is not None
            dedupe_key = target.memory.dedupe_key
        else:
            dedupe_key = dream_fact_identity_key(
                fact.text,
                fact.memory_kind,
                fact.epistemic_status,
            )
    return models.DreamProposalItemDraft(
        action=item.action.value,
        dedupe_key=dedupe_key,
        text=text,
        memory_kind=fact.memory_kind,
        epistemic_status=fact.epistemic_status,
        salience=fact.salience,
        target_memory_id=item.target_memory_id,
        base_revision_number=(
            target.memory.current_revision_number if target is not None else None
        ),
        selected=item.selected,
        sort_order=index,
        reason=item.reason,
        evidence=tuple(
            models.DreamEvidenceDraft(
                message_id=evidence.message_id,
                turn_id=evidence.turn_id,
                message_version=evidence.message_version,
                content_hash=evidence.content_hash,
            )
            for evidence in item.evidence
        ),
    )


def _proposal_view(proposal: models.DreamProposal) -> DreamProposalView:
    return DreamProposalView(
        proposal_id=proposal.id,
        session_id=proposal.session_id,
        depth=proposal.depth,
        scope=proposal.scope,
        status=proposal.status,
        ledger_revision=proposal.ledger_revision,
        items=tuple(
            DreamProposalItemView(
                item_id=item.id,
                action=item.action,
                target_memory_id=item.target_memory_id,
                base_revision_number=item.base_revision_number,
                selected=item.selected,
                text=item.text or None,
                memory_kind=item.memory_kind or None,
                epistemic_status=item.epistemic_status or None,
                salience=item.salience,
                reason=item.reason,
                evidence=tuple(
                    DreamEvidenceView(
                        message_id=evidence.message_id,
                        turn_id=evidence.turn_id,
                        message_version=evidence.message_version,
                        content_hash=evidence.content_hash,
                    )
                    for evidence in item.evidence
                ),
            )
            for item in proposal.items
        ),
        error_code=proposal.error_code,
        error_message=proposal.error_message,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        finished_at=proposal.finished_at,
    )


def _memory_view(bundle: models.PersistentMemoryBundle) -> DreamMemoryView:
    current = bundle.current_revision
    return DreamMemoryView(
        memory_id=bundle.memory.id,
        session_id=bundle.memory.session_id,
        lifecycle=bundle.memory.lifecycle,
        current_revision_number=bundle.memory.current_revision_number,
        superseded_by_memory_id=bundle.memory.superseded_by_memory_id,
        evidence_valid=bundle.evidence_valid,
        current_revision=_revision_view(current, bundle.memory.dedupe_key),
        revisions=tuple(
            _revision_view(revision, bundle.memory.dedupe_key)
            for revision in bundle.revisions
        ),
        evidence=tuple(
            DreamEvidenceView(
                message_id=evidence.message_id,
                turn_id=evidence.turn_id,
                message_version=evidence.message_version,
                content_hash=evidence.content_hash,
            )
            for evidence in current.evidence
        ),
        created_at=bundle.memory.created_at,
        updated_at=bundle.memory.updated_at,
    )


def _revision_view(
    revision: models.PersistentMemoryRevision,
    dedupe_key: str,
) -> DreamRevisionView:
    return DreamRevisionView(
        revision_number=revision.revision_number,
        text=revision.text,
        memory_kind=revision.memory_kind,
        epistemic_status=revision.epistemic_status,
        salience=revision.salience,
        dedupe_key=dedupe_key,
        proposal_id=revision.source_proposal_id,
        created_at=revision.created_at,
    )


def _parse_manifest(raw: str) -> Mapping[str, DreamManifestEntry]:
    try:
        decoded = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    result: dict[str, DreamManifestEntry] = {}
    for source_id, value in decoded.items():
        if not isinstance(value, dict):
            continue
        try:
            result[str(source_id)] = DreamManifestEntry(
                source_id=str(source_id),
                fingerprint=str(value["fingerprint"]),
                turn_start=int(value["turnStart"]),
                turn_end=int(value["turnEnd"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _manifest_json(entries: Mapping[str, DreamManifestEntry]) -> str:
    return json.dumps(
        {
            source_id: {
                "fingerprint": entry.fingerprint,
                "turnStart": entry.turn_start,
                "turnEnd": entry.turn_end,
            }
            for source_id, entry in sorted(entries.items())
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _optional_positive_int(value: object, *, allow_zero: bool = False) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    minimum = 0 if allow_zero else 1
    return parsed if parsed >= minimum else None


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
def _player_character_fingerprint(player_state: SessionPlayerCharacterState) -> str:
    if (
        player_state.status != models.PLAYER_CHARACTER_STATUS_BOUND
        or player_state.player is None
    ):
        return ""
    player = player_state.player
    payload = json.dumps(
        {
            "characterId": player.character_id,
            "mountId": player.mount_id,
            "storyId": player.story_id,
            "name": player.name,
            "updatedAt": player.updated_at,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _content_hash(payload)
