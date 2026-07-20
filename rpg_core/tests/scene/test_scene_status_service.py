from __future__ import annotations

import pytest

from rpg_core.scene.status import SceneStatusPolicyError, SceneStatusService
from rpg_data.model.status import (
    STATUS_KIND_NORMAL,
    STATUS_KIND_SCENE,
    STATUS_UPDATE_FREQUENCY_MANUAL,
    SessionStatusTable,
    StatusTableDocument,
    StatusTableRow,
)


def _table(table_id: int, name: str, *, sort_order: int) -> SessionStatusTable:
    return SessionStatusTable(
        id=table_id,
        session_id="session",
        workspace_id="workspace",
        story_id=1,
        source_table_id=table_id + 10,
        origin="template_copy",
        name=name,
        status_kind=STATUS_KIND_SCENE,
        document=StatusTableDocument.from_rows(
            rows=[StatusTableRow("位置", name)]
        ),
        sort_order=sort_order,
    )


class _Data:
    def __init__(self, tables: list[SessionStatusTable]) -> None:
        self.tables = tables
        self.calls: list[tuple[str, object]] = []

    def list_tables(self, session_id: str, status_kind: str | None = None):
        self.calls.append((session_id, status_kind))
        return list(self.tables)


def test_scene_service_uses_first_data_sorted_table() -> None:
    first = _table(2, "当前场景", sort_order=10)
    later = _table(1, "备用场景", sort_order=20)
    data = _Data([first, later])

    service = SceneStatusService(data)

    assert service.get_active_table("session") is first
    assert service.get_attrs("session") == {"位置": "当前场景"}
    assert data.calls == [
        ("session", STATUS_KIND_SCENE),
        ("session", STATUS_KIND_SCENE),
    ]


def test_scene_document_policy_locks_core_fields() -> None:
    document = StatusTableDocument.from_rows(
        rows=[
            StatusTableRow("时间", "第 1 年 1 月 1 日 6 时"),
            StatusTableRow("位置", "森林"),
            StatusTableRow("天气", "晴"),
        ]
    )

    prepared = SceneStatusService.prepare_document(STATUS_KIND_SCENE, document)

    assert prepared.row_for_key("时间").runtime_key_locked is True
    assert prepared.row_for_key("位置").runtime_key_locked is True
    assert prepared.row_for_key("天气").runtime_key_locked is False
    assert SceneStatusService.prepare_document(STATUS_KIND_NORMAL, document) is document


def test_scene_document_policy_rejects_non_realtime_fields() -> None:
    document = StatusTableDocument.from_rows(
        rows=[
            StatusTableRow(
                "天气",
                "晴",
                update_frequency=STATUS_UPDATE_FREQUENCY_MANUAL,
            )
        ]
    )

    with pytest.raises(SceneStatusPolicyError, match="realtime"):
        SceneStatusService.prepare_document(STATUS_KIND_SCENE, document)
