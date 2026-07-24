from __future__ import annotations

import pytest

from rpg_core.status.administration import StatusTableAdministrationService
from rpg_data.model.status import (
    STATUS_KIND_SCENE,
    StatusTableDocument,
    StatusTableRow,
    StoryStatusTable,
)


class _Data:
    def __init__(self) -> None:
        self.document: StatusTableDocument | None = None
        self.table = StoryStatusTable(
            id=5,
            workspace_id="workspace",
            story_id=1,
            story_character_id=None,
            name="状态",
        )
        self.calls: list[tuple[object, ...]] = []

    def create_story_table(self, workspace_id, story_id, name, **kwargs):
        self.document = kwargs["document"]
        self.table = StoryStatusTable(
            id=5,
            workspace_id=workspace_id,
            story_id=story_id,
            story_character_id=kwargs.get("story_character_id"),
            name=name,
            status_kind=kwargs["status_kind"],
            document=kwargs["document"],
        )
        return self.table

    def get_story_table(self, table_id: int):
        return self.table if table_id == self.table.id else None

    def update_story_table(self, workspace_id, story_id, table_id, **kwargs):
        assert (workspace_id, story_id, table_id) == ("workspace", 1, 5)
        self.document = kwargs.get("document")
        return self.table

    def delete_story_table(self, workspace_id, story_id, table_id):
        self.calls.append(("delete_story_table", workspace_id, story_id, table_id))


def test_administration_prepares_scene_document_before_persistence() -> None:
    data = _Data()
    document = StatusTableDocument.from_rows(
        rows=[StatusTableRow("位置", "森林"), StatusTableRow("天气", "晴")]
    )

    StatusTableAdministrationService(data).create_story_table(
        "workspace",
        1,
        "当前场景",
        status_kind=STATUS_KIND_SCENE,
        document=document,
    )

    assert data.document is not None
    assert data.document.row_for_key("位置").runtime_key_locked is True
    assert data.document.row_for_key("天气").runtime_key_locked is False


def test_administration_preserves_rules_when_kind_changes_to_scene() -> None:
    data = _Data()
    data.table = StoryStatusTable(
        id=5,
        workspace_id="workspace",
        story_id=1,
        story_character_id=None,
        name="普通状态",
        document=StatusTableDocument.from_rows(
            rows=[
                StatusTableRow(
                    "备注",
                    "人工维护",
                    update_rule="仅在备注事实明确变化时更新",
                )
            ]
        ),
    )

    StatusTableAdministrationService(data).update_story_table(
        "workspace",
        1,
        5,
        status_kind=STATUS_KIND_SCENE,
    )

    assert data.document is not None
    assert data.document.rows[0].update_rule == "仅在备注事实明确变化时更新"


def test_administration_scopes_story_table_deletion() -> None:
    data = _Data()
    service = StatusTableAdministrationService(data)

    with pytest.raises(FileNotFoundError, match="Story status table not found"):
        service.delete_story_table(
            "workspace",
            2,
            5,
        )

    service.delete_story_table(
        "workspace",
        1,
        5,
    )
    assert data.calls == [("delete_story_table", "workspace", 1, 5)]
