"""Shared storage helpers for session message-shaped tables."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import TypeAlias

from peewee import Database, IntegrityError, SQL, fn

from commons.errors import InvalidTurnMetadataError
from rpg_data import models
from rpg_data.repositories import records
from rpg_data.repositories._utils import get_or_none, to_session_message
from rpg_data.repositories.records import bind_database

MessageRecord: TypeAlias = records.SessionMessageRecord | records.SessionBackupMessageRecord
MessageRecordModel: TypeAlias = type[records.SessionMessageRecord] | type[records.SessionBackupMessageRecord]
MessageInput: TypeAlias = models.SessionMessage | Mapping[str, object]


class BaseSessionMessageStore:
    """Common implementation for the main and backup message tables."""

    def __init__(self, database: Database, record_model: MessageRecordModel) -> None:
        self._database = database
        self._record_model = record_model
        bind_database(database)

    def append(
        self,
        session_id: str,
        role: str,
        content: str = "",
        *,
        mode: str = models.TURN_MODE_IC,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        tool_call_id: str = "",
        tool_calls_json: str = "",
        metadata_json: str = "{}",
        summary_processed: bool = False,
        summary_batch_id: int | None = None,
        summary_processed_at: str = "",
        story_memory_processed: bool = False,
        story_memory_processed_at: str = "",
    ) -> models.SessionMessage:
        role = _validate_role(role)
        mode = _validate_mode(mode)
        turn_id, seq_in_turn = _validate_turn_metadata_fields(turn_id, seq_in_turn)
        fields: dict[str, object] = {
            "session": session_id,
            "role": role,
            "content": str(content or ""),
            "mode": mode,
            "turn_id": int(turn_id or 0),
            "seq_in_turn": int(seq_in_turn or 0),
            "tool_call_id": str(tool_call_id or ""),
            "tool_calls_json": str(tool_calls_json or ""),
            "metadata_json": str(metadata_json or "{}"),
        }
        if _supports_processing_fields(self._record_model):
            fields.update(
                summary_processed=bool(summary_processed),
                summary_batch_id=summary_batch_id,
                summary_processed_at=str(summary_processed_at or "") or None,
                story_memory_processed=bool(story_memory_processed),
                story_memory_processed_at=str(story_memory_processed_at or "") or None,
            )
        try:
            row = self._record_model.create(**fields)
        except IntegrityError as exc:
            if _is_turn_metadata_integrity_error(exc):
                raise InvalidTurnMetadataError(
                    f"invalid turn metadata for session message append: session_id={session_id}, "
                    f"turn_id={turn_id}, seq_in_turn={seq_in_turn}: {exc}"
                ) from exc
            raise
        return to_session_message(row)

    def append_mapping(
        self,
        session_id: str,
        values: MessageInput,
    ) -> models.SessionMessage:
        payload = _coerce_message_input(values)
        return self.append(session_id, **payload)

    def list(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[models.SessionMessage]:
        query = (
            self._record_model
            .select()
            .where(self._record_model.session == session_id)
        )
        if _supports_processing_fields(self._record_model):
            query = query.order_by(
                self._record_model.turn_id,
                self._record_model.seq_in_turn,
                self._record_model.id,
            )
        else:
            query = query.order_by(self._record_model.id)
        if offset > 0:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return [to_session_message(row) for row in query]

    def list_turn_window(
        self,
        session_id: str,
        *,
        limit: int,
        before_turn_id: int | None = None,
        after_turn_id: int | None = None,
    ) -> list[models.SessionMessage]:
        turn_ids = self._turn_window_ids(
            session_id,
            limit=limit,
            before_turn_id=before_turn_id,
            after_turn_id=after_turn_id,
        )
        if not turn_ids:
            return []

        query = (
            self._record_model
            .select()
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.turn_id.in_(turn_ids))
            )
            .order_by(
                self._record_model.turn_id,
                self._record_model.seq_in_turn,
                self._record_model.id,
            )
        )
        return [to_session_message(row) for row in query]

    def has_turn_before(self, session_id: str, turn_id: int) -> bool:
        return bool(
            self._record_model
            .select(self._record_model.id)
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.turn_id > 0)
                & (self._record_model.turn_id < int(turn_id))
            )
            .limit(1)
            .first()
        )

    def has_turn_after(self, session_id: str, turn_id: int) -> bool:
        return bool(
            self._record_model
            .select(self._record_model.id)
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.turn_id > int(turn_id))
            )
            .limit(1)
            .first()
        )

    def get(self, message_id: int) -> models.SessionMessage | None:
        row = get_or_none(self._record_model, message_id)
        return to_session_message(row) if row is not None else None

    def get_for_session(self, session_id: str, message_id: int) -> models.SessionMessage | None:
        row = (
            self._record_model
            .select()
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.id == int(message_id))
            )
            .first()
        )
        return to_session_message(row) if row is not None else None

    def count(self, session_id: str) -> int:
        return int(
            self._record_model
            .select()
            .where(self._record_model.session == session_id)
            .count()
        )

    def latest_turn_id(self, session_id: str) -> int:
        row = (
            self._record_model
            .select(self._record_model.turn_id)
            .where(self._record_model.session == session_id)
            .order_by(self._record_model.turn_id.desc(), self._record_model.id.desc())
            .limit(1)
            .first()
        )
        if row is None:
            return 0
        return max(0, int(row.turn_id))

    def list_summary_turn_ranges(self, session_id: str) -> dict[int, tuple[int, int]]:
        """Aggregate UI-only turn ranges for processed summary batches."""

        if not _supports_processing_fields(self._record_model):
            return {}
        query = (
            self._record_model
            .select(
                self._record_model.summary_batch_id,
                fn.MIN(self._record_model.turn_id).alias("turn_start"),
                fn.MAX(self._record_model.turn_id).alias("turn_end"),
            )
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.summary_processed == 1)
                & (self._record_model.summary_batch_id.is_null(False))
                & (self._record_model.turn_id > 0)
            )
            .group_by(self._record_model.summary_batch_id)
        )
        return {
            int(row["summary_batch_id"]): (
                int(row["turn_start"]),
                int(row["turn_end"]),
            )
            for row in query.dicts()
        }

    def _turn_window_ids(
        self,
        session_id: str,
        *,
        limit: int,
        before_turn_id: int | None,
        after_turn_id: int | None,
    ) -> list[int]:
        normalized_limit = max(1, int(limit))
        query = (
            self._record_model
            .select(self._record_model.turn_id)
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.turn_id > 0)
            )
            .group_by(self._record_model.turn_id)
        )
        if before_turn_id is not None:
            query = (
                query
                .where(self._record_model.turn_id < int(before_turn_id))
                .order_by(self._record_model.turn_id.desc())
                .limit(normalized_limit)
            )
            return sorted(int(row.turn_id) for row in query)

        if after_turn_id is not None:
            query = (
                query
                .where(self._record_model.turn_id > int(after_turn_id))
                .order_by(self._record_model.turn_id)
                .limit(normalized_limit)
            )
            return [int(row.turn_id) for row in query]

        query = (
            query
            .order_by(self._record_model.turn_id.desc())
            .limit(normalized_limit)
        )
        return sorted(int(row.turn_id) for row in query)

    def update(
        self,
        message_id: int,
        *,
        role: str | None = None,
        content: str | None = None,
        mode: str | None = None,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        tool_call_id: str | None = None,
        tool_calls_json: str | None = None,
        metadata_json: str | None = None,
    ) -> models.SessionMessage | None:
        if turn_id is not None or seq_in_turn is not None:
            raise InvalidTurnMetadataError("turn_id and seq_in_turn are immutable; use a dedicated repair flow")
        fields: dict[str, object] = {}
        if role is not None:
            fields["role"] = _validate_role(role)
        if content is not None:
            fields["content"] = str(content)
        if mode is not None:
            fields["mode"] = _validate_mode(mode)
        if turn_id is not None:
            fields["turn_id"] = int(turn_id)
        if seq_in_turn is not None:
            fields["seq_in_turn"] = int(seq_in_turn)
        if tool_call_id is not None:
            fields["tool_call_id"] = str(tool_call_id)
        if tool_calls_json is not None:
            fields["tool_calls_json"] = str(tool_calls_json)
        if metadata_json is not None:
            fields["metadata_json"] = str(metadata_json)
        if not fields:
            return self.get(message_id)
        fields["updated_at"] = SQL("CURRENT_TIMESTAMP")
        updated = (
            self._record_model
            .update(**fields)
            .where(self._record_model.id == message_id)
            .execute()
        )
        if not updated:
            return None
        return self.get(message_id)

    def delete(self, message_id: int) -> bool:
        deleted = (
            self._record_model
            .delete()
            .where(self._record_model.id == message_id)
            .execute()
        )
        return bool(deleted)

    def delete_for_session(self, session_id: str, message_id: int) -> bool:
        deleted = (
            self._record_model
            .delete()
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.id == int(message_id))
            )
            .execute()
        )
        return bool(deleted)

    def clear(self, session_id: str) -> int:
        return int(
            self._record_model
            .delete()
            .where(self._record_model.session == session_id)
            .execute()
        )

    def replace(
        self,
        session_id: str,
        messages: Iterable[MessageInput],
    ) -> list[models.SessionMessage]:
        payloads = [_coerce_message_input(message) for message in messages]
        with self._database.atomic():
            self.clear(session_id)
            return [self.append(session_id, **payload) for payload in payloads]

    def truncate_before_id(self, session_id: str, boundary_id: int) -> int:
        boundary = (
            self._record_model
            .select(self._record_model.id)
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.id == int(boundary_id))
            )
            .first()
        )
        if boundary is None:
            raise FileNotFoundError(f"session message boundary not found: {boundary_id}")
        return int(
            self._record_model
            .delete()
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.id < int(boundary_id))
            )
            .execute()
        )

    def truncate_before_index(self, session_id: str, keep_from_index: int) -> int:
        if keep_from_index <= 0:
            return 0
        count = self.count(session_id)
        if keep_from_index >= count:
            return self.clear(session_id)
        boundary = (
            self._record_model
            .select(self._record_model.id)
            .where(self._record_model.session == session_id)
            .order_by(self._record_model.id)
            .offset(keep_from_index)
            .limit(1)
            .first()
        )
        if boundary is None:
            return self.clear(session_id)
        return self.truncate_before_id(session_id, int(boundary.id))

    def truncate_from_turn(self, session_id: str, turn_id: int) -> int:
        boundary_turn = int(turn_id)
        if boundary_turn <= 0:
            raise ValueError("turn_id must be positive")
        return int(
            self._record_model
            .delete()
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.turn_id >= boundary_turn)
            )
            .execute()
        )

    def mark_summary_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
        *,
        batch_id: int | None,
    ) -> int:
        ids = _normalize_ids(message_ids)
        if not ids:
            return 0
        return int(
            self._record_model
            .update(
                summary_processed=True,
                summary_batch_id=(int(batch_id) if batch_id is not None else None),
                summary_processed_at=SQL("CURRENT_TIMESTAMP"),
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.id.in_(ids))
            )
            .execute()
        )

    def mark_story_memory_processed(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int:
        ids = _normalize_ids(message_ids)
        if not ids:
            return 0
        return int(
            self._record_model
            .update(
                story_memory_processed=True,
                story_memory_processed_at=SQL("CURRENT_TIMESTAMP"),
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.id.in_(ids))
            )
            .execute()
        )

    def reset_processing_for_messages(
        self,
        session_id: str,
        message_ids: Iterable[int],
    ) -> int:
        ids = _normalize_ids(message_ids)
        if not ids:
            return 0
        return int(
            self._record_model
            .update(
                summary_processed=False,
                summary_batch_id=None,
                summary_processed_at=None,
                story_memory_processed=False,
                story_memory_processed_at=None,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (self._record_model.session == session_id)
                & (self._record_model.id.in_(ids))
            )
            .execute()
        )


def _validate_role(role: str) -> str:
    normalized = str(role)
    if normalized not in models.MESSAGE_ROLES:
        raise ValueError(f"invalid session message role: {normalized}")
    return normalized


def _validate_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower() or models.TURN_MODE_IC
    if normalized not in models.TURN_MODES:
        raise ValueError(f"invalid session message mode: {normalized}")
    return normalized


def _validate_turn_metadata_fields(
    turn_id: object | None,
    seq_in_turn: object | None,
) -> tuple[int, int]:
    return (
        _required_positive_int(turn_id, "turn_id"),
        _required_positive_int(seq_in_turn, "seq_in_turn"),
    )


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


def _is_turn_metadata_integrity_error(exc: IntegrityError) -> bool:
    message = str(exc)
    return any(
        marker in message
        for marker in (
            "turn_id",
            "seq_in_turn",
            "ux_rpg_session_messages_turn_seq",
            "rpg_session_messages.session_id, rpg_session_messages.turn_id, rpg_session_messages.seq_in_turn",
        )
    )


def _normalize_ids(message_ids: Iterable[int]) -> list[int]:
    return sorted({int(message_id) for message_id in message_ids if int(message_id) > 0})


def _supports_processing_fields(record_model: MessageRecordModel) -> bool:
    return hasattr(record_model, "summary_processed")


def _coerce_message_input(values: MessageInput) -> dict[str, object]:
    if isinstance(values, models.SessionMessage):
        return {
            "role": values.role,
            "content": values.content,
            "mode": values.mode,
            "turn_id": values.turn_id,
            "seq_in_turn": values.seq_in_turn,
            "tool_call_id": values.tool_call_id,
            "tool_calls_json": values.tool_calls_json,
            "metadata_json": values.metadata_json,
            "summary_processed": values.summary_processed,
            "summary_batch_id": values.summary_batch_id,
            "summary_processed_at": values.summary_processed_at,
            "story_memory_processed": values.story_memory_processed,
            "story_memory_processed_at": values.story_memory_processed_at,
        }

    tool_calls_json = values.get("tool_calls_json", "")
    if not tool_calls_json and values.get("tool_calls"):
        tool_calls_json = json.dumps(values["tool_calls"], ensure_ascii=False)
    return {
        "role": str(values["role"]),
        "content": str(values.get("content", "") or ""),
        "mode": _validate_mode(str(values.get("mode", models.TURN_MODE_IC) or "")),
        "turn_id": _required_positive_int(values.get("turn_id", values.get("turnId")), "turn_id"),
        "seq_in_turn": _required_positive_int(
            values.get("seq_in_turn", values.get("seqInTurn")),
            "seq_in_turn",
        ),
        "tool_call_id": str(values.get("tool_call_id", "") or ""),
        "tool_calls_json": str(tool_calls_json or ""),
        "metadata_json": str(values.get("metadata_json", "{}") or "{}"),
        "summary_processed": bool(values.get("summary_processed", False)),
        "summary_batch_id": _optional_int(values.get("summary_batch_id")),
        "summary_processed_at": str(values.get("summary_processed_at", "") or ""),
        "story_memory_processed": bool(values.get("story_memory_processed", False)),
        "story_memory_processed_at": str(values.get("story_memory_processed_at", "") or ""),
    }


def _optional_int(value: object | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
