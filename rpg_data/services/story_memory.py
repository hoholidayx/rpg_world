"""Session story memory service backed by rpg_data."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from peewee import Database, SQL

from commons.errors import InvalidTurnMetadataError
from rpg_data import models
from rpg_data.repositories._utils import get_or_none, to_session_story_memory
from rpg_data.repositories.records import (
    SessionMessageRecord,
    SessionRecord,
    SessionStoryMemoryRecord,
    bind_database,
)

__all__ = ["StoryMemoryService"]


class StoryMemoryService:
    """Manage persisted story-memory details for sessions."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def list(
        self,
        session_id: str,
        *,
        dream_processed: bool | None = None,
    ) -> list[models.SessionStoryMemory]:
        where_clause = SessionStoryMemoryRecord.session == session_id
        if dream_processed is not None:
            where_clause &= SessionStoryMemoryRecord.dream_processed == bool(dream_processed)
        query = (
            SessionStoryMemoryRecord
            .select()
            .where(where_clause)
            .order_by(SessionStoryMemoryRecord.id)
        )
        return [to_session_story_memory(row) for row in query]

    def get(self, memory_id: int) -> models.SessionStoryMemory | None:
        row = get_or_none(SessionStoryMemoryRecord, memory_id)
        return to_session_story_memory(row) if row is not None else None

    def add_detail(
        self,
        session_id: str,
        text: str,
        *,
        turn_id: int,
        dream_processed: bool = False,
        memory_kind: str = "event",
        epistemic_status: str = "confirmed",
        salience: float = 0.5,
        source_turn_start: int | None = None,
        source_turn_end: int | None = None,
        dedupe_key: str = "",
        metadata_schema_version: int = 1,
        metadata_json: str = "{}",
        source_messages_manifest_json: str = "[]",
    ) -> models.SessionStoryMemory:
        payload = _normalize_detail(
            text=text,
            turn_id=turn_id,
            dream_processed=dream_processed,
            memory_kind=memory_kind,
            epistemic_status=epistemic_status,
            salience=salience,
            source_turn_start=source_turn_start,
            source_turn_end=source_turn_end,
            dedupe_key=dedupe_key,
            metadata_schema_version=metadata_schema_version,
            metadata_json=metadata_json,
            source_messages_manifest_json=source_messages_manifest_json,
        )
        with self._database.atomic():
            return self._upsert_detail(session_id, payload)

    def add_details_and_mark_processed(
        self,
        session_id: str,
        details: Iterable[models.SessionStoryMemory | dict[str, object]],
        *,
        message_ids: Iterable[int],
    ) -> list[models.SessionStoryMemory]:
        """Upsert extracted details and advance their source messages atomically."""
        payloads = [_coerce_detail(detail) for detail in details]
        ids = sorted({_required_positive_int(value, "message_id") for value in message_ids})
        with self._database.atomic():
            source_rows: list[SessionMessageRecord] = []
            if ids:
                source_rows = list(
                    SessionMessageRecord.select()
                    .where(
                        (SessionMessageRecord.session == session_id)
                        & (SessionMessageRecord.id.in_(ids))
                    )
                    .order_by(SessionMessageRecord.id)
                )
                if len(source_rows) != len(ids):
                    raise ValueError("story-memory source messages must belong to the session")
                source_manifest = _source_messages_manifest_json(source_rows)
                source_turn_start = min(int(row.turn_id) for row in source_rows)
                source_turn_end = max(int(row.turn_id) for row in source_rows)
                for payload in payloads:
                    if (
                        int(payload["source_turn_start"]) > source_turn_start
                        or int(payload["source_turn_end"]) < source_turn_end
                    ):
                        raise ValueError(
                            "story-memory source turn range must cover every source message"
                        )
                    payload["source_messages_manifest_json"] = source_manifest
            rows = [self._upsert_detail(session_id, payload) for payload in payloads]
            if ids:
                SessionMessageRecord.update(
                    story_memory_processed=True,
                    story_memory_processed_at=SQL("CURRENT_TIMESTAMP"),
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                ).where(
                    (SessionMessageRecord.session == session_id)
                    & (SessionMessageRecord.id.in_(ids))
                ).execute()
            return rows

    def set_details(
        self,
        session_id: str,
        details: Iterable[models.SessionStoryMemory | dict[str, object]],
    ) -> list[models.SessionStoryMemory]:
        payloads = [_coerce_detail(detail) for detail in details]
        with self._database.atomic():
            self.clear(session_id)
            return [
                self._upsert_detail(session_id, payload)
                for payload in payloads
            ]

    def _upsert_detail(
        self,
        session_id: str,
        payload: dict[str, object],
    ) -> models.SessionStoryMemory:
        existing = (
            SessionStoryMemoryRecord.select()
            .where(
                (SessionStoryMemoryRecord.session == session_id)
                & (SessionStoryMemoryRecord.dedupe_key == payload["dedupe_key"])
            )
            .first()
        )
        if existing is None:
            row = SessionStoryMemoryRecord.create(session=session_id, **payload)
            return to_session_story_memory(SessionStoryMemoryRecord.get_by_id(row.id))
        semantic_before = _story_memory_semantic_signature(existing)
        existing.turn_id = max(int(existing.turn_id), int(payload["turn_id"]))
        existing.text = str(payload["text"])
        existing.memory_kind = str(payload["memory_kind"])
        existing.epistemic_status = str(payload["epistemic_status"])
        existing.salience = max(float(existing.salience), float(payload["salience"]))
        existing.source_turn_start = min(
            int(existing.source_turn_start), int(payload["source_turn_start"])
        )
        existing.source_turn_end = max(
            int(existing.source_turn_end), int(payload["source_turn_end"])
        )
        existing.dream_processed = bool(existing.dream_processed) or bool(payload["dream_processed"])
        existing.metadata_schema_version = max(
            int(existing.metadata_schema_version),
            int(payload["metadata_schema_version"]),
        )
        existing.metadata_json = _merge_metadata_json(
            str(existing.metadata_json or "{}"),
            str(payload["metadata_json"]),
        )
        incoming_source_manifest = _normalize_source_messages_manifest_json(
            payload["source_messages_manifest_json"]
        )
        if incoming_source_manifest != "[]":
            # A repeated extraction of the same normalized fact is fresh
            # support, not an ever-growing union with potentially stale rows.
            existing.source_messages_manifest_json = incoming_source_manifest
        if _story_memory_semantic_signature(existing) != semantic_before:
            existing.version = int(existing.version) + 1
        existing.updated_at = SQL("CURRENT_TIMESTAMP")
        existing.save()
        return to_session_story_memory(SessionStoryMemoryRecord.get_by_id(existing.id))

    def clear(self, session_id: str) -> int:
        return int(
            SessionStoryMemoryRecord
            .delete()
            .where(SessionStoryMemoryRecord.session == session_id)
            .execute()
        )

    def set_dream_processed(
        self,
        memory_ids: Iterable[int],
        *,
        dream_processed: bool = True,
    ) -> int:
        ids = [int(memory_id) for memory_id in memory_ids]
        if not ids:
            return 0
        return int(
            SessionStoryMemoryRecord
            .update(
                dream_processed=bool(dream_processed),
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(SessionStoryMemoryRecord.id.in_(ids))
            .execute()
        )

    def require_session(self, session_id: str) -> None:
        if not SessionRecord.select().where(SessionRecord.id == session_id).exists():
            raise FileNotFoundError(f"Session not found: {session_id}")


def _story_memory_semantic_signature(
    row: SessionStoryMemoryRecord,
) -> tuple[object, ...]:
    """Fields that change the derived story-memory source, excluding checkpoints."""

    return (
        int(row.turn_id),
        str(row.text),
        str(row.memory_kind),
        str(row.epistemic_status),
        float(row.salience),
        int(row.source_turn_start),
        int(row.source_turn_end),
        int(row.metadata_schema_version),
        str(row.metadata_json or "{}"),
        str(row.source_messages_manifest_json or "[]"),
    )


def _coerce_detail(
    detail: models.SessionStoryMemory | dict[str, object],
) -> dict[str, object]:
    if isinstance(detail, models.SessionStoryMemory):
        return {
            "text": detail.text,
            "turn_id": detail.turn_id,
            "dream_processed": detail.dream_processed,
            "memory_kind": detail.memory_kind,
            "epistemic_status": detail.epistemic_status,
            "salience": detail.salience,
            "source_turn_start": detail.source_turn_start,
            "source_turn_end": detail.source_turn_end,
            "dedupe_key": detail.dedupe_key,
            "metadata_schema_version": detail.metadata_schema_version,
            "metadata_json": detail.metadata_json,
            "source_messages_manifest_json": detail.source_messages_manifest_json,
        }

    metadata_json = detail.get("metadata_json", "")
    if not metadata_json and "metadata" in detail:
        metadata_json = json.dumps(detail.get("metadata") or {}, ensure_ascii=False)
    return _normalize_detail(
        text=str(detail.get("text", "") or ""),
        turn_id=_required_positive_int(detail.get("turn_id"), "turn_id"),
        dream_processed=bool(detail.get("dream_processed", False)),
        memory_kind=str(detail.get("memory_kind", "event") or "event"),
        epistemic_status=str(detail.get("epistemic_status", "confirmed") or "confirmed"),
        salience=detail.get("salience", 0.5),
        source_turn_start=detail.get("source_turn_start"),
        source_turn_end=detail.get("source_turn_end"),
        dedupe_key=str(detail.get("dedupe_key", "") or ""),
        metadata_schema_version=detail.get("metadata_schema_version", 1),
        metadata_json=str(metadata_json or "{}"),
        source_messages_manifest_json=str(
            detail.get("source_messages_manifest_json", "[]") or "[]"
        ),
    )


def _normalize_detail(
    *,
    text: object,
    turn_id: object,
    dream_processed: object,
    memory_kind: object,
    epistemic_status: object,
    salience: object,
    source_turn_start: object | None,
    source_turn_end: object | None,
    dedupe_key: object,
    metadata_schema_version: object,
    metadata_json: object,
    source_messages_manifest_json: object,
) -> dict[str, object]:
    normalized_turn_id = _required_positive_int(turn_id, "turn_id")
    start = _required_positive_int(
        source_turn_start if source_turn_start not in (None, "", 0) else normalized_turn_id,
        "source_turn_start",
    )
    end = _required_positive_int(
        source_turn_end if source_turn_end not in (None, "", 0) else normalized_turn_id,
        "source_turn_end",
    )
    if end < start:
        raise ValueError("source_turn_end must be greater than or equal to source_turn_start")
    kind = str(memory_kind or "event").strip().lower()
    if kind not in models.STORY_MEMORY_KINDS:
        raise ValueError(f"unsupported story memory kind: {kind}")
    status = str(epistemic_status or "confirmed").strip().lower()
    if status not in models.STORY_MEMORY_EPISTEMIC_STATUSES:
        raise ValueError(f"unsupported story memory epistemic status: {status}")
    if isinstance(salience, bool):
        raise ValueError("salience must be within [0, 1]")
    try:
        normalized_salience = float(salience)
    except (TypeError, ValueError) as exc:
        raise ValueError("salience must be within [0, 1]") from exc
    if not 0.0 <= normalized_salience <= 1.0:
        raise ValueError("salience must be within [0, 1]")
    schema_version = _required_positive_int(metadata_schema_version, "metadata_schema_version")
    try:
        metadata = json.loads(str(metadata_json or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("story memory metadata_json must be a JSON object") from exc
    if not isinstance(metadata, dict):
        raise ValueError("story memory metadata_json must be a JSON object")
    source_manifest_json = _normalize_source_messages_manifest_json(
        source_messages_manifest_json
    )
    normalized_text = " ".join(str(text or "").split())
    if not normalized_text:
        raise ValueError("story memory text must not be empty")
    normalized_key = _normalize_dedupe_key(str(dedupe_key or ""), kind, normalized_text)
    return {
        "turn_id": normalized_turn_id,
        "text": normalized_text,
        "memory_kind": kind,
        "epistemic_status": status,
        "salience": normalized_salience,
        "source_turn_start": start,
        "source_turn_end": end,
        "dedupe_key": normalized_key,
        "dream_processed": bool(dream_processed),
        "metadata_schema_version": schema_version,
        "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        "source_messages_manifest_json": source_manifest_json,
    }


def _source_messages_manifest_json(
    rows: Iterable[SessionMessageRecord],
) -> str:
    return _normalize_source_messages_manifest_json(
        json.dumps(
            [
                {
                    "messageId": int(row.id),
                    "turnId": int(row.turn_id),
                    "messageVersion": int(row.version),
                    "contentHash": hashlib.sha256(
                        str(row.content or "").encode("utf-8")
                    ).hexdigest(),
                }
                for row in rows
            ],
            ensure_ascii=False,
        )
    )


def _normalize_source_messages_manifest_json(value: object) -> str:
    try:
        payload = json.loads(str(value or "[]"))
    except json.JSONDecodeError as exc:
        raise ValueError("story memory source manifest must be a JSON array") from exc
    if not isinstance(payload, list):
        raise ValueError("story memory source manifest must be a JSON array")
    normalized: dict[int, dict[str, object]] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("story memory source manifest entries must be objects")
        message_id = _required_positive_int(item.get("messageId"), "messageId")
        if message_id in normalized:
            raise ValueError("story memory source manifest message IDs must be unique")
        content_hash = str(item.get("contentHash", "") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise ValueError("story memory source contentHash must be SHA-256")
        normalized[message_id] = {
            "messageId": message_id,
            "turnId": _required_positive_int(item.get("turnId"), "turnId"),
            "messageVersion": _required_positive_int(
                item.get("messageVersion"),
                "messageVersion",
            ),
            "contentHash": content_hash,
        }
    return json.dumps(
        [normalized[message_id] for message_id in sorted(normalized)],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _normalize_dedupe_key(raw: str, memory_kind: str, text: str) -> str:
    normalized_raw = raw.strip().casefold()
    if re.fullmatch(r"[0-9a-f]{64}", normalized_raw):
        return normalized_raw
    canonical = re.sub(r"\s+", "", raw or text).casefold()
    return hashlib.sha256(f"{memory_kind}:{canonical}".encode("utf-8")).hexdigest()


def _merge_metadata_json(existing_json: str, incoming_json: str) -> str:
    existing = json.loads(existing_json or "{}")
    incoming = json.loads(incoming_json or "{}")
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        raise ValueError("story memory metadata_json must be a JSON object")
    return json.dumps({**existing, **incoming}, ensure_ascii=False, sort_keys=True)


def _required_positive_int(value: object | None, field_name: str) -> int:
    if value is None or value == "" or isinstance(value, bool):
        raise InvalidTurnMetadataError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidTurnMetadataError(f"{field_name} must be a positive integer") from exc
    if parsed <= 0:
        raise InvalidTurnMetadataError(f"{field_name} must be a positive integer")
    return parsed
