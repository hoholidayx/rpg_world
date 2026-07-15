"""Immutable source snapshots and compact turn previews."""

from __future__ import annotations

import hashlib
import json
import re

from rpg_data import models
from rpg_data.services.media import MediaDataService
from rpg_media.types import MediaSourceSnapshot, MediaSourceTurnView

_WHITESPACE_RE = re.compile(r"\s+")


def build_source_snapshot(
    media_data: MediaDataService,
    session_id: str,
    *,
    start_turn_id: int,
    end_turn_id: int,
) -> MediaSourceSnapshot:
    turns = tuple(
        media_data.get_source_turns(
            session_id,
            start_turn_id=start_turn_id,
            end_turn_id=end_turn_id,
        )
    )
    messages = tuple(message for turn in turns for message in turn.messages)
    fingerprint_payload = [
        {
            "id": message.id,
            "version": message.version,
            "role": message.role,
            "content": message.content,
        }
        for message in messages
    ]
    canonical = json.dumps(
        fingerprint_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    snapshot_payload = {
        "sessionId": str(session_id),
        "startTurnId": int(start_turn_id),
        "endTurnId": int(end_turn_id),
        "messages": [
            {
                "id": message.id,
                "version": message.version,
                "role": message.role,
                "content": message.content,
                "turnId": message.turn_id,
                "seqInTurn": message.seq_in_turn,
            }
            for message in messages
        ],
    }
    return MediaSourceSnapshot(
        session_id=str(session_id),
        start_turn_id=int(start_turn_id),
        end_turn_id=int(end_turn_id),
        turns=turns,
        fingerprint=fingerprint,
        snapshot_json=json.dumps(
            snapshot_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def source_turn_views(turns: list[models.MediaSourceTurn]) -> list[MediaSourceTurnView]:
    views: list[MediaSourceTurnView] = []
    for turn in turns:
        combined = " ".join(message.content for message in turn.messages)
        views.append(
            MediaSourceTurnView(
                turn_id=turn.turn_id,
                roles=tuple(message.role for message in turn.messages),
                preview=visible_excerpt(combined),
                message_count=len(turn.messages),
            )
        )
    return views


def visible_excerpt(text: str, segment_length: int = 16) -> str:
    normalized = _WHITESPACE_RE.sub(" ", str(text)).strip()
    if len(normalized) <= segment_length * 3:
        return normalized
    middle_start = max(0, (len(normalized) - segment_length) // 2)
    return "…".join((
        normalized[:segment_length],
        normalized[middle_start:middle_start + segment_length],
        normalized[-segment_length:],
    ))
