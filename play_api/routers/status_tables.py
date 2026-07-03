"""Status table management endpoints for Play WebUI backend."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from commons.types import JsonObject
from play_api.backends import get_data_manager_backend
from rpg_data import models

router = APIRouter(tags=["play-status-tables"])


class StatusRowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    key: str
    value: str = ""
    runtime_key_locked: bool = Field(default=False, alias="runtimeKeyLocked")
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("key")
    @classmethod
    def _key_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("key must not be empty")
        return value


class StatusDocumentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    key_column: str = Field(default=models.STATUS_KEY_COLUMN, alias="keyColumn")
    value_column: str = Field(default=models.STATUS_VALUE_COLUMN, alias="valueColumn")
    rows: list[StatusRowPayload] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)

    def to_document(self) -> models.StatusTableDocument:
        return models.StatusTableDocument.from_rows(
            key_column=self.key_column,
            value_column=self.value_column,
            rows=[
                models.StatusTableRow(
                    key=row.key,
                    value=row.value,
                    runtime_key_locked=row.runtime_key_locked,
                    metadata=row.metadata,
                )
                for row in self.rows
            ],
            metadata=self.metadata,
        )


class StatusTemplatePayload(StatusDocumentPayload):
    name: str
    status_kind: str = Field(default=models.STATUS_KIND_NORMAL, alias="statusKind")
    description: str = ""
    sort_order: int = Field(default=0, alias="sortOrder")
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class StatusTemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = None
    description: str | None = None
    sort_order: int | None = Field(default=None, alias="sortOrder")
    key_column: str | None = Field(default=None, alias="keyColumn")
    value_column: str | None = Field(default=None, alias="valueColumn")
    rows: list[StatusRowPayload] | None = None
    metadata: JsonObject | None = None

    def to_document(self, fallback: dict[str, object]) -> models.StatusTableDocument | None:
        if self.key_column is None and self.value_column is None and self.rows is None and self.metadata is None:
            return None
        return _document_from_patch(self, fallback)


class StoryStatusMountPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    template_id: int = Field(alias="templateId")
    sort_order: int = Field(default=0, alias="sortOrder")


class SessionStatusTablePayload(StatusDocumentPayload):
    name: str
    status_kind: str = Field(default=models.STATUS_KIND_NORMAL, alias="statusKind")
    description: str = ""
    sort_order: int = Field(default=0, alias="sortOrder")
    metadata: JsonObject = Field(default_factory=dict)


class SessionStatusTablePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = None
    description: str | None = None
    sort_order: int | None = Field(default=None, alias="sortOrder")
    key_column: str | None = Field(default=None, alias="keyColumn")
    value_column: str | None = Field(default=None, alias="valueColumn")
    rows: list[StatusRowPayload] | None = None
    metadata: JsonObject | None = None

    def to_document(self, fallback: dict[str, object]) -> models.StatusTableDocument | None:
        if self.key_column is None and self.value_column is None and self.rows is None and self.metadata is None:
            return None
        return _document_from_patch(self, fallback)


class StatusTableResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    status_kind: str = Field(alias="statusKind")
    description: str
    key_column: str = Field(alias="keyColumn")
    value_column: str = Field(alias="valueColumn")
    rows: list[StatusRowPayload]
    metadata: JsonObject = Field(default_factory=dict)
    sort_order: int = Field(alias="sortOrder")
    version: int
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    session_id: str | None = Field(default=None, alias="sessionId")
    story_id: int | None = Field(default=None, alias="storyId")
    source_table_id: int | None = Field(default=None, alias="sourceTableId")
    origin: str | None = None


class StoryStatusMountResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    workspace_id: str = Field(alias="workspaceId")
    story_id: int = Field(alias="storyId")
    status_table_id: int = Field(alias="statusTableId")
    table_name: str = Field(alias="tableName")
    status_kind: str = Field(alias="statusKind")
    description: str
    sort_order: int = Field(alias="sortOrder")
    metadata: JsonObject = Field(default_factory=dict)
    version: int
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


def _table_response(item: dict[str, object]) -> StatusTableResponse:
    return StatusTableResponse(
        id=int(item["id"]),
        workspace_id=str(item["workspace_id"]) if item.get("workspace_id") is not None else None,
        session_id=str(item["session_id"]) if item.get("session_id") is not None else None,
        story_id=int(item["story_id"]) if item.get("story_id") is not None else None,
        source_table_id=int(item["source_table_id"]) if item.get("source_table_id") is not None else None,
        origin=str(item["origin"]) if item.get("origin") is not None else None,
        name=str(item["name"]),
        status_kind=str(item["status_kind"]),
        description=str(item.get("description") or ""),
        key_column=str(item.get("key_column") or models.STATUS_KEY_COLUMN),
        value_column=str(item.get("value_column") or models.STATUS_VALUE_COLUMN),
        rows=[
            StatusRowPayload(
                key=str(row.get("key", "")),
                value=str(row.get("value", "")),
                runtimeKeyLocked=bool(row.get("runtime_key_locked", False)),
                metadata=dict(row.get("metadata") or {}),
            )
            for row in item.get("rows", [])
            if isinstance(row, dict)
        ],
        metadata=dict(item.get("metadata") or {}),
        sort_order=int(item.get("sort_order") or 0),
        version=int(item.get("version") or 1),
        created_at=str(item.get("created_at") or ""),
        updated_at=str(item.get("updated_at") or ""),
    )


def _mount_response(item: dict[str, object]) -> StoryStatusMountResponse:
    return StoryStatusMountResponse(
        id=int(item["id"]),
        workspace_id=str(item["workspace_id"]),
        story_id=int(item["story_id"]),
        status_table_id=int(item["status_table_id"]),
        table_name=str(item["table_name"]),
        status_kind=str(item["status_kind"]),
        description=str(item.get("description") or ""),
        sort_order=int(item.get("sort_order") or 0),
        metadata=dict(item.get("metadata") or {}),
        version=int(item.get("version") or 1),
        created_at=str(item.get("created_at") or ""),
        updated_at=str(item.get("updated_at") or ""),
    )


def _document_from_patch(
    payload: StatusTemplatePatch | SessionStatusTablePatch,
    fallback: dict[str, object],
) -> models.StatusTableDocument:
    rows = payload.rows
    if rows is None:
        rows = [
            StatusRowPayload(
                key=str(row.get("key", "")),
                value=str(row.get("value", "")),
                runtimeKeyLocked=bool(row.get("runtime_key_locked", False)),
                metadata=dict(row.get("metadata") or {}),
            )
            for row in fallback.get("rows", [])
            if isinstance(row, dict)
        ]
    return models.StatusTableDocument.from_rows(
        key_column=payload.key_column or str(fallback.get("key_column") or models.STATUS_KEY_COLUMN),
        value_column=payload.value_column or str(fallback.get("value_column") or models.STATUS_VALUE_COLUMN),
        rows=[
            models.StatusTableRow(row.key, row.value, row.runtime_key_locked, row.metadata)
            for row in rows
        ],
        metadata=payload.metadata if payload.metadata is not None else dict(fallback.get("metadata") or {}),
    )


@router.get("/workspaces/{workspace_id}/status-templates", response_model=list[StatusTableResponse])
async def list_status_templates(workspace_id: str, statusKind: str | None = None) -> list[StatusTableResponse]:
    items = await get_data_manager_backend().list_status_templates(workspace_id, status_kind=statusKind)
    if items is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return [_table_response(item) for item in items]


@router.post("/workspaces/{workspace_id}/status-templates", response_model=StatusTableResponse)
async def create_status_template(workspace_id: str, payload: StatusTemplatePayload) -> StatusTableResponse:
    item = await get_data_manager_backend().create_status_template(
        workspace_id,
        name=payload.name,
        status_kind=payload.status_kind,
        document=payload.to_document(),
        description=payload.description,
        sort_order=payload.sort_order,
        metadata=payload.metadata,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _table_response(item)


@router.patch("/workspaces/{workspace_id}/status-templates/{template_id}", response_model=StatusTableResponse)
async def update_status_template(workspace_id: str, template_id: int, payload: StatusTemplatePatch) -> StatusTableResponse:
    current_items = await get_data_manager_backend().list_status_templates(workspace_id)
    if current_items is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    current = next((item for item in current_items if int(item["id"]) == template_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="status template not found")
    item = await get_data_manager_backend().update_status_template(
        workspace_id,
        template_id,
        name=payload.name,
        document=payload.to_document(current),
        description=payload.description,
        sort_order=payload.sort_order,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="status template not found")
    return _table_response(item)


@router.delete("/workspaces/{workspace_id}/status-templates/{template_id}", status_code=204)
async def delete_status_template(workspace_id: str, template_id: int) -> None:
    try:
        deleted = await get_data_manager_backend().delete_status_template(workspace_id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if deleted is None:
        raise HTTPException(status_code=404, detail="status template not found")


@router.get("/workspaces/{workspace_id}/stories/{story_id}/status-mounts", response_model=list[StoryStatusMountResponse])
async def list_story_status_mounts(workspace_id: str, story_id: int) -> list[StoryStatusMountResponse]:
    items = await get_data_manager_backend().list_story_status_mounts(workspace_id, story_id)
    if items is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return [_mount_response(item) for item in items]


@router.post("/workspaces/{workspace_id}/stories/{story_id}/status-mounts", response_model=StoryStatusMountResponse)
async def mount_status_template(workspace_id: str, story_id: int, payload: StoryStatusMountPayload) -> StoryStatusMountResponse:
    try:
        item = await get_data_manager_backend().mount_status_template(
            workspace_id,
            story_id,
            payload.template_id,
            sort_order=payload.sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="story or status template not found")
    return _mount_response(item)


@router.delete("/workspaces/{workspace_id}/stories/{story_id}/status-mounts/{mount_id}", status_code=204)
async def unmount_status_template(workspace_id: str, story_id: int, mount_id: int) -> None:
    removed = await get_data_manager_backend().unmount_status_template(workspace_id, story_id, mount_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="status mount not found")


@router.get("/sessions/{session_id}/status-tables", response_model=list[StatusTableResponse])
async def list_session_status_tables(session_id: str, statusKind: str | None = None) -> list[StatusTableResponse]:
    items = await get_data_manager_backend().list_session_status_tables(session_id, status_kind=statusKind)
    if items is None:
        raise HTTPException(status_code=404, detail="session not found")
    return [_table_response(item) for item in items]


@router.post("/sessions/{session_id}/status-tables", response_model=StatusTableResponse)
async def create_session_status_table(session_id: str, payload: SessionStatusTablePayload) -> StatusTableResponse:
    item = await get_data_manager_backend().create_session_status_table(
        session_id,
        name=payload.name,
        status_kind=payload.status_kind,
        document=payload.to_document(),
        description=payload.description,
        sort_order=payload.sort_order,
        metadata=payload.metadata,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _table_response(item)


@router.patch("/sessions/{session_id}/status-tables/{table_id}", response_model=StatusTableResponse)
async def update_session_status_table(session_id: str, table_id: int, payload: SessionStatusTablePatch) -> StatusTableResponse:
    current_items = await get_data_manager_backend().list_session_status_tables(session_id)
    if current_items is None:
        raise HTTPException(status_code=404, detail="session not found")
    current = next((item for item in current_items if int(item["id"]) == table_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="status table not found")
    item = await get_data_manager_backend().update_session_status_table(
        session_id,
        table_id,
        name=payload.name,
        document=payload.to_document(current),
        description=payload.description,
        sort_order=payload.sort_order,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="status table not found")
    return _table_response(item)


@router.delete("/sessions/{session_id}/status-tables/{table_id}", status_code=204)
async def delete_session_status_table(session_id: str, table_id: int) -> None:
    deleted = await get_data_manager_backend().delete_session_status_table(session_id, table_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="status table not found")
