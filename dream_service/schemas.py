from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dream_service.contracts import (
    DreamMemoryListView,
    DreamMemoryView,
    DreamProposalListView,
    DreamProposalView,
)
from rp_memory.dream.types import (
    MAX_DREAM_FACT_TEXT_CHARS,
    MAX_DREAM_ITEM_EVIDENCE,
    MAX_DREAM_PROPOSAL_ITEMS,
    MAX_DREAM_REASON_CHARS,
)


class DreamSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class DreamHealthResponse(DreamSchema):
    status: Literal["ok"] = "ok"


class DreamProposalCreateRequest(DreamSchema):
    depth: Literal["shallow", "deep"]
    scope: Literal["incremental", "full"]
    recover_proposal_id: str | None = Field(
        default=None,
        alias="recoverProposalId",
        min_length=1,
    )


class DreamEvidenceResponse(DreamSchema):
    message_id: int = Field(alias="messageId")
    turn_id: int = Field(alias="turnId")
    message_version: int = Field(alias="messageVersion")
    content_hash: str = Field(alias="contentHash")


class DreamProposalItemResponse(DreamSchema):
    item_id: str = Field(alias="itemId")
    action: Literal["add", "revise", "supersede", "retire"]
    target_memory_id: str | None = Field(default=None, alias="targetMemoryId")
    base_revision_number: int | None = Field(
        default=None,
        alias="baseRevisionNumber",
    )
    selected: bool
    text: str | None = Field(default=None, max_length=MAX_DREAM_FACT_TEXT_CHARS)
    memory_kind: str | None = Field(default=None, alias="memoryKind")
    epistemic_status: str | None = Field(default=None, alias="epistemicStatus")
    salience: float | None = None
    reason: str = Field(default="", max_length=MAX_DREAM_REASON_CHARS)
    evidence: list[DreamEvidenceResponse] = Field(
        default_factory=list,
        max_length=MAX_DREAM_ITEM_EVIDENCE,
    )


class DreamProposalResponse(DreamSchema):
    proposal_id: str = Field(alias="proposalId")
    session_id: str = Field(alias="sessionId")
    depth: Literal["shallow", "deep"]
    scope: Literal["incremental", "full"]
    status: Literal[
        "generating",
        "ready",
        "applied",
        "rejected",
        "failed",
        "interrupted",
        "stale",
    ]
    ledger_revision: int = Field(alias="ledgerRevision")
    items: list[DreamProposalItemResponse] = Field(
        default_factory=list,
        max_length=MAX_DREAM_PROPOSAL_ITEMS,
    )
    error_code: str = Field(default="", alias="errorCode")
    error_message: str = Field(default="", alias="errorMessage")
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")
    finished_at: str = Field(default="", alias="finishedAt")


class DreamProposalListResponse(DreamSchema):
    items: list[DreamProposalResponse]


class DreamProposalItemUpdateRequest(DreamSchema):
    item_id: str = Field(alias="itemId")
    selected: bool | None = None
    text: str | None = Field(default=None, max_length=MAX_DREAM_FACT_TEXT_CHARS)
    memory_kind: str | None = Field(default=None, alias="memoryKind")
    epistemic_status: str | None = Field(default=None, alias="epistemicStatus")
    salience: float | None = None


class DreamProposalUpdateRequest(DreamSchema):
    items: list[DreamProposalItemUpdateRequest] = Field(
        max_length=MAX_DREAM_PROPOSAL_ITEMS
    )


class DreamMemoryRevisionResponse(DreamSchema):
    revision_number: int = Field(alias="revisionNumber")
    text: str = Field(max_length=MAX_DREAM_FACT_TEXT_CHARS)
    memory_kind: str = Field(alias="memoryKind")
    epistemic_status: str = Field(alias="epistemicStatus")
    salience: float
    dedupe_key: str = Field(alias="dedupeKey")
    proposal_id: str | None = Field(default=None, alias="proposalId")
    created_at: str = Field(default="", alias="createdAt")


class DreamMemoryResponse(DreamSchema):
    memory_id: str = Field(alias="memoryId")
    session_id: str = Field(alias="sessionId")
    lifecycle: Literal["active", "retired", "superseded"]
    current_revision_number: int = Field(alias="currentRevisionNumber")
    superseded_by_memory_id: str | None = Field(
        default=None,
        alias="supersededByMemoryId",
    )
    evidence_valid: bool = Field(alias="evidenceValid")
    current_revision: DreamMemoryRevisionResponse = Field(alias="currentRevision")
    revisions: list[DreamMemoryRevisionResponse] = Field(default_factory=list)
    evidence: list[DreamEvidenceResponse] = Field(
        default_factory=list,
        max_length=MAX_DREAM_ITEM_EVIDENCE,
    )
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")


class DreamMemoryListResponse(DreamSchema):
    items: list[DreamMemoryResponse]
    active_count: int = Field(alias="activeCount")
    active_limit: int = Field(alias="activeLimit")


def proposal_response(view: DreamProposalView) -> DreamProposalResponse:
    return DreamProposalResponse.model_validate(view, from_attributes=True)


def proposal_list_response(view: DreamProposalListView) -> DreamProposalListResponse:
    return DreamProposalListResponse.model_validate(view, from_attributes=True)


def memory_response(view: DreamMemoryView) -> DreamMemoryResponse:
    return DreamMemoryResponse.model_validate(view, from_attributes=True)


def memory_list_response(view: DreamMemoryListView) -> DreamMemoryListResponse:
    return DreamMemoryListResponse.model_validate(view, from_attributes=True)
