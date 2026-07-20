from __future__ import annotations

import pytest

from rpg_core.session.catalog import SessionCatalogService
from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway


def _opening(title: str, message: str, opening_id: int | None = None):
    return models.StoryOpeningInput(
        id=opening_id,
        title=title,
        message=message,
    )


def test_catalog_manages_zero_to_three_ordered_story_openings() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        catalog = SessionCatalogService(gateway)
        empty = catalog.create_story(
            "demo_workspace",
            title="无开局故事",
        )
        assert empty is not None
        assert empty.openings == ()

        story = catalog.create_story(
            "demo_workspace",
            title="多开局故事",
            openings=(
                _opening("开局甲", "甲"),
                _opening("开局乙", "乙"),
                _opening("开局丙", "丙"),
            ),
        )
        assert story is not None
        assert [(item.title, item.sort_order) for item in story.openings] == [
            ("开局甲", 0),
            ("开局乙", 1),
            ("开局丙", 2),
        ]

        first_id, second_id, third_id = (item.id for item in story.openings)
        updated = catalog.update_story(
            "demo_workspace",
            story.id,
            openings=(
                _opening("开局乙", "乙的新正文", second_id),
                _opening("开局甲", "甲的新正文", first_id),
                _opening("开局丙", "丙", third_id),
            ),
        )
        assert updated is not None
        assert [(item.id, item.title, item.sort_order) for item in updated.openings] == [
            (second_id, "开局乙", 0),
            (first_id, "开局甲", 1),
            (third_id, "开局丙", 2),
        ]

        with pytest.raises(ValueError, match="at most 3"):
            catalog.update_story(
                "demo_workspace",
                story.id,
                openings=tuple(_opening(f"开局 {index}", str(index)) for index in range(4)),
            )
        with pytest.raises(ValueError, match="duplicate story opening title"):
            catalog.update_story(
                "demo_workspace",
                story.id,
                openings=(_opening("重复", "一"), _opening("重复", "二")),
            )
    finally:
        gateway.close()


def test_story_opening_update_rejects_foreign_id_without_partial_changes() -> None:
    gateway = DataServiceGateway(":memory:")
    try:
        gateway.initialize()
        catalog = SessionCatalogService(gateway)
        first = catalog.create_story(
            "demo_workspace",
            title="开局归属甲",
            summary="原摘要",
            openings=(_opening("甲", "甲正文"),),
        )
        second = catalog.create_story(
            "demo_workspace",
            title="开局归属乙",
            openings=(_opening("乙", "乙正文"),),
        )
        assert first is not None and second is not None

        with pytest.raises(ValueError, match="does not belong"):
            catalog.update_story(
                "demo_workspace",
                first.id,
                summary="不应提交",
                openings=(_opening("越界", "越界正文", second.openings[0].id),),
            )

        unchanged = gateway.catalog.get_story("demo_workspace", first.id)
        assert unchanged is not None
        assert unchanged.summary == "原摘要"
        assert unchanged.version == first.version
        assert unchanged.openings == first.openings
    finally:
        gateway.close()
