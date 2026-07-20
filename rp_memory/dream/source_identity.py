"""Pure Dream source and Evidence identity policy."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from commons.dream_identity import dream_derived_source_fingerprint
from rpg_data.model import memory as models
from rpg_data.model.session import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    TURN_MODE_GM,
    TURN_MODE_IC,
    SessionMessage,
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_EVIDENCE_ROLES = frozenset(
    {MESSAGE_ROLE_USER, MESSAGE_ROLE_ASSISTANT}
)
_EVIDENCE_MODES = frozenset({TURN_MODE_IC, TURN_MODE_GM})


@dataclass(frozen=True)
class StoryMemorySourceIdentity:
    evidence_message_ids: tuple[int, ...]
    fingerprint: str


def story_memory_source_identity(
    memory: models.SessionStoryMemory,
    messages_by_id: Mapping[int, SessionMessage],
) -> StoryMemorySourceIdentity:
    evidence_message_ids = valid_story_memory_evidence_ids(memory, messages_by_id)
    return StoryMemorySourceIdentity(
        evidence_message_ids=evidence_message_ids,
        fingerprint=dream_derived_source_fingerprint(
            version=memory.version,
            content_hash=content_hash(memory.text),
            source_turn_start=memory.source_turn_start,
            source_turn_end=memory.source_turn_end,
            evidence_message_ids=evidence_message_ids,
        ),
    )


def valid_story_memory_evidence_ids(
    memory: models.SessionStoryMemory,
    messages_by_id: Mapping[int, SessionMessage],
) -> tuple[int, ...]:
    if not memory.evidence:
        return ()
    result: list[int] = []
    seen_message_ids: set[int] = set()
    for item in memory.evidence:
        content_digest = str(item.content_hash or "").strip().lower()
        if (
            item.message_id <= 0
            or item.turn_id <= 0
            or item.message_version <= 0
            or _SHA256_RE.fullmatch(content_digest) is None
            or item.message_id in seen_message_ids
        ):
            return ()
        seen_message_ids.add(item.message_id)
        current = messages_by_id.get(item.message_id)
        if (
            current is None
            or not evidence_matches(
                current,
                message_id=item.message_id,
                turn_id=item.turn_id,
                message_version=item.message_version,
                expected_content_hash=content_digest,
            )
            or not memory.source_turn_start <= item.turn_id <= memory.source_turn_end
        ):
            continue
        result.append(item.message_id)
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


def evidence_matches(
    message: SessionMessage | None,
    *,
    message_id: int,
    turn_id: int,
    message_version: int,
    expected_content_hash: str,
) -> bool:
    return bool(
        message is not None
        and message.id == message_id
        and message.role in _EVIDENCE_ROLES
        and message.mode in _EVIDENCE_MODES
        and message.turn_id == turn_id
        and message.version == message_version
        and content_hash(message.content) == expected_content_hash
    )


def history_fingerprint(messages: Sequence[SessionMessage]) -> str:
    return json_fingerprint(
        [
            {
                "id": item.id,
                "version": item.version,
                "role": item.role,
                "mode": item.mode,
                "turn_id": item.turn_id,
                "seq_in_turn": item.seq_in_turn,
                "content_hash": content_hash(item.content),
            }
            for item in messages
        ]
    )


def story_memory_fingerprint(
    memories: Sequence[models.SessionStoryMemory],
) -> str:
    return json_fingerprint(
        [
            {
                "id": memory.id,
                "version": memory.version,
                "dedupe_key": memory.dedupe_key,
                "turn_id": memory.turn_id,
                "source_turn_start": memory.source_turn_start,
                "source_turn_end": memory.source_turn_end,
                "text_hash": content_hash(memory.text),
                "evidence": [
                    {
                        "message_id": item.message_id,
                        "turn_id": item.turn_id,
                        "message_version": item.message_version,
                        "content_hash": item.content_hash,
                    }
                    for item in memory.evidence
                ],
            }
            for memory in memories
        ]
    )


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
