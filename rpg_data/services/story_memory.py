"""Session story memory service backed by rpg_data."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from peewee import Database, SQL, fn

from commons.errors import InvalidTurnMetadataError
from rpg_data import models
from rpg_data.repositories._utils import (
    get_or_none,
    to_memory_evidence,
    to_session_story_memory,
)
from rpg_data.repositories.records import (
    SessionMessageRecord,
    SessionRecord,
    SessionStoryMemoryEvidenceRecord,
    SessionStoryMemoryRecord,
    bind_database,
)

__all__ = ["StoryMemoryService"]

_EVIDENCE_ROLES = frozenset(
    {models.MESSAGE_ROLE_USER, models.MESSAGE_ROLE_ASSISTANT}
)
_EVIDENCE_MODES = frozenset({models.TURN_MODE_IC, models.TURN_MODE_GM})


@dataclass(frozen=True)
class _CoercedDetail:
    payload: dict[str, object]
    evidence_message_ids: tuple[int, ...] | None = None
    evidence: tuple[models.MemoryEvidence, ...] | None = None


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
        rows = list(
            SessionStoryMemoryRecord
            .select()
            .where(where_clause)
            .order_by(SessionStoryMemoryRecord.id)
        )
        return _to_story_memories(rows)

    def list_page(
        self,
        session_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        memory_kind: str | None = None,
        dream_processed: bool | None = None,
    ) -> models.SessionStoryMemoryPage:
        if page <= 0:
            raise ValueError("story-memory page must be positive")
        if page_size <= 0 or page_size > 100:
            raise ValueError("story-memory page_size must be between 1 and 100")
        normalized_kind = str(memory_kind or "").strip()
        if normalized_kind and normalized_kind not in models.STORY_MEMORY_KINDS:
            raise ValueError("unsupported story-memory memory_kind")

        session_clause = SessionStoryMemoryRecord.session == session_id
        filtered_clause = session_clause
        if normalized_kind:
            filtered_clause &= SessionStoryMemoryRecord.memory_kind == normalized_kind
        if dream_processed is not None:
            filtered_clause &= SessionStoryMemoryRecord.dream_processed == bool(dream_processed)

        filtered_query = SessionStoryMemoryRecord.select().where(filtered_clause)
        total = filtered_query.count()
        rows = list(
            filtered_query
            .order_by(
                SessionStoryMemoryRecord.updated_at.desc(),
                SessionStoryMemoryRecord.id.desc(),
            )
            .paginate(page, page_size)
        )
        total_facts = (
            SessionStoryMemoryRecord.select()
            .where(session_clause)
            .count()
        )
        dream_processed_facts = (
            SessionStoryMemoryRecord.select()
            .where(
                session_clause
                & SessionStoryMemoryRecord.dream_processed
            )
            .count()
        )
        latest_updated_at = (
            SessionStoryMemoryRecord
            .select(fn.MAX(SessionStoryMemoryRecord.updated_at))
            .where(session_clause)
            .scalar()
        )
        return models.SessionStoryMemoryPage(
            items=tuple(_to_story_memories(rows)),
            page=page,
            page_size=page_size,
            total=total,
            stats=models.SessionStoryMemoryStats(
                total_facts=total_facts,
                dream_processed_facts=dream_processed_facts,
                pending_dream_facts=total_facts - dream_processed_facts,
                latest_updated_at=str(latest_updated_at or ""),
            ),
        )

    def get(self, memory_id: int) -> models.SessionStoryMemory | None:
        row = get_or_none(SessionStoryMemoryRecord, memory_id)
        return _to_story_memory(row) if row is not None else None

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
        evidence_message_ids: Iterable[int] | None = None,
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
        )
        with self._database.atomic():
            evidence = None
            if evidence_message_ids is not None:
                ids = _normalize_evidence_message_ids(evidence_message_ids)
                evidence = tuple(
                    _message_evidence(row)
                    for row in _load_source_rows(session_id, ids)
                )
                if evidence:
                    _set_exact_source_range(payload, evidence)
            return self._upsert_detail(session_id, payload, evidence=evidence)

    def add_details_and_mark_processed(
        self,
        session_id: str,
        details: Iterable[models.SessionStoryMemory | dict[str, object]],
        *,
        message_ids: Iterable[int],
    ) -> list[models.SessionStoryMemory]:
        """Persist per-fact Evidence and source-message progress atomically."""
        coerced = [_coerce_detail(detail) for detail in details]
        ids = _normalize_evidence_message_ids(message_ids)
        with self._database.atomic():
            source_rows = _load_source_rows(session_id, ids)
            source_by_id = {int(row.id): row for row in source_rows}
            rows: list[models.SessionStoryMemory] = []
            for detail in coerced:
                evidence_ids = detail.evidence_message_ids
                if not evidence_ids:
                    raise ValueError(
                        "each extracted story memory must cite evidence_message_ids"
                    )
                if not set(evidence_ids).issubset(source_by_id):
                    raise ValueError(
                        "story-memory Evidence must belong to the current source batch"
                    )
                selected_ids = set(evidence_ids)
                evidence = tuple(
                    _message_evidence(row)
                    for row in source_rows
                    if int(row.id) in selected_ids
                )
                _set_exact_source_range(detail.payload, evidence)
                rows.append(
                    self._upsert_detail(
                        session_id,
                        detail.payload,
                        evidence=evidence,
                    )
                )
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
        coerced = [_coerce_detail(detail) for detail in details]
        with self._database.atomic():
            self.clear(session_id)
            rows: list[models.SessionStoryMemory] = []
            for detail in coerced:
                evidence = detail.evidence
                if evidence is None and detail.evidence_message_ids is not None:
                    evidence = tuple(
                        _message_evidence(row)
                        for row in _load_source_rows(
                            session_id,
                            detail.evidence_message_ids,
                        )
                    )
                rows.append(
                    self._upsert_detail(
                        session_id,
                        detail.payload,
                        evidence=evidence,
                    )
                )
            return rows

    def _upsert_detail(
        self,
        session_id: str,
        payload: dict[str, object],
        *,
        evidence: tuple[models.MemoryEvidence, ...] | None = None,
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
            if evidence is not None:
                _replace_evidence(int(row.id), evidence)
            return _to_story_memory(SessionStoryMemoryRecord.get_by_id(row.id))
        previous_evidence = _evidence_for_memory(int(existing.id))
        semantic_before = _story_memory_semantic_signature(
            existing,
            previous_evidence,
        )
        existing.turn_id = (
            int(payload["turn_id"])
            if evidence is not None
            else max(int(existing.turn_id), int(payload["turn_id"]))
        )
        existing.text = str(payload["text"])
        existing.memory_kind = str(payload["memory_kind"])
        existing.epistemic_status = str(payload["epistemic_status"])
        existing.salience = max(float(existing.salience), float(payload["salience"]))
        if evidence is not None:
            existing.source_turn_start = int(payload["source_turn_start"])
            existing.source_turn_end = int(payload["source_turn_end"])
        else:
            existing.source_turn_start = min(
                int(existing.source_turn_start), int(payload["source_turn_start"])
            )
            existing.source_turn_end = max(
                int(existing.source_turn_end), int(payload["source_turn_end"])
            )
        existing.dream_processed = bool(existing.dream_processed) or bool(
            payload["dream_processed"]
        )
        existing.metadata_schema_version = max(
            int(existing.metadata_schema_version),
            int(payload["metadata_schema_version"]),
        )
        existing.metadata_json = _merge_metadata_json(
            str(existing.metadata_json or "{}"),
            str(payload["metadata_json"]),
        )
        effective_evidence = previous_evidence if evidence is None else evidence
        if (
            _story_memory_semantic_signature(existing, effective_evidence)
            != semantic_before
        ):
            existing.version = int(existing.version) + 1
        existing.updated_at = SQL("CURRENT_TIMESTAMP")
        existing.save()
        if evidence is not None and _evidence_signature(evidence) != _evidence_signature(
            previous_evidence
        ):
            # Exact-dedupe refreshes the source set instead of accumulating an
            # unbounded union of old and potentially stale Evidence.
            _replace_evidence(int(existing.id), evidence)
        return _to_story_memory(SessionStoryMemoryRecord.get_by_id(existing.id))

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
    evidence: Iterable[models.MemoryEvidence],
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
        _evidence_signature(evidence),
    )


def _coerce_detail(
    detail: models.SessionStoryMemory | dict[str, object],
) -> _CoercedDetail:
    if isinstance(detail, models.SessionStoryMemory):
        return _CoercedDetail(
            payload=_normalize_detail(
                text=detail.text,
                turn_id=detail.turn_id,
                dream_processed=detail.dream_processed,
                memory_kind=detail.memory_kind,
                epistemic_status=detail.epistemic_status,
                salience=detail.salience,
                source_turn_start=detail.source_turn_start,
                source_turn_end=detail.source_turn_end,
                dedupe_key=detail.dedupe_key,
                metadata_schema_version=detail.metadata_schema_version,
                metadata_json=detail.metadata_json,
            ),
            evidence=tuple(detail.evidence),
            evidence_message_ids=tuple(item.message_id for item in detail.evidence),
        )

    metadata_json = detail.get("metadata_json", "")
    if not metadata_json and "metadata" in detail:
        metadata_json = json.dumps(detail.get("metadata") or {}, ensure_ascii=False)
    evidence_message_ids = (
        _normalize_evidence_message_ids(detail.get("evidence_message_ids"))
        if "evidence_message_ids" in detail
        else None
    )
    return _CoercedDetail(
        payload=_normalize_detail(
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
        ),
        evidence_message_ids=evidence_message_ids,
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
    }


def _normalize_evidence_message_ids(values: object) -> tuple[int, ...]:
    if values is None or isinstance(values, (str, bytes)):
        raise ValueError("evidence_message_ids must be an array of positive integers")
    try:
        raw_values = list(values)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(
            "evidence_message_ids must be an array of positive integers"
        ) from exc
    normalized = tuple(
        _required_positive_int(value, "evidence_message_id")
        for value in raw_values
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError("evidence_message_ids must be unique")
    return normalized


def _load_source_rows(
    session_id: str,
    message_ids: Iterable[int],
) -> list[SessionMessageRecord]:
    ids = tuple(message_ids)
    if not ids:
        return []
    rows = list(
        SessionMessageRecord.select()
        .where(
            (SessionMessageRecord.session == session_id)
            & (SessionMessageRecord.id.in_(ids))
        )
        .order_by(
            SessionMessageRecord.turn_id,
            SessionMessageRecord.seq_in_turn,
            SessionMessageRecord.id,
        )
    )
    if len(rows) != len(ids):
        raise ValueError("story-memory source messages must belong to the session")
    if any(
        str(row.role) not in _EVIDENCE_ROLES
        or str(row.mode) not in _EVIDENCE_MODES
        for row in rows
    ):
        raise ValueError("story-memory Evidence must reference IC/GM user or assistant messages")
    return rows


def _message_evidence(row: SessionMessageRecord) -> models.MemoryEvidence:
    return models.MemoryEvidence(
        message_id=int(row.id),
        turn_id=int(row.turn_id),
        message_version=int(row.version),
        content_hash=hashlib.sha256(
            str(row.content or "").encode("utf-8")
        ).hexdigest(),
    )


def _set_exact_source_range(
    payload: dict[str, object],
    evidence: Iterable[models.MemoryEvidence],
) -> None:
    items = tuple(evidence)
    if not items:
        return
    turns = tuple(item.turn_id for item in items)
    payload["turn_id"] = max(turns)
    payload["source_turn_start"] = min(turns)
    payload["source_turn_end"] = max(turns)


def _evidence_signature(
    evidence: Iterable[models.MemoryEvidence],
) -> tuple[tuple[int, int, int, str], ...]:
    normalized: dict[int, tuple[int, int, int, str]] = {}
    for item in evidence:
        message_id = _required_positive_int(item.message_id, "message_id")
        if message_id in normalized:
            raise ValueError("story-memory Evidence message IDs must be unique")
        content_hash = str(item.content_hash or "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", content_hash) is None:
            raise ValueError("story-memory Evidence content_hash must be SHA-256")
        normalized[message_id] = (
            message_id,
            _required_positive_int(item.turn_id, "turn_id"),
            _required_positive_int(item.message_version, "message_version"),
            content_hash,
        )
    return tuple(
        sorted(
            normalized.values(),
            key=lambda item: (item[1], item[0]),
        )
    )


def _replace_evidence(
    story_memory_id: int,
    evidence: Iterable[models.MemoryEvidence],
) -> None:
    signature = _evidence_signature(evidence)
    SessionStoryMemoryEvidenceRecord.delete().where(
        SessionStoryMemoryEvidenceRecord.story_memory == story_memory_id
    ).execute()
    for message_id, turn_id, message_version, content_hash in signature:
        SessionStoryMemoryEvidenceRecord.create(
            story_memory=story_memory_id,
            message_id=message_id,
            turn_id=turn_id,
            message_version=message_version,
            content_hash=content_hash,
            created_at=SQL("CURRENT_TIMESTAMP"),
        )


def _evidence_for_memory(story_memory_id: int) -> tuple[models.MemoryEvidence, ...]:
    rows = (
        SessionStoryMemoryEvidenceRecord.select()
        .where(SessionStoryMemoryEvidenceRecord.story_memory == story_memory_id)
        .order_by(
            SessionStoryMemoryEvidenceRecord.turn_id,
            SessionStoryMemoryEvidenceRecord.message_id,
        )
    )
    return tuple(to_memory_evidence(row) for row in rows)


def _to_story_memory(row: SessionStoryMemoryRecord) -> models.SessionStoryMemory:
    return to_session_story_memory(
        row,
        evidence=_evidence_for_memory(int(row.id)),
    )


def _to_story_memories(
    rows: Iterable[SessionStoryMemoryRecord],
) -> list[models.SessionStoryMemory]:
    items = list(rows)
    if not items:
        return []
    memory_ids = [int(row.id) for row in items]
    evidence_by_memory: dict[int, list[models.MemoryEvidence]] = {}
    evidence_rows = (
        SessionStoryMemoryEvidenceRecord.select()
        .where(SessionStoryMemoryEvidenceRecord.story_memory.in_(memory_ids))
        .order_by(
            SessionStoryMemoryEvidenceRecord.story_memory,
            SessionStoryMemoryEvidenceRecord.turn_id,
            SessionStoryMemoryEvidenceRecord.message_id,
        )
    )
    for evidence_row in evidence_rows:
        evidence_by_memory.setdefault(
            int(evidence_row.story_memory_id),
            [],
        ).append(to_memory_evidence(evidence_row))
    return [
        to_session_story_memory(
            row,
            evidence=tuple(evidence_by_memory.get(int(row.id), ())),
        )
        for row in items
    ]


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
