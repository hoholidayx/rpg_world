"""Shared preparation and rendering for normal status-table context."""

from __future__ import annotations

import logging
from typing import Iterable

from rpg_data.model.status import (
    STATUS_ORIGIN_STORY_COPY,
    STATUS_ROW_UPDATE_RULE_KEY,
    parse_session_status_metadata,
)
from rpg_core.context.rendering import render_jinja_template
from rpg_core.status.tools import (
    STATUS_TABLE_EDIT_FIELDS_TOOL_NAME,
    STATUS_TABLE_SET_VALUES_TOOL_NAME,
)

_DEFAULT_DESCRIPTION = "仅在剧情事实明确影响现有键时更新；不确定时保持原值。"
_UNRESOLVED_CHARACTER = object()

logger = logging.getLogger("rpg_core.status.context")


def prepare_status_context_tables(
    tables: Iterable[dict[str, object]],
    *,
    available_tool_names: Iterable[str] = (),
    preflight_staged_table_ids: Iterable[int] = (),
) -> list[dict[str, object]]:
    tool_names = frozenset(str(name) for name in available_tool_names)
    staged_table_ids = frozenset(
        int(table_id) for table_id in preflight_staged_table_ids
    )
    prepared: list[dict[str, object]] = []
    for source in tables:
        table = dict(source)
        character_name = _character_name(table)
        if character_name is _UNRESOLVED_CHARACTER:
            source = parse_session_status_metadata(
                str(table.get("metadata_json") or "{}")
            ).story_source
            logger.warning(
                "excluded character-bound status table from LLM context because character name is missing session_id=%s table_id=%s character_id=%s",
                table.get("session_id"),
                table.get("id"),
                source.character_id if source is not None else None,
            )
            continue
        table["context_description"] = str(table.get("description") or "").strip() or _DEFAULT_DESCRIPTION
        table["character_name"] = character_name
        context_rows = _context_rows(table)
        table["context_rows"] = context_rows
        table["has_rows"] = bool(context_rows)
        table["value_writable"] = (
            STATUS_TABLE_SET_VALUES_TOOL_NAME in tool_names
            and bool(context_rows)
        )
        table["structure_writable"] = (
            STATUS_TABLE_EDIT_FIELDS_TOOL_NAME in tool_names
        )
        table["preflight_staged"] = int(table.get("id", 0)) in staged_table_ids
        prepared.append(table)
    return prepared


def render_status_tables_context(
    tables: Iterable[dict[str, object]],
    *,
    available_tool_names: Iterable[str] = (),
    preflight_staged_table_ids: Iterable[int] = (),
) -> str:
    prepared = prepare_status_context_tables(
        tables,
        available_tool_names=available_tool_names,
        preflight_staged_table_ids=preflight_staged_table_ids,
    )
    if not prepared:
        return ""
    return render_jinja_template(
        "modules/status_tables.jinja",
        status_tables=prepared,
    )


def _character_name(table: dict[str, object]) -> str | object | None:
    if str(table.get("origin") or "") != STATUS_ORIGIN_STORY_COPY:
        return None
    source = parse_session_status_metadata(
        str(table.get("metadata_json") or "{}")
    ).story_source
    if source is None:
        return None

    name = str(source.character_name or "").strip()
    if name:
        return name
    if source.character_id is not None:
        return _UNRESOLVED_CHARACTER
    return None


def _context_rows(table: dict[str, object]) -> list[dict[str, object]]:
    raw_document = table.get("document")
    rows = raw_document.get("rows") if isinstance(raw_document, dict) else None
    if not isinstance(rows, list):
        return []
    return [
        {
            "key": str(row.get("key", "")),
            "value": str(row.get("value", "")),
            "update_rule": str(row.get(STATUS_ROW_UPDATE_RULE_KEY) or ""),
            "runtime_key_locked": bool(
                row.get("runtimeKeyLocked", False)
            ),
        }
        for row in rows
        if isinstance(row, dict) and str(row.get("key", ""))
    ]
