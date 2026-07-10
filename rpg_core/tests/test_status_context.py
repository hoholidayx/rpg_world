from __future__ import annotations

import json

from rpg_core.status.context import prepare_status_context_tables, render_status_tables_context


def _table(
    table_id: int,
    name: str,
    *,
    description: str = "",
    character_name: str | None = None,
    character_id: int | None = None,
) -> dict[str, object]:
    mount = None
    if character_name is not None or character_id is not None:
        mount = {
            "mountId": 20 + table_id,
            "characterMountId": 30 + table_id,
            "characterId": character_id,
            "characterName": character_name,
        }
    metadata = {"storyStatusMount": mount} if mount is not None else {}
    return {
        "id": table_id,
        "name": name,
        "description": description,
        "headers": ["属性", "值"],
        "rows": [["生命", "10"]],
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "origin": "template_copy",
        "source_table_id": 100 + table_id,
    }


def test_status_context_separates_regular_and_character_tables() -> None:
    rendered = render_status_tables_context([
        _table(1, "世界状态", description="追踪世界事实。"),
        _table(2, "身体状态", description="只在 Alice 受伤或恢复时更新。", character_name="Alice", character_id=7),
        _table(3, "装备状态", character_name="Alice", character_id=7),
    ])

    assert "## 状态表" in rendered
    assert "status_table_set_values" in rendered
    assert "### 世界状态" in rendered
    assert "运行时表 ID：1" in rendered
    assert "用途与更新规则：追踪世界事实。" in rendered
    assert "## 角色状态表" in rendered
    assert rendered.count("### Alice") == 1
    assert "#### 身体状态" in rendered
    assert "#### 装备状态" in rendered
    assert "只在 Alice 受伤或恢复时更新。" in rendered
    assert "仅在剧情事实明确影响现有键时更新" in rendered
    assert "template_copy" not in rendered
    assert "source_table_id" not in rendered
    assert "characterId" not in rendered


def test_status_context_excludes_unresolved_character_table(caplog) -> None:
    with caplog.at_level("WARNING", logger="rpg_core.status.context"):
        prepared = prepare_status_context_tables([
            _table(4, "未知状态", character_name=None, character_id=99),
        ])
        rendered = render_status_tables_context(prepared)

    assert prepared == []
    assert rendered == ""
    assert "99" not in rendered
    assert "excluded character-bound status table" in caplog.text


def test_status_context_ignores_character_metadata_on_session_native_table() -> None:
    table = _table(5, "会话状态", character_name="伪造角色", character_id=100)
    table["origin"] = "session_native"

    prepared = prepare_status_context_tables([table])
    rendered = render_status_tables_context(prepared)

    assert prepared[0]["character_name"] is None
    assert "### 会话状态" in rendered
    assert "伪造角色" not in rendered


def test_empty_status_table_does_not_advertise_unregistered_writer() -> None:
    table = _table(6, "空状态表")
    table["rows"] = []

    rendered = render_status_tables_context([table])

    assert "### 空状态表" in rendered
    assert "status_table_set_values" not in rendered
