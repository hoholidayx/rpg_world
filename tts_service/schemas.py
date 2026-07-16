from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TTSSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class TTSHealthResponse(TTSSchema):
    status: Literal["ok"] = "ok"


class TTSAudioPartResponse(TTSSchema):
    part_index: int = Field(alias="partIndex")
    audio_url: str = Field(alias="audioUrl")


class TTSJobResponse(TTSSchema):
    job_id: str = Field(alias="jobId")
    session_id: str = Field(alias="sessionId")
    message_id: int = Field(alias="messageId")
    status: Literal["queued", "running", "succeeded", "failed", "interrupted"]
    part_count: int = Field(alias="partCount")
    parts: list[TTSAudioPartResponse] = Field(default_factory=list)
    error_code: str = Field(alias="errorCode")
    error_message: str = Field(alias="errorMessage")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class TTSReconcileResponse(TTSSchema):
    workspace_id: str = Field(alias="workspaceId")
    scanned_blobs: int = Field(alias="scannedBlobs")
    removed_blobs: int = Field(alias="removedBlobs")
    removed_files: int = Field(alias="removedFiles")
