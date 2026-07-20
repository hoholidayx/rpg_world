from __future__ import annotations

from contextlib import contextmanager

import pytest

from rpg_core.scene.status import SceneStatusPolicyError
from rpg_core.status.administration import StatusTableAdministrationService
from rpg_data.model.status import (
    STATUS_KIND_SCENE,
    STATUS_UPDATE_FREQUENCY_MANUAL,
    STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE,
    STORY_STATUS_MOUNT_ORIGIN_SYSTEM,
    StatusTableDocument,
    StatusTableRow,
    StatusTableTemplate,
    StoryStatusTable,
)


class _Data:
    def __init__(self, mount_origin=STORY_STATUS_MOUNT_ORIGIN_SYSTEM) -> None:
        self.document: StatusTableDocument | None = None
        self.mount = StoryStatusTable(
            id=5,
            workspace_id="workspace",
            story_id=1,
            status_table_id=9,
            story_character_mount_id=None,
            table_name="状态",
            mount_origin=mount_origin,
        )
        self.calls: list[tuple[object, ...]] = []
        self.still_mounted = False
        self.template = StatusTableTemplate(
            id=9,
            workspace_id="workspace",
            name="状态",
        )

    @contextmanager
    def transaction(self):
        self.calls.append(("transaction",))
        yield

    def create_template(self, workspace_id, name, **kwargs):
        self.document = kwargs["document"]
        self.template = StatusTableTemplate(
            id=9,
            workspace_id=workspace_id,
            name=name,
            status_kind=kwargs["status_kind"],
            document=kwargs["document"],
        )
        return self.template

    def get_template(self, template_id: int):
        assert template_id == self.template.id
        return self.template

    def get_story_mount(self, mount_id: int):
        assert mount_id == self.mount.id
        return self.mount

    def unmount_template(self, mount_id: int):
        self.calls.append(("unmount", mount_id))

    def has_template_mounts(self, template_id: int):
        self.calls.append(("has_mounts", template_id))
        return self.still_mounted

    def delete_template(self, template_id: int):
        self.calls.append(("delete_template", template_id))


def test_administration_prepares_scene_document_before_persistence() -> None:
    data = _Data()
    document = StatusTableDocument.from_rows(
        rows=[StatusTableRow("位置", "森林"), StatusTableRow("天气", "晴")]
    )

    StatusTableAdministrationService(data).create_template(
        "workspace",
        "当前场景",
        status_kind=STATUS_KIND_SCENE,
        document=document,
    )

    assert data.document is not None
    assert data.document.row_for_key("位置").runtime_key_locked is True
    assert data.document.row_for_key("天气").runtime_key_locked is False


def test_administration_validates_existing_document_when_kind_changes() -> None:
    data = _Data()
    data.template = StatusTableTemplate(
        id=9,
        workspace_id="workspace",
        name="普通状态",
        document=StatusTableDocument.from_rows(
            rows=[
                StatusTableRow(
                    "备注",
                    "人工维护",
                    update_frequency=STATUS_UPDATE_FREQUENCY_MANUAL,
                )
            ]
        ),
    )

    with pytest.raises(SceneStatusPolicyError, match="realtime"):
        StatusTableAdministrationService(data).update_template(
            "workspace",
            9,
            status_kind=STATUS_KIND_SCENE,
        )


def test_administration_only_deletes_story_owned_mounts() -> None:
    system_data = _Data(STORY_STATUS_MOUNT_ORIGIN_SYSTEM)
    with pytest.raises(ValueError, match="not story-owned"):
        StatusTableAdministrationService(system_data).delete_story_template(
            "workspace",
            1,
            5,
        )
    assert ("unmount", 5) not in system_data.calls

    owned_data = _Data(STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE)
    StatusTableAdministrationService(owned_data).delete_story_template(
        "workspace",
        1,
        5,
    )
    assert owned_data.calls == [
        ("transaction",),
        ("unmount", 5),
        ("has_mounts", 9),
        ("delete_template", 9),
    ]
