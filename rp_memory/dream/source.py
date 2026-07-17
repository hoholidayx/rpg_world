"""Deterministic source selection and turn-safe batching for Dream runs."""

from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping, Sequence

from rp_memory.dream.errors import DreamSourceError
from rp_memory.dream.types import (
    DreamDepth,
    DreamDerivedSource,
    DreamEvidence,
    DreamManifestEntry,
    DreamMessageSource,
    DreamRetirementPolicy,
    DreamScope,
    DreamSelection,
    DreamSourceBatch,
    DreamSourceKind,
    DreamSourceSegment,
    DreamSourceSnapshot,
)

_ALLOWED_ROLES = frozenset({"user", "assistant"})
_ALLOWED_MODES = frozenset({"ic", "gm"})


class DreamSourceSelector:
    def __init__(self, *, max_map_turns: int = 12, max_map_chars: int = 24000) -> None:
        self.max_map_turns = max(1, int(max_map_turns))
        self.max_map_chars = max(1000, int(max_map_chars))

    def select(
        self,
        snapshot: DreamSourceSnapshot,
        *,
        depth: DreamDepth,
        scope: DreamScope,
    ) -> DreamSelection:
        messages = tuple(
            sorted(
                (
                    message
                    for message in snapshot.messages
                    if message.role in _ALLOWED_ROLES
                    and message.mode in _ALLOWED_MODES
                    and message.content.strip()
                ),
                key=lambda message: (
                    message.turn_id,
                    message.seq_in_turn,
                    message.message_id,
                ),
            )
        )
        message_by_id = {message.message_id: message for message in messages}
        next_messages = _message_manifest(messages)
        current_story = _derived_manifest(snapshot.story_memories)
        current_summaries = _derived_manifest(snapshot.summary_batches)

        if depth == DreamDepth.SHALLOW:
            segments, story_ids = self._select_shallow(
                snapshot,
                scope=scope,
                message_by_id=message_by_id,
            )
            retirement = DreamRetirementPolicy.CONTRADICTION_ONLY
            analyzed_story_ids = {
                segment.source_id
                for segment in segments
                if segment.source_kind == DreamSourceKind.STORY_MEMORY
            }
            analyzed_summary_ids = {
                segment.source_id
                for segment in segments
                if segment.source_kind == DreamSourceKind.SUMMARY_BATCH
            }
            # Shallow and Deep checkpoints are intentionally independent.  A
            # Shallow run must not establish a Deep history baseline.
            next_messages = dict(snapshot.message_manifest)
            next_story = _advance_derived_manifest(
                snapshot.story_memory_manifest,
                current_story,
                analyzed_story_ids,
            )
            next_summaries = _advance_derived_manifest(
                snapshot.summary_batch_manifest,
                current_summaries,
                analyzed_summary_ids,
            )
        else:
            segments = self._select_deep(
                snapshot,
                scope=scope,
                messages=messages,
                next_manifest=next_messages,
            )
            story_ids = ()
            if scope == DreamScope.FULL:
                retirement = DreamRetirementPolicy.FULL_RECONCILIATION
            else:
                retirement = DreamRetirementPolicy.INVALIDATED_EVIDENCE
            # Deep consumes current main history only.  It must not mark
            # summary/story-memory inputs as analyzed by a future Shallow run.
            next_story = dict(snapshot.story_memory_manifest)
            next_summaries = dict(snapshot.summary_batch_manifest)

        batches = self._build_batches(
            segments,
            player_character_name=snapshot.player_character_name,
        )
        return DreamSelection(
            snapshot=snapshot,
            depth=depth,
            scope=scope,
            batches=batches,
            retirement_policy=retirement,
            next_message_manifest=next_messages,
            next_story_memory_manifest=next_story,
            next_summary_batch_manifest=next_summaries,
            source_story_memory_ids=story_ids,
        )

    def _select_shallow(
        self,
        snapshot: DreamSourceSnapshot,
        *,
        scope: DreamScope,
        message_by_id: Mapping[int, DreamMessageSource],
    ) -> tuple[tuple[DreamSourceSegment, ...], tuple[int, ...]]:
        selected: list[DreamDerivedSource] = []
        for source in (*snapshot.story_memories, *snapshot.summary_batches):
            manifest = (
                snapshot.story_memory_manifest
                if source.kind == DreamSourceKind.STORY_MEMORY
                else snapshot.summary_batch_manifest
            )
            previous = manifest.get(source.source_id)
            if scope == DreamScope.FULL or previous is None or previous.fingerprint != source.fingerprint:
                selected.append(source)

        segments: list[DreamSourceSegment] = []
        story_ids: list[int] = []
        for source in selected:
            evidence = tuple(
                message_by_id[message_id].evidence
                for message_id in source.evidence_message_ids
                if message_id in message_by_id
            )
            if not evidence:
                continue
            segments.append(
                DreamSourceSegment(
                    source_kind=source.kind,
                    source_id=source.source_id,
                    text=source.content,
                    turn_start=source.source_turn_start,
                    turn_end=source.source_turn_end,
                    evidence=evidence,
                )
            )
            if source.kind == DreamSourceKind.STORY_MEMORY:
                try:
                    story_ids.append(int(source.source_id))
                except ValueError as exc:
                    raise DreamSourceError(
                        f"story-memory source id must be numeric: {source.source_id}"
                    ) from exc
        return tuple(segments), tuple(sorted(set(story_ids)))

    def _select_deep(
        self,
        snapshot: DreamSourceSnapshot,
        *,
        scope: DreamScope,
        messages: tuple[DreamMessageSource, ...],
        next_manifest: Mapping[str, DreamManifestEntry],
    ) -> tuple[DreamSourceSegment, ...]:
        if scope == DreamScope.FULL or not snapshot.message_manifest:
            chosen_turns = {message.turn_id for message in messages}
        else:
            changed_turns = {
                message.turn_id
                for message in messages
                if (
                    (previous := snapshot.message_manifest.get(message.source_id)) is None
                    or previous.fingerprint != message.fingerprint
                )
            }
            ordered_turns = sorted({message.turn_id for message in messages})
            turn_positions = {turn: index for index, turn in enumerate(ordered_turns)}
            chosen_turns = set(changed_turns)
            for turn in tuple(changed_turns):
                position = turn_positions[turn]
                if position > 0:
                    chosen_turns.add(ordered_turns[position - 1])
                if position + 1 < len(ordered_turns):
                    chosen_turns.add(ordered_turns[position + 1])

            deleted_ids = set(snapshot.message_manifest) - set(next_manifest)
            for source_id in deleted_ids:
                previous = snapshot.message_manifest[source_id]
                left = bisect_left(ordered_turns, previous.turn_start)
                right = bisect_right(ordered_turns, previous.turn_end)
                chosen_turns.update(ordered_turns[left:right])
                if left > 0:
                    chosen_turns.add(ordered_turns[left - 1])
                if right < len(ordered_turns):
                    chosen_turns.add(ordered_turns[right])

        selected = [message for message in messages if message.turn_id in chosen_turns]
        segments = [
            DreamSourceSegment(
                source_kind=DreamSourceKind.MESSAGE,
                source_id=message.source_id,
                text=f"role={message.role} mode={message.mode}\n{message.content}",
                turn_start=message.turn_id,
                turn_end=message.turn_id,
                evidence=(message.evidence,),
            )
            for message in selected
        ]

        if scope == DreamScope.INCREMENTAL and snapshot.message_manifest:
            for source_id in sorted(set(snapshot.message_manifest) - set(next_manifest)):
                previous = snapshot.message_manifest[source_id]
                segments.append(
                    DreamSourceSegment(
                        source_kind=DreamSourceKind.MESSAGE_TOMBSTONE,
                        source_id=source_id,
                        text="This previously analyzed message was deleted from current history.",
                        turn_start=previous.turn_start,
                        turn_end=previous.turn_end,
                        evidence=(),
                        deleted=True,
                    )
                )
        message_order = {
            message.source_id: (message.seq_in_turn, message.message_id)
            for message in selected
        }
        segments.sort(
            key=lambda item: (
                item.turn_start,
                item.turn_end,
                0 if item.source_kind == DreamSourceKind.MESSAGE else 1,
                *message_order.get(item.source_id, (0, 0)),
                item.source_id,
            )
        )
        return tuple(segments)

    def _build_batches(
        self,
        segments: Sequence[DreamSourceSegment],
        *,
        player_character_name: str,
    ) -> tuple[DreamSourceBatch, ...]:
        expanded: list[DreamSourceSegment] = []
        for segment in segments:
            expanded.extend(self._split_oversize_segment(segment))

        units = self._turn_safe_units(expanded)

        groups: list[list[DreamSourceSegment]] = []
        current: list[DreamSourceSegment] = []
        current_turns: set[int] = set()
        current_chars = 0
        for unit in units:
            unit_turns = {
                turn_id
                for segment in unit
                for turn_id in range(segment.turn_start, segment.turn_end + 1)
            }
            unit_chars = sum(len(segment.text) for segment in unit)
            exceeds = bool(current) and (
                len(current_turns | unit_turns) > self.max_map_turns
                or current_chars + unit_chars > self.max_map_chars
            )
            if exceeds:
                groups.append(current)
                current = []
                current_turns = set()
                current_chars = 0
            current.extend(unit)
            current_turns.update(unit_turns)
            current_chars += unit_chars
        if current:
            groups.append(current)
        return tuple(
            DreamSourceBatch(
                index=index,
                segments=tuple(group),
                player_character_name=player_character_name,
            )
            for index, group in enumerate(groups)
        )

    def _turn_safe_units(
        self,
        segments: Sequence[DreamSourceSegment],
    ) -> list[list[DreamSourceSegment]]:
        """Keep persisted user/assistant components of one normal turn together."""

        units: list[list[DreamSourceSegment]] = []
        index = 0
        while index < len(segments):
            segment = segments[index]
            if segment.source_kind != DreamSourceKind.MESSAGE:
                units.append([segment])
                index += 1
                continue
            turn_id = segment.turn_start
            turn_segments: list[DreamSourceSegment] = []
            while index < len(segments):
                candidate = segments[index]
                if (
                    candidate.source_kind != DreamSourceKind.MESSAGE
                    or candidate.turn_start != turn_id
                    or candidate.turn_end != turn_id
                ):
                    break
                turn_segments.append(candidate)
                index += 1
            units.extend(self._split_oversize_turn(turn_segments))
        return units

    def _split_oversize_turn(
        self,
        segments: Sequence[DreamSourceSegment],
    ) -> list[list[DreamSourceSegment]]:
        if sum(len(segment.text) for segment in segments) <= self.max_map_chars:
            return [list(segments)]
        # A complete persisted turn is the normal batching atom.  Splitting is
        # an explicit fallback only when that atom cannot fit by itself.
        parts: list[list[DreamSourceSegment]] = []
        current: list[DreamSourceSegment] = []
        current_chars = 0
        for segment in segments:
            if current and current_chars + len(segment.text) > self.max_map_chars:
                parts.append(current)
                current = []
                current_chars = 0
            current.append(segment)
            current_chars += len(segment.text)
        if current:
            parts.append(current)
        if len(parts) <= 1:
            return parts
        return [
            [
                DreamSourceSegment(
                    source_kind=segment.source_kind,
                    source_id=f"{segment.source_id}#turn-part-{part_index + 1}",
                    text=segment.text,
                    turn_start=segment.turn_start,
                    turn_end=segment.turn_end,
                    evidence=segment.evidence,
                    deleted=segment.deleted,
                )
                for segment in part
            ]
            for part_index, part in enumerate(parts)
        ]

    def _split_oversize_segment(
        self,
        segment: DreamSourceSegment,
    ) -> list[DreamSourceSegment]:
        if len(segment.text) <= self.max_map_chars:
            return [segment]
        chunks = _safe_text_chunks(segment.text, self.max_map_chars)
        return [
            DreamSourceSegment(
                source_kind=segment.source_kind,
                source_id=f"{segment.source_id}#part-{index + 1}",
                text=chunk,
                turn_start=segment.turn_start,
                turn_end=segment.turn_end,
                evidence=segment.evidence,
                deleted=segment.deleted,
            )
            for index, chunk in enumerate(chunks)
        ]


def combine_source_fingerprint(
    base_fingerprint: str,
    summaries: Iterable[DreamDerivedSource],
    *,
    player_character_fingerprint: str = "",
) -> str:
    """Fold file-backed summary versions into the data-owned source fingerprint."""

    payload = {
        "base": base_fingerprint,
        "player_character": player_character_fingerprint,
        "summaries": [
            (source.source_id, source.version, source.content_hash)
            for source in sorted(summaries, key=lambda item: item.source_id)
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _message_manifest(
    messages: Iterable[DreamMessageSource],
) -> Mapping[str, DreamManifestEntry]:
    return {
        message.source_id: DreamManifestEntry(
            source_id=message.source_id,
            fingerprint=message.fingerprint,
            turn_start=message.turn_id,
            turn_end=message.turn_id,
        )
        for message in messages
    }


def _derived_manifest(
    sources: Iterable[DreamDerivedSource],
) -> Mapping[str, DreamManifestEntry]:
    return {
        source.source_id: DreamManifestEntry(
            source_id=source.source_id,
            fingerprint=source.fingerprint,
            turn_start=source.source_turn_start,
            turn_end=source.source_turn_end,
        )
        for source in sources
    }


def _advance_derived_manifest(
    previous: Mapping[str, DreamManifestEntry],
    current: Mapping[str, DreamManifestEntry],
    analyzed_source_ids: set[str],
) -> Mapping[str, DreamManifestEntry]:
    # Remove sources which no longer exist, retain the previous fingerprint for
    # a present but currently unsourced item, and advance only inputs that were
    # actually placed in a Map batch.
    advanced = {
        source_id: entry
        for source_id, entry in previous.items()
        if source_id in current
    }
    for source_id in analyzed_source_ids:
        entry = current.get(source_id)
        if entry is not None:
            advanced[source_id] = entry
    return advanced


def _safe_text_chunks(text: str, limit: int) -> list[str]:
    paragraphs = [part for part in re.split(r"(?<=\n)\n+", text) if part]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [text]:
        if len(paragraph) > limit:
            if current:
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(paragraph), limit):
                chunks.append(paragraph[start : start + limit].strip())
            continue
        if current and len(current) + len(paragraph) > limit:
            chunks.append(current.strip())
            current = paragraph
        else:
            current += paragraph
    if current.strip():
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]
