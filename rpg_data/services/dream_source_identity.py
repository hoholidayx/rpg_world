"""Pure source-identity helpers shared by Dream snapshot and apply guards."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

from commons.dream_identity import dream_derived_source_fingerprint
from rpg_data import models

__all__ = ["StoryMemorySourceIdentity", "story_memory_source_identity"]

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_EVIDENCE_ROLES = frozenset(
    {models.MESSAGE_ROLE_USER, models.MESSAGE_ROLE_ASSISTANT}
)
_EVIDENCE_MODES = frozenset({models.TURN_MODE_IC, models.TURN_MODE_GM})


@dataclass(frozen=True)
class StoryMemorySourceIdentity:
    """Current valid Evidence IDs and the fingerprint derived from them."""

    evidence_message_ids: tuple[int, ...]
    fingerprint: str


def story_memory_source_identity(
    memory: models.SessionStoryMemory,
    messages_by_id: Mapping[int, models.SessionMessage],
) -> StoryMemorySourceIdentity:
    """Resolve a Story Memory identity against current authoritative messages."""

    evidence_message_ids = _valid_story_memory_evidence_ids(
        memory,
        messages_by_id,
    )
    return StoryMemorySourceIdentity(
        evidence_message_ids=evidence_message_ids,
        fingerprint=dream_derived_source_fingerprint(
            version=memory.version,
            content_hash=hashlib.sha256(memory.text.encode("utf-8")).hexdigest(),
            source_turn_start=memory.source_turn_start,
            source_turn_end=memory.source_turn_end,
            evidence_message_ids=evidence_message_ids,
        ),
    )


def _valid_story_memory_evidence_ids(
    memory: models.SessionStoryMemory,
    messages_by_id: Mapping[int, models.SessionMessage],
) -> tuple[int, ...]:
    if not memory.evidence:
        return ()

    result: list[int] = []
    seen_message_ids: set[int] = set()
    for item in memory.evidence:
        message_id = item.message_id
        turn_id = item.turn_id
        version = item.message_version
        content_hash = str(item.content_hash or "").strip().lower()
        if (
            message_id <= 0
            or turn_id <= 0
            or version <= 0
            or _SHA256_RE.fullmatch(content_hash) is None
            or message_id in seen_message_ids
        ):
            return ()
        seen_message_ids.add(message_id)
        current = messages_by_id.get(message_id)
        if (
            current is None
            or current.role not in _EVIDENCE_ROLES
            or current.mode not in _EVIDENCE_MODES
            or current.turn_id != turn_id
            or current.version != version
            or hashlib.sha256(current.content.encode("utf-8")).hexdigest()
            != content_hash
            or not memory.source_turn_start <= turn_id <= memory.source_turn_end
        ):
            continue
        result.append(message_id)

    return tuple(
        sorted(
            result,
            key=lambda message_id: (
                messages_by_id[message_id].turn_id,
                messages_by_id[message_id].seq_in_turn,
                message_id,
            ),
        )
    )
