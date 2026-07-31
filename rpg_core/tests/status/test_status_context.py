from __future__ import annotations

import json

from rpg_core.status.context import prepare_status_context_tables, render_status_tables_context
from rpg_core.status.tools import (
    STATUS_TABLE_EDIT_FIELDS_TOOL_NAME,
    STATUS_TABLE_SET_VALUES_TOOL_NAME,
)


_STATUS_WRITE_TOOLS = (
    STATUS_TABLE_SET_VALUES_TOOL_NAME,
    STATUS_TABLE_EDIT_FIELDS_TOOL_NAME,
)


def _table(
    table_id: int,
    name: str,
    *,
    description: str = "",
    character_name: str | None = None,
    character_id: int | None = None,
) -> dict[str, object]:
    source = None
    if character_name is not None or character_id is not None:
        source = {
            "storyStatusTableId": 20 + table_id,
            "characterId": character_id,
            "characterName": character_name,
        }
    metadata = {"storyStatusSource": source} if source is not None else {}
    return {
        "id": table_id,
        "name": name,
        "description": description,
        "headers": ["属性", "值"],
        "rows": [["生命", "10"]],
        "document": {
            "schemaVersion": 2,
            "kind": "status_table",
            "mode": "key_value",
            "keyColumn": "属性",
            "valueColumn": "值",
            "rows": [{
                "key": "生命",
                "value": "10",
                "runtimeKeyLocked": False,
                "updateRule": "",
                "metadata": {},
            }],
            "metadata": {},
        },
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "origin": "story_copy",
        "source_story_status_table_id": 100 + table_id,
    }


def test_status_context_separates_regular_and_character_tables() -> None:
    world_table = _table(1, "世界状态", description="追踪世界事实。")
    world_table["document"] = {
        "rows": [{
            "key": "生命",
            "value": "10",
            "updateRule": "生命事实明确变化时更新",
        }],
    }
    rendered = render_status_tables_context(
        [
            world_table,
            _table(2, "身体状态", description="只在 Alice 受伤或恢复时更新。", character_name="Alice", character_id=7),
            _table(3, "装备状态", character_name="Alice", character_id=7),
        ],
        available_tool_names=_STATUS_WRITE_TOOLS,
    )

    assert "## 状态表" in rendered
    assert "status_table_set_values" in rendered
    assert "status_table_edit_fields" in rendered
    assert "本轮回复前的普通状态表快照" in rendered
    assert "遵循核心状态同步协议" in rendered
    assert "不能创建、删除或重命名整张表" in rendered
    assert "Key 结构" in rendered
    assert "规则为空时使用默认语义" in rendered
    assert "生命事实明确变化时更新" in rendered
    assert "deferred" not in rendered
    assert "manual" not in rendered
    assert "只有核验后确认无变化" not in rendered
    assert "### 世界状态" in rendered
    assert "运行时表 ID：1" in rendered
    assert "用途与更新规则：追踪世界事实。" in rendered
    assert "## 角色状态表" in rendered
    assert rendered.count("### Alice") == 1
    assert "#### 身体状态" in rendered
    assert "#### 装备状态" in rendered
    assert "只在 Alice 受伤或恢复时更新。" in rendered
    assert "仅在剧情事实明确影响现有键时更新" in rendered
    assert "story_copy" not in rendered
    assert "source_story_status_table_id" not in rendered
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


def test_status_context_does_not_fallback_to_flat_rows() -> None:
    table = _table(6, "空状态表")
    table["document"]["rows"] = []  # type: ignore[index]

    rendered = render_status_tables_context(
        [table],
        available_tool_names=_STATUS_WRITE_TOOLS,
    )

    assert "### 空状态表" in rendered
    assert "status_table_set_values" not in rendered
    assert "status_table_edit_fields" in rendered


def test_status_context_is_read_only_without_actual_tools_and_shows_lock() -> None:
    table = _table(7, "只读状态")
    table["document"]["rows"][0]["runtimeKeyLocked"] = True  # type: ignore[index]

    rendered = render_status_tables_context([table])

    assert "本轮未提供普通状态写入工具" in rendered
    assert "status_table_set_values" not in rendered
    assert "status_table_edit_fields" not in rendered
    assert "| 生命 | 10 | 锁定 |" in rendered
