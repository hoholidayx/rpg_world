"""Story Memory application service and exact-upsert policy."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import ContextManager, Protocol

from commons.errors import InvalidTurnMetadataError
from rpg_data.model import memory as models
from rpg_data.model.session import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    TURN_MODE_GM,
    TURN_MODE_IC,
    SessionMessage,
)
from rpg_data.transaction import DataTransactionMode
from rp_memory.memory_types import EpistemicStatus, MemoryKind

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_EVIDENCE_ROLES = frozenset(
    {MESSAGE_ROLE_USER, MESSAGE_ROLE_ASSISTANT}
)
_EVIDENCE_MODES = frozenset({TURN_MODE_IC, TURN_MODE_GM})


class StoryMemoryDataPort(Protocol):
    """Typed persistence operations required by the application policy."""

    def transaction(
        self,
        mode: DataTransactionMode = DataTransactionMode.DEFERRED,
    ) -> ContextManager[None]: ...

    def require_session(self, session_id: str) -> None: ...

    def list(
        self,
        session_id: str,
        *,
        dream_processed: bool | None = None,
    ) -> tuple[models.SessionStoryMemory, ...]: ...

    def list_page(
        self,
        session_id: str,
        *,
        page: int,
        page_size: int,
        memory_kind: str | None,
        dream_processed: bool | None,
    ) -> models.SessionStoryMemoryPage: ...

    def get(self, memory_id: int) -> models.SessionStoryMemory | None: ...

    def get_by_dedupe_key(
        self,
        session_id: str,
        dedupe_key: str,
    ) -> models.SessionStoryMemory | None: ...

    def create(
        self,
        session_id: str,
        values: models.StoryMemoryRowValues,
    ) -> models.SessionStoryMemory: ...

    def update(
        self,
        memory_id: int,
        values: models.StoryMemoryRowValues,
        *,
        expected_version: int,
    ) -> models.SessionStoryMemory: ...

    def replace_evidence(
        self,
        story_memory_id: int,
        evidence: Sequence[models.MemoryEvidence],
    ) -> None: ...

    def list_source_messages(
        self,
        session_id: str,
        message_ids: Sequence[int],
    ) -> tuple[SessionMessage, ...]: ...

    def mark_messages_processed(
        self,
        session_id: str,
        message_ids: Sequence[int],
    ) -> int: ...

    def clear(self, session_id: str) -> int: ...

    def set_dream_processed(
        self,
        memory_ids: Sequence[int],
        *,
        dream_processed: bool = True,
        session_id: str | None = None,
    ) -> int: ...


@dataclass(frozen=True)
class StoryMemoryCandidate:
    """Normalized fact supplied to the Story Memory merge policy."""

    turn_id: int
    text: str
    memory_kind: MemoryKind
    epistemic_status: EpistemicStatus
    salience: float
    source_turn_start: int
    source_turn_end: int
    dedupe_key: str
    dream_processed: bool
    metadata_schema_version: int
    metadata_json: str


@dataclass(frozen=True)
class StoryMemoryContextItem:
    id: int
    turn_id: int
    text: str
    memory_kind: MemoryKind
    epistemic_status: EpistemicStatus
    salience: float
    source_turn_start: int
    source_turn_end: int
    dedupe_key: str
    dream_processed: bool
    metadata_schema_version: int
    metadata: Mapping[str, object]

    def to_context_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "turn_id": self.turn_id,
            "text": self.text,
            "memory_kind": self.memory_kind.value,
            "epistemic_status": self.epistemic_status.value,
            "salience": self.salience,
            "source_turn_start": self.source_turn_start,
            "source_turn_end": self.source_turn_end,
            "dedupe_key": self.dedupe_key,
            "dream_processed": self.dream_processed,
            "metadata_schema_version": self.metadata_schema_version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class _ParsedCandidate:
    candidate: StoryMemoryCandidate
    evidence_message_ids: tuple[int, ...] | None = None
    evidence: tuple[models.MemoryEvidence, ...] | None = None


class StoryMemoryApplicationService:
    """Own Story Memory validation, identity, merge, Evidence, and version rules."""

    def __init__(self, data: StoryMemoryDataPort) -> None:
        self._data = data

    def list(
        self,
        session_id: str,
        *,
        dream_processed: bool | None = None,
    ) -> list[models.SessionStoryMemory]:
        return list(self._data.list(session_id, dream_processed=dream_processed))

    def list_page(
        self,
        session_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        memory_kind: str | MemoryKind | None = None,
        dream_processed: bool | None = None,
    ) -> models.SessionStoryMemoryPage:
        normalized_kind = (
            _memory_kind(memory_kind).value if memory_kind not in (None, "") else None
        )
        return self._data.list_page(
            session_id,
            page=page,
            page_size=page_size,
            memory_kind=normalized_kind,
            dream_processed=dream_processed,
        )

    def get(self, memory_id: int) -> models.SessionStoryMemory | None:
        return self._data.get(memory_id)

    def get_context_items(self, session_id: str) -> tuple[StoryMemoryContextItem, ...]:
        return tuple(_context_item(item) for item in self._data.list(session_id))

    def add_detail(
        self,
        session_id: str,
        text: str,
        *,
        turn_id: int,
        dream_processed: bool = False,
        memory_kind: str | MemoryKind = MemoryKind.EVENT,
        epistemic_status: str | EpistemicStatus = EpistemicStatus.CONFIRMED,
        salience: object = 0.5,
        source_turn_start: object | None = None,
        source_turn_end: object | None = None,
        dedupe_key: str = "",
        metadata_schema_version: object = 1,
        metadata_json: str = "{}",
        evidence_message_ids: Iterable[int] | None = None,
    ) -> models.SessionStoryMemory:
        parsed = _normalize_candidate(
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
        normalized_ids = (
            _normalize_evidence_message_ids(evidence_message_ids)
            if evidence_message_ids is not None
            else None
        )
        with self._data.transaction():
            evidence = (
                self._capture_evidence(session_id, normalized_ids)
                if normalized_ids is not None
                else None
            )
            candidate = _with_exact_source_range(parsed, evidence)
            return self._upsert(session_id, candidate, evidence=evidence)

    def add_candidate(
        self,
        session_id: str,
        detail: Mapping[str, object],
    ) -> models.SessionStoryMemory:
        """Parse one dynamic-layer mapping at the application boundary."""

        parsed = _parse_detail(detail)
        with self._data.transaction():
            evidence = (
                self._capture_evidence(session_id, parsed.evidence_message_ids)
                if parsed.evidence_message_ids is not None
                else parsed.evidence
            )
            candidate = _with_exact_source_range(parsed.candidate, evidence)
            return self._upsert(session_id, candidate, evidence=evidence)

    def add_details_and_mark_processed(
        self,
        session_id: str,
        details: Iterable[models.SessionStoryMemory | Mapping[str, object]],
        *,
        message_ids: Iterable[int],
    ) -> list[models.SessionStoryMemory]:
        parsed = tuple(_parse_detail(item) for item in details)
        batch_ids = _normalize_evidence_message_ids(message_ids)
        with self._data.transaction():
            source_rows = self._load_source_messages(session_id, batch_ids)
            source_by_id = {item.id: item for item in source_rows}
            saved: list[models.SessionStoryMemory] = []
            for item in parsed:
                evidence_ids = item.evidence_message_ids
                if not evidence_ids:
                    raise ValueError(
                        "each extracted story memory must cite evidence_message_ids"
                    )
                if not set(evidence_ids).issubset(source_by_id):
                    raise ValueError(
                        "story-memory Evidence must belong to the current source batch"
                    )
                evidence = tuple(
                    _message_evidence(message)
                    for message in source_rows
                    if message.id in set(evidence_ids)
                )
                candidate = _with_exact_source_range(item.candidate, evidence)
                saved.append(self._upsert(session_id, candidate, evidence=evidence))
            self._data.mark_messages_processed(session_id, batch_ids)
            return saved

    def set_details(
        self,
        session_id: str,
        details: Iterable[models.SessionStoryMemory | Mapping[str, object]],
    ) -> list[models.SessionStoryMemory]:
        parsed = tuple(_parse_detail(item) for item in details)
        with self._data.transaction():
            self._data.clear(session_id)
            saved: list[models.SessionStoryMemory] = []
            for item in parsed:
                evidence = item.evidence
                if evidence is None and item.evidence_message_ids is not None:
                    evidence = self._capture_evidence(
                        session_id,
                        item.evidence_message_ids,
                    )
                candidate = _with_exact_source_range(item.candidate, evidence)
                saved.append(self._upsert(session_id, candidate, evidence=evidence))
            return saved

    def clear(self, session_id: str) -> int:
        return self._data.clear(session_id)

    def set_dream_processed(
        self,
        memory_ids: Iterable[int],
        *,
        dream_processed: bool = True,
        session_id: str | None = None,
    ) -> int:
        ids = tuple(int(item) for item in memory_ids)
        return self._data.set_dream_processed(
            ids,
            dream_processed=dream_processed,
            session_id=session_id,
        )

    def require_session(self, session_id: str) -> None:
        self._data.require_session(session_id)

    def _capture_evidence(
        self,
        session_id: str,
        message_ids: tuple[int, ...],
    ) -> tuple[models.MemoryEvidence, ...]:
        return tuple(
            _message_evidence(item)
            for item in self._load_source_messages(session_id, message_ids)
        )

    def _load_source_messages(
        self,
        session_id: str,
        message_ids: tuple[int, ...],
    ) -> tuple[SessionMessage, ...]:
        rows = self._data.list_source_messages(session_id, message_ids)
        if len(rows) != len(message_ids):
            raise ValueError("story-memory source messages must belong to the session")
        if any(
            item.role not in _EVIDENCE_ROLES or item.mode not in _EVIDENCE_MODES
            for item in rows
        ):
            raise ValueError(
                "story-memory Evidence must reference IC/GM user or assistant messages"
            )
        return rows

    def _upsert(
        self,
        session_id: str,
        candidate: StoryMemoryCandidate,
        *,
        evidence: tuple[models.MemoryEvidence, ...] | None,
    ) -> models.SessionStoryMemory:
        existing = self._data.get_by_dedupe_key(session_id, candidate.dedupe_key)
        if existing is None:
            created = self._data.create(
                session_id,
                _row_values(candidate, version=1),
            )
            if evidence is not None:
                normalized_evidence = _normalize_evidence(evidence)
                self._data.replace_evidence(created.id, normalized_evidence)
                refreshed = self._data.get(created.id)
                if refreshed is None:
                    raise RuntimeError("Story Memory row disappeared after Evidence write")
                return refreshed
            return created

        previous_evidence = _normalize_evidence(existing.evidence)
        effective_evidence = previous_evidence if evidence is None else _normalize_evidence(evidence)
        merged = _merge_candidate(existing, candidate, evidence=evidence)
        next_version = existing.version + int(
            _semantic_signature_from_row(existing, previous_evidence)
            != _semantic_signature_from_candidate(merged, effective_evidence)
        )
        updated = self._data.update(
            existing.id,
            _row_values(merged, version=next_version),
            expected_version=existing.version,
        )
        if evidence is not None and _evidence_signature(effective_evidence) != _evidence_signature(
            previous_evidence
        ):
            self._data.replace_evidence(existing.id, effective_evidence)
            refreshed = self._data.get(existing.id)
            if refreshed is None:
                raise RuntimeError("Story Memory row disappeared after Evidence refresh")
            return refreshed
        return updated


def _parse_detail(
    detail: models.SessionStoryMemory | Mapping[str, object],
) -> _ParsedCandidate:
    if isinstance(detail, models.SessionStoryMemory):
        return _ParsedCandidate(
            candidate=_normalize_candidate(
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
    return _ParsedCandidate(
        candidate=_normalize_candidate(
            text=detail.get("text", ""),
            turn_id=detail.get("turn_id"),
            dream_processed=detail.get("dream_processed", False),
            memory_kind=detail.get("memory_kind", MemoryKind.EVENT),
            epistemic_status=detail.get(
                "epistemic_status",
                EpistemicStatus.CONFIRMED,
            ),
            salience=detail.get("salience", 0.5),
            source_turn_start=detail.get("source_turn_start"),
            source_turn_end=detail.get("source_turn_end"),
            dedupe_key=detail.get("dedupe_key", ""),
            metadata_schema_version=detail.get("metadata_schema_version", 1),
            metadata_json=metadata_json or "{}",
        ),
        evidence_message_ids=evidence_message_ids,
    )


def _normalize_candidate(
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
) -> StoryMemoryCandidate:
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
        raise ValueError(
            "source_turn_end must be greater than or equal to source_turn_start"
        )
    kind = _memory_kind(memory_kind)
    status = _epistemic_status(epistemic_status)
    if isinstance(salience, bool):
        raise ValueError("salience must be within [0, 1]")
    try:
        normalized_salience = float(salience)
    except (TypeError, ValueError) as exc:
        raise ValueError("salience must be within [0, 1]") from exc
    if not 0.0 <= normalized_salience <= 1.0:
        raise ValueError("salience must be within [0, 1]")
    schema_version = _required_positive_int(
        metadata_schema_version,
        "metadata_schema_version",
    )
    try:
        metadata = json.loads(str(metadata_json or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("story memory metadata_json must be a JSON object") from exc
    if not isinstance(metadata, dict):
        raise ValueError("story memory metadata_json must be a JSON object")
    normalized_text = " ".join(str(text or "").split())
    if not normalized_text:
        raise ValueError("story memory text must not be empty")
    normalized_key = _normalize_dedupe_key(
        str(dedupe_key or ""),
        kind,
        normalized_text,
    )
    return StoryMemoryCandidate(
        turn_id=normalized_turn_id,
        text=normalized_text,
        memory_kind=kind,
        epistemic_status=status,
        salience=normalized_salience,
        source_turn_start=start,
        source_turn_end=end,
        dedupe_key=normalized_key,
        dream_processed=bool(dream_processed),
        metadata_schema_version=schema_version,
        metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    )


def _merge_candidate(
    existing: models.SessionStoryMemory,
    incoming: StoryMemoryCandidate,
    *,
    evidence: tuple[models.MemoryEvidence, ...] | None,
) -> StoryMemoryCandidate:
    return StoryMemoryCandidate(
        turn_id=(
            incoming.turn_id
            if evidence is not None
            else max(existing.turn_id, incoming.turn_id)
        ),
        text=incoming.text,
        memory_kind=incoming.memory_kind,
        epistemic_status=incoming.epistemic_status,
        salience=max(existing.salience, incoming.salience),
        source_turn_start=(
            incoming.source_turn_start
            if evidence is not None
            else min(existing.source_turn_start, incoming.source_turn_start)
        ),
        source_turn_end=(
            incoming.source_turn_end
            if evidence is not None
            else max(existing.source_turn_end, incoming.source_turn_end)
        ),
        dedupe_key=existing.dedupe_key,
        dream_processed=existing.dream_processed or incoming.dream_processed,
        metadata_schema_version=max(
            existing.metadata_schema_version,
            incoming.metadata_schema_version,
        ),
        metadata_json=_merge_metadata_json(
            existing.metadata_json,
            incoming.metadata_json,
        ),
    )


def _with_exact_source_range(
    candidate: StoryMemoryCandidate,
    evidence: tuple[models.MemoryEvidence, ...] | None,
) -> StoryMemoryCandidate:
    if not evidence:
        return candidate
    turns = tuple(item.turn_id for item in evidence)
    return StoryMemoryCandidate(
        turn_id=max(turns),
        text=candidate.text,
        memory_kind=candidate.memory_kind,
        epistemic_status=candidate.epistemic_status,
        salience=candidate.salience,
        source_turn_start=min(turns),
        source_turn_end=max(turns),
        dedupe_key=candidate.dedupe_key,
        dream_processed=candidate.dream_processed,
        metadata_schema_version=candidate.metadata_schema_version,
        metadata_json=candidate.metadata_json,
    )


def _row_values(
    candidate: StoryMemoryCandidate,
    *,
    version: int,
) -> models.StoryMemoryRowValues:
    return models.StoryMemoryRowValues(
        turn_id=candidate.turn_id,
        text=candidate.text,
        memory_kind=candidate.memory_kind.value,
        epistemic_status=candidate.epistemic_status.value,
        salience=candidate.salience,
        source_turn_start=candidate.source_turn_start,
        source_turn_end=candidate.source_turn_end,
        dedupe_key=candidate.dedupe_key,
        dream_processed=candidate.dream_processed,
        metadata_schema_version=candidate.metadata_schema_version,
        metadata_json=candidate.metadata_json,
        version=version,
    )


def _semantic_signature_from_row(
    row: models.SessionStoryMemory,
    evidence: Sequence[models.MemoryEvidence],
) -> tuple[object, ...]:
    return (
        row.turn_id,
        row.text,
        row.memory_kind,
        row.epistemic_status,
        row.salience,
        row.source_turn_start,
        row.source_turn_end,
        row.metadata_schema_version,
        row.metadata_json,
        _evidence_signature(evidence),
    )


def _semantic_signature_from_candidate(
    candidate: StoryMemoryCandidate,
    evidence: Sequence[models.MemoryEvidence],
) -> tuple[object, ...]:
    return (
        candidate.turn_id,
        candidate.text,
        candidate.memory_kind.value,
        candidate.epistemic_status.value,
        candidate.salience,
        candidate.source_turn_start,
        candidate.source_turn_end,
        candidate.metadata_schema_version,
        candidate.metadata_json,
        _evidence_signature(evidence),
    )


def _message_evidence(message: SessionMessage) -> models.MemoryEvidence:
    return models.MemoryEvidence(
        message_id=message.id,
        turn_id=message.turn_id,
        message_version=message.version,
        content_hash=hashlib.sha256(message.content.encode("utf-8")).hexdigest(),
    )


def _normalize_evidence(
    evidence: Iterable[models.MemoryEvidence],
) -> tuple[models.MemoryEvidence, ...]:
    signature = _evidence_signature(evidence)
    return tuple(
        models.MemoryEvidence(
            message_id=message_id,
            turn_id=turn_id,
            message_version=message_version,
            content_hash=content_hash,
        )
        for message_id, turn_id, message_version, content_hash in signature
    )


def _evidence_signature(
    evidence: Iterable[models.MemoryEvidence],
) -> tuple[tuple[int, int, int, str], ...]:
    normalized: dict[int, tuple[int, int, int, str]] = {}
    for item in evidence:
        message_id = _required_positive_int(item.message_id, "message_id")
        if message_id in normalized:
            raise ValueError("story-memory Evidence message IDs must be unique")
        content_hash = str(item.content_hash or "").strip().lower()
        if _SHA256_RE.fullmatch(content_hash) is None:
            raise ValueError("story-memory Evidence content_hash must be SHA-256")
        normalized[message_id] = (
            message_id,
            _required_positive_int(item.turn_id, "turn_id"),
            _required_positive_int(item.message_version, "message_version"),
            content_hash,
        )
    return tuple(sorted(normalized.values(), key=lambda item: (item[1], item[0])))


def _normalize_evidence_message_ids(values: object) -> tuple[int, ...]:
    if values is None or isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError("evidence_message_ids must be an array of positive integers")
    normalized = tuple(
        _required_positive_int(value, "evidence_message_id") for value in values
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError("evidence_message_ids must be unique")
    return normalized


def _context_item(memory: models.SessionStoryMemory) -> StoryMemoryContextItem:
    try:
        metadata = json.loads(memory.metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return StoryMemoryContextItem(
        id=memory.id,
        turn_id=memory.turn_id,
        text=memory.text,
        memory_kind=_memory_kind(memory.memory_kind),
        epistemic_status=_epistemic_status(memory.epistemic_status),
        salience=memory.salience,
        source_turn_start=memory.source_turn_start,
        source_turn_end=memory.source_turn_end,
        dedupe_key=memory.dedupe_key,
        dream_processed=memory.dream_processed,
        metadata_schema_version=memory.metadata_schema_version,
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _normalize_dedupe_key(raw: str, kind: MemoryKind, text: str) -> str:
    normalized_raw = raw.strip().casefold()
    if _SHA256_RE.fullmatch(normalized_raw) is not None:
        return normalized_raw
    canonical = re.sub(r"\s+", "", raw or text).casefold()
    return hashlib.sha256(f"{kind.value}:{canonical}".encode("utf-8")).hexdigest()


def _merge_metadata_json(existing_json: str, incoming_json: str) -> str:
    existing = json.loads(existing_json or "{}")
    incoming = json.loads(incoming_json or "{}")
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        raise ValueError("story memory metadata_json must be a JSON object")
    return json.dumps({**existing, **incoming}, ensure_ascii=False, sort_keys=True)


def _memory_kind(value: object) -> MemoryKind:
    try:
        return value if isinstance(value, MemoryKind) else MemoryKind(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"unsupported story-memory memory_kind: {value}") from exc


def _epistemic_status(value: object) -> EpistemicStatus:
    try:
        return (
            value
            if isinstance(value, EpistemicStatus)
            else EpistemicStatus(str(value).strip().lower())
        )
    except ValueError as exc:
        raise ValueError(
            f"unsupported story memory epistemic status: {value}"
        ) from exc


def _required_positive_int(value: object | None, field_name: str) -> int:
    if value is None or value == "" or isinstance(value, bool):
        raise InvalidTurnMetadataError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidTurnMetadataError(
            f"{field_name} must be a positive integer"
        ) from exc
    if parsed <= 0:
        raise InvalidTurnMetadataError(f"{field_name} must be a positive integer")
    return parsed
