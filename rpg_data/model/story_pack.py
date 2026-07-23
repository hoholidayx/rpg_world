"""Typed persistence contracts for Story Pack identity and operation ledgers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from commons.types import JsonValue


STORY_PACK_OPERATION_PREVIEWED = "previewed"
STORY_PACK_OPERATION_APPLYING = "applying"
STORY_PACK_OPERATION_APPLIED = "applied"
STORY_PACK_OPERATION_LOCAL_SYNC_PENDING = "applied_with_local_sync_pending"
STORY_PACK_OPERATION_FAILED = "failed"
STORY_PACK_OPERATION_STATUSES = frozenset({
    STORY_PACK_OPERATION_PREVIEWED,
    STORY_PACK_OPERATION_APPLYING,
    STORY_PACK_OPERATION_APPLIED,
    STORY_PACK_OPERATION_LOCAL_SYNC_PENDING,
    STORY_PACK_OPERATION_FAILED,
})


@dataclass(frozen=True)
class StoryPackBinding:
    id: int
    workspace_id: str
    story_id: int
    resource_kind: str
    source_id: str
    resource_id: str
    source_digest: str
    resource_version: int
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryPackOperation:
    id: str
    operation_kind: str
    status: str
    project_id: str
    pack_id: str
    pack_digest: str
    workspace_id: str
    story_stable_id: str
    story_id: int | None
    pack: Mapping[str, JsonValue]
    plan: Mapping[str, JsonValue]
    result: Mapping[str, JsonValue] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    applied_at: str | None = None


__all__ = [
    "STORY_PACK_OPERATION_APPLIED",
    "STORY_PACK_OPERATION_APPLYING",
    "STORY_PACK_OPERATION_FAILED",
    "STORY_PACK_OPERATION_LOCAL_SYNC_PENDING",
    "STORY_PACK_OPERATION_PREVIEWED",
    "STORY_PACK_OPERATION_STATUSES",
    "StoryPackBinding",
    "StoryPackOperation",
]
