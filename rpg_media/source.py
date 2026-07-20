"""Immutable source snapshots and compact turn previews."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Protocol

from rpg_data import models
from rpg_media.errors import MediaSourceRangeError
from rpg_media.types import (
    MediaBackgroundSourceSnapshot,
    MediaSourceSnapshot,
    MediaSourceTurnView,
)

_WHITESPACE_RE = re.compile(r"\s+")
MAX_MEDIA_SOURCE_TURNS = 20


class MediaSourceDataPort(Protocol):
    def get_source_turns(
        self,
        session_id: str,
        *,
        start_turn_id: int,
        end_turn_id: int,
    ) -> list[models.MediaSourceTurn]: ...

    def get_latest_source_turns(
        self,
        session_id: str,
        *,
        through_turn_id: int,
        limit: int = 3,
    ) -> list[models.MediaSourceTurn]: ...


def build_source_snapshot(
    media_data: MediaSourceDataPort,
    session_id: str,
    *,
    start_turn_id: int,
    end_turn_id: int,
) -> MediaSourceSnapshot:
    start = int(start_turn_id)
    end = int(end_turn_id)
    if start <= 0 or end < start:
        raise MediaSourceRangeError("media source turn range is invalid")
    if end - start + 1 > MAX_MEDIA_SOURCE_TURNS:
        raise MediaSourceRangeError(
            f"media source may contain at most {MAX_MEDIA_SOURCE_TURNS} turns"
        )
    turns = tuple(
        media_data.get_source_turns(
            session_id,
            start_turn_id=start,
            end_turn_id=end,
        )
    )
    if [turn.turn_id for turn in turns] != list(range(start, end + 1)):
        raise MediaSourceRangeError(
            "media source must be a contiguous range of committed turns"
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


def build_background_source_snapshot(
    media_data: MediaSourceDataPort,
    session: models.Session,
    *,
    target_turn_id: int,
    scene_attrs: dict[str, str] | None,
    current_asset: models.MediaDisplayAssetBundle | None,
    state: models.SessionMediaBackgroundState,
) -> MediaBackgroundSourceSnapshot:
    turns = tuple(
        media_data.get_latest_source_turns(
            session.id,
            through_turn_id=int(target_turn_id),
            limit=3,
        )
    )
    if not turns or turns[-1].turn_id != int(target_turn_id):
        raise ValueError(f"committed media source turn not found: {target_turn_id}")
    normalized_scene = {
        str(key): str(value)
        for key, value in sorted((scene_attrs or {}).items())
    }
    current_title = (
        current_asset.library_item.title
        if current_asset is not None and current_asset.library_item is not None
        else ""
    )
    payload = {
        "sessionId": session.id,
        "workspaceId": session.workspace_id,
        "storyId": session.story_id,
        "targetTurnId": int(target_turn_id),
        "scene": normalized_scene,
        "messages": [
            {
                "id": message.id,
                "version": message.version,
                "role": message.role,
                "content": message.content,
                "turnId": message.turn_id,
                "seqInTurn": message.seq_in_turn,
            }
            for turn in turns
            for message in turn.messages
        ],
        "currentBackground": {
            "assetId": current_asset.asset.id if current_asset is not None else None,
            "title": current_title,
        },
        "lastDecision": state.last_decision,
        "lastReason": state.last_reason,
    }
    snapshot_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    return MediaBackgroundSourceSnapshot(
        session_id=session.id,
        workspace_id=session.workspace_id,
        story_id=session.story_id,
        target_turn_id=int(target_turn_id),
        scene_attrs=normalized_scene,
        turns=turns,
        current_asset_id=current_asset.asset.id if current_asset is not None else None,
        current_title=current_title,
        last_decision=state.last_decision,
        last_reason=state.last_reason,
        fingerprint=fingerprint,
        snapshot_json=snapshot_json,
    )


def parse_background_source_snapshot(raw: str) -> MediaBackgroundSourceSnapshot:
    payload = json.loads(str(raw))
    if not isinstance(payload, dict):
        raise ValueError("media background source snapshot must be an object")
    grouped: dict[int, list[models.MediaSourceMessage]] = {}
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        raise ValueError("media background source messages must be an array")
    for item in messages:
        if not isinstance(item, dict):
            raise ValueError("media background source message must be an object")
        message = models.MediaSourceMessage(
            id=int(item.get("id", 0)),
            version=int(item.get("version", 0)),
            role=str(item.get("role", "")),
            content=str(item.get("content", "")),
            turn_id=int(item.get("turnId", 0)),
            seq_in_turn=int(item.get("seqInTurn", 0)),
        )
        grouped.setdefault(message.turn_id, []).append(message)
    turns = tuple(
        models.MediaSourceTurn(turn_id=turn_id, messages=tuple(grouped[turn_id]))
        for turn_id in sorted(grouped)
    )
    scene = payload.get("scene", {})
    if not isinstance(scene, dict):
        raise ValueError("media background scene must be an object")
    current = payload.get("currentBackground", {})
    if not isinstance(current, dict):
        current = {}
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return MediaBackgroundSourceSnapshot(
        session_id=str(payload.get("sessionId", "")),
        workspace_id=str(payload.get("workspaceId", "")),
        story_id=int(payload.get("storyId", 0)),
        target_turn_id=int(payload.get("targetTurnId", 0)),
        scene_attrs={str(key): str(value) for key, value in scene.items()},
        turns=turns,
        current_asset_id=(
            str(current.get("assetId"))
            if current.get("assetId") is not None
            else None
        ),
        current_title=str(current.get("title", "")),
        last_decision=str(payload.get("lastDecision", "")),
        last_reason=str(payload.get("lastReason", "")),
        fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        snapshot_json=canonical,
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
