"""Shared storage helpers for session message-shaped tables."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import TypeAlias

from peewee import Database, SQL

from rpg_data import models
from rpg_data.repositories import records
from rpg_data.repositories._utils import get_or_none, to_session_message
from rpg_data.repositories.records import bind_database

MessageRecord: TypeAlias = records.SessionMessageRecord | records.SessionBackupMessageRecord
MessageRecordModel: TypeAlias = type[records.SessionMessageRecord] | type[records.SessionBackupMessageRecord]
MessageInput: TypeAlias = models.SessionMessage | Mapping[str, object]

_VALID_ROLES = frozenset({"system", "user", "assistant", "tool"})


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
        turn_id: int = 0,
        seq_in_turn: int = 0,
        tool_call_id: str = "",
        tool_calls_json: str = "",
        metadata_json: str = "{}",
    ) -> models.SessionMessage:
        role = _validate_role(role)
        row = self._record_model.create(
            session=session_id,
            role=role,
            content=str(content or ""),
            turn_id=int(turn_id or 0),
            seq_in_turn=int(seq_in_turn or 0),
            tool_call_id=str(tool_call_id or ""),
            tool_calls_json=str(tool_calls_json or ""),
            metadata_json=str(metadata_json or "{}"),
        )
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
            .order_by(self._record_model.id)
        )
        if offset > 0:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return [to_session_message(row) for row in query]

    def get(self, message_id: int) -> models.SessionMessage | None:
        row = get_or_none(self._record_model, message_id)
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

    def update(
        self,
        message_id: int,
        *,
        role: str | None = None,
        content: str | None = None,
        turn_id: int | None = None,
        seq_in_turn: int | None = None,
        tool_call_id: str | None = None,
        tool_calls_json: str | None = None,
        metadata_json: str | None = None,
    ) -> models.SessionMessage | None:
        fields: dict[str, object] = {}
        if role is not None:
            fields["role"] = _validate_role(role)
        if content is not None:
            fields["content"] = str(content)
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
        with self._database.atomic():
            self.clear(session_id)
            return [self.append_mapping(session_id, message) for message in messages]

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


def _validate_role(role: str) -> str:
    normalized = str(role)
    if normalized not in _VALID_ROLES:
        raise ValueError(f"invalid session message role: {normalized}")
    return normalized


def _coerce_message_input(values: MessageInput) -> dict[str, object]:
    if isinstance(values, models.SessionMessage):
        return {
            "role": values.role,
            "content": values.content,
            "turn_id": values.turn_id,
            "seq_in_turn": values.seq_in_turn,
            "tool_call_id": values.tool_call_id,
            "tool_calls_json": values.tool_calls_json,
            "metadata_json": values.metadata_json,
        }

    tool_calls_json = values.get("tool_calls_json", "")
    if not tool_calls_json and values.get("tool_calls"):
        tool_calls_json = json.dumps(values["tool_calls"], ensure_ascii=False)
    return {
        "role": str(values["role"]),
        "content": str(values.get("content", "") or ""),
        "turn_id": int(values.get("turn_id", 0) or 0),
        "seq_in_turn": int(values.get("seq_in_turn", 0) or 0),
        "tool_call_id": str(values.get("tool_call_id", "") or ""),
        "tool_calls_json": str(tool_calls_json or ""),
        "metadata_json": str(values.get("metadata_json", "{}") or "{}"),
    }
