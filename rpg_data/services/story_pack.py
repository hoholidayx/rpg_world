"""Typed Story Pack binding and operation-ledger persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any, Iterator

from peewee import Database, IntegrityError, SQL

from commons.types import JsonValue
from rpg_data.errors import DataIntegrityError
from rpg_data.model.story_pack import (
    STORY_PACK_OPERATION_APPLIED,
    STORY_PACK_OPERATION_APPLYING,
    STORY_PACK_OPERATION_FAILED,
    STORY_PACK_OPERATION_LOCAL_SYNC_PENDING,
    STORY_PACK_OPERATION_PREVIEWED,
    StoryPackBinding,
    StoryPackOperation,
)
from rpg_data.repositories.records import (
    StoryPackBindingRecord,
    StoryPackOperationRecord,
    StoryRecord,
    bind_database,
)

__all__ = ["StoryPackDataService"]


class StoryPackDataService:
    """Store caller-decided import identity and CAS operation transitions."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._database.atomic():
            yield

    def get_binding(
        self,
        workspace_id: str,
        story_id: int,
        resource_kind: str,
        source_id: str,
    ) -> StoryPackBinding | None:
        row = StoryPackBindingRecord.get_or_none(
            (StoryPackBindingRecord.workspace == str(workspace_id))
            & (StoryPackBindingRecord.story == int(story_id))
            & (StoryPackBindingRecord.resource_kind == str(resource_kind))
            & (StoryPackBindingRecord.source_id == str(source_id))
        )
        return _to_binding(row) if row is not None else None

    def list_bindings(
        self,
        workspace_id: str,
        story_id: int,
        *,
        resource_kind: str | None = None,
    ) -> list[StoryPackBinding]:
        self._require_story(workspace_id, story_id)
        query = StoryPackBindingRecord.select().where(
            (StoryPackBindingRecord.workspace == str(workspace_id))
            & (StoryPackBindingRecord.story == int(story_id))
        )
        if resource_kind is not None:
            query = query.where(
                StoryPackBindingRecord.resource_kind == str(resource_kind)
            )
        return [
            _to_binding(row)
            for row in query.order_by(
                StoryPackBindingRecord.resource_kind,
                StoryPackBindingRecord.source_id,
                StoryPackBindingRecord.id,
            )
        ]

    def find_bindings(
        self,
        workspace_id: str,
        resource_kind: str,
        source_id: str,
    ) -> list[StoryPackBinding]:
        rows = (
            StoryPackBindingRecord
            .select()
            .where(
                (StoryPackBindingRecord.workspace == str(workspace_id))
                & (
                    StoryPackBindingRecord.resource_kind
                    == str(resource_kind)
                )
                & (StoryPackBindingRecord.source_id == str(source_id))
            )
            .order_by(StoryPackBindingRecord.story, StoryPackBindingRecord.id)
        )
        return [_to_binding(row) for row in rows]

    def upsert_binding(
        self,
        workspace_id: str,
        story_id: int,
        resource_kind: str,
        source_id: str,
        *,
        resource_id: str | int,
        source_digest: str,
        resource_version: int,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> StoryPackBinding:
        self._require_story(workspace_id, story_id)
        normalized_kind = _required_text(resource_kind, "resource_kind")
        normalized_source = _required_text(source_id, "source_id")
        normalized_resource = _required_text(resource_id, "resource_id")
        normalized_digest = _sha256(source_digest, "source_digest")
        normalized_version = _positive_int(resource_version, "resource_version")
        metadata_json = _dump_json(dict(metadata or {}), "binding metadata")
        current = StoryPackBindingRecord.get_or_none(
            (StoryPackBindingRecord.story == int(story_id))
            & (StoryPackBindingRecord.resource_kind == normalized_kind)
            & (StoryPackBindingRecord.source_id == normalized_source)
        )
        try:
            if current is None:
                row = StoryPackBindingRecord.create(
                    workspace=str(workspace_id),
                    story=int(story_id),
                    resource_kind=normalized_kind,
                    source_id=normalized_source,
                    resource_id=normalized_resource,
                    source_digest=normalized_digest,
                    resource_version=normalized_version,
                    metadata_json=metadata_json,
                )
                return _to_binding(
                    StoryPackBindingRecord.get_by_id(int(row.id))
                )
            (
                StoryPackBindingRecord
                .update(
                    workspace=str(workspace_id),
                    resource_id=normalized_resource,
                    source_digest=normalized_digest,
                    resource_version=normalized_version,
                    metadata_json=metadata_json,
                    version=StoryPackBindingRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(StoryPackBindingRecord.id == int(current.id))
                .execute()
            )
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Story Pack binding write violated persisted constraints"
            ) from exc
        refreshed = StoryPackBindingRecord.get_by_id(int(current.id))
        return _to_binding(refreshed)

    def create_operation(
        self,
        operation_id: str,
        *,
        operation_kind: str,
        project_id: str,
        pack_id: str,
        pack_digest: str,
        workspace_id: str,
        story_stable_id: str,
        story_id: int | None,
        pack: Mapping[str, JsonValue],
        plan: Mapping[str, JsonValue],
    ) -> StoryPackOperation:
        normalized_id = _required_text(operation_id, "operation_id")
        normalized_kind = _required_text(operation_kind, "operation_kind")
        if story_id is not None:
            self._require_story(workspace_id, story_id)
        try:
            row = StoryPackOperationRecord.create(
                id=normalized_id,
                operation_kind=normalized_kind,
                status=STORY_PACK_OPERATION_PREVIEWED,
                project_id=_required_text(project_id, "project_id"),
                pack_id=_required_text(pack_id, "pack_id"),
                pack_digest=_sha256(pack_digest, "pack_digest"),
                workspace_id=_required_text(workspace_id, "workspace_id"),
                story_stable_id=_required_text(
                    story_stable_id,
                    "story_stable_id",
                ),
                story=story_id,
                pack_json=_dump_json(dict(pack), "pack"),
                plan_json=_dump_json(dict(plan), "plan"),
                result_json="{}",
            )
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Story Pack operation write violated persisted constraints"
            ) from exc
        return _to_operation(
            StoryPackOperationRecord.get_by_id(str(row.id))
        )

    def get_operation(self, operation_id: str) -> StoryPackOperation | None:
        row = StoryPackOperationRecord.get_or_none(
            StoryPackOperationRecord.id == str(operation_id)
        )
        return _to_operation(row) if row is not None else None

    def find_completed_operation(
        self,
        workspace_id: str,
        story_stable_id: str,
        pack_digest: str,
        *,
        operation_kind: str,
    ) -> StoryPackOperation | None:
        row = (
            StoryPackOperationRecord
            .select()
            .where(
                (StoryPackOperationRecord.workspace_id == str(workspace_id))
                & (
                    StoryPackOperationRecord.story_stable_id
                    == str(story_stable_id)
                )
                & (StoryPackOperationRecord.pack_digest == str(pack_digest))
                & (
                    StoryPackOperationRecord.operation_kind
                    == str(operation_kind)
                )
                & (
                    StoryPackOperationRecord.status.in_([
                        STORY_PACK_OPERATION_APPLIED,
                        STORY_PACK_OPERATION_LOCAL_SYNC_PENDING,
                    ])
                )
            )
            .order_by(StoryPackOperationRecord.created_at.desc())
            .first()
        )
        return _to_operation(row) if row is not None else None

    def claim_operation(self, operation_id: str) -> StoryPackOperation | None:
        updated = (
            StoryPackOperationRecord
            .update(
                status=STORY_PACK_OPERATION_APPLYING,
                version=StoryPackOperationRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (StoryPackOperationRecord.id == str(operation_id))
                & (
                    StoryPackOperationRecord.status
                    == STORY_PACK_OPERATION_PREVIEWED
                )
            )
            .execute()
        )
        return self.get_operation(operation_id) if updated == 1 else None

    def complete_operation(
        self,
        operation_id: str,
        *,
        story_id: int,
        result: Mapping[str, JsonValue],
    ) -> StoryPackOperation | None:
        updated = (
            StoryPackOperationRecord
            .update(
                status=STORY_PACK_OPERATION_APPLIED,
                story=int(story_id),
                result_json=_dump_json(dict(result), "result"),
                error_code="",
                error_message="",
                applied_at=SQL("CURRENT_TIMESTAMP"),
                version=StoryPackOperationRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (StoryPackOperationRecord.id == str(operation_id))
                & (
                    StoryPackOperationRecord.status
                    == STORY_PACK_OPERATION_APPLYING
                )
            )
            .execute()
        )
        return self.get_operation(operation_id) if updated == 1 else None

    def mark_local_sync_pending(
        self,
        operation_id: str,
        *,
        error_message: str,
    ) -> StoryPackOperation | None:
        updated = (
            StoryPackOperationRecord
            .update(
                status=STORY_PACK_OPERATION_LOCAL_SYNC_PENDING,
                error_code="local_sync_failed",
                error_message=str(error_message),
                version=StoryPackOperationRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (StoryPackOperationRecord.id == str(operation_id))
                & (
                    StoryPackOperationRecord.status
                    == STORY_PACK_OPERATION_APPLIED
                )
            )
            .execute()
        )
        return self.get_operation(operation_id) if updated == 1 else None

    def update_applied_result(
        self,
        operation_id: str,
        *,
        result: Mapping[str, JsonValue],
    ) -> StoryPackOperation | None:
        updated = (
            StoryPackOperationRecord
            .update(
                result_json=_dump_json(dict(result), "result"),
                version=StoryPackOperationRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (StoryPackOperationRecord.id == str(operation_id))
                & (
                    StoryPackOperationRecord.status
                    == STORY_PACK_OPERATION_APPLIED
                )
            )
            .execute()
        )
        return self.get_operation(operation_id) if updated == 1 else None

    def mark_local_sync_complete(
        self,
        operation_id: str,
        *,
        result: Mapping[str, JsonValue],
    ) -> StoryPackOperation | None:
        updated = (
            StoryPackOperationRecord
            .update(
                status=STORY_PACK_OPERATION_APPLIED,
                result_json=_dump_json(dict(result), "result"),
                error_code="",
                error_message="",
                version=StoryPackOperationRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (StoryPackOperationRecord.id == str(operation_id))
                & (
                    StoryPackOperationRecord.status
                    == STORY_PACK_OPERATION_LOCAL_SYNC_PENDING
                )
            )
            .execute()
        )
        return self.get_operation(operation_id) if updated == 1 else None

    def fail_operation(
        self,
        operation_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> StoryPackOperation | None:
        updated = (
            StoryPackOperationRecord
            .update(
                status=STORY_PACK_OPERATION_FAILED,
                error_code=_required_text(error_code, "error_code"),
                error_message=str(error_message),
                version=StoryPackOperationRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (StoryPackOperationRecord.id == str(operation_id))
                & (
                    StoryPackOperationRecord.status.in_([
                        STORY_PACK_OPERATION_PREVIEWED,
                        STORY_PACK_OPERATION_APPLYING,
                    ])
                )
            )
            .execute()
        )
        return self.get_operation(operation_id) if updated == 1 else None

    @staticmethod
    def _require_story(workspace_id: str, story_id: int) -> None:
        story = StoryRecord.get_or_none(
            (StoryRecord.id == int(story_id))
            & (StoryRecord.workspace == str(workspace_id))
        )
        if story is None:
            raise FileNotFoundError(
                f"Story not found in workspace: {workspace_id}/{story_id}"
            )


def _to_binding(row: StoryPackBindingRecord) -> StoryPackBinding:
    return StoryPackBinding(
        id=int(row.id),
        workspace_id=str(row.workspace_id),
        story_id=int(row.story_id),
        resource_kind=str(row.resource_kind),
        source_id=str(row.source_id),
        resource_id=str(row.resource_id),
        source_digest=str(row.source_digest),
        resource_version=int(row.resource_version),
        metadata=_load_json(row.metadata_json),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _to_operation(row: StoryPackOperationRecord) -> StoryPackOperation:
    return StoryPackOperation(
        id=str(row.id),
        operation_kind=str(row.operation_kind),
        status=str(row.status),
        project_id=str(row.project_id),
        pack_id=str(row.pack_id),
        pack_digest=str(row.pack_digest),
        workspace_id=str(row.workspace_id),
        story_stable_id=str(row.story_stable_id),
        story_id=int(row.story_id) if row.story_id is not None else None,
        pack=_load_json(row.pack_json),
        plan=_load_json(row.plan_json),
        result=_load_json(row.result_json),
        error_code=str(row.error_code or ""),
        error_message=str(row.error_message or ""),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
        applied_at=(
            str(row.applied_at) if row.applied_at is not None else None
        ),
    )


def _dump_json(value: Mapping[str, Any], label: str) -> str:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be JSON-serializable") from exc


def _load_json(raw: str) -> dict[str, JsonValue]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _required_text(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized


def _sha256(value: object, label: str) -> str:
    normalized = _required_text(value, label)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
    return normalized


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return parsed
