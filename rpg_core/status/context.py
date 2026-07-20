"""Shared preparation and rendering for normal status-table context."""

from __future__ import annotations

import logging
from typing import Iterable

from rpg_data.model.status import (
    STATUS_ORIGIN_TEMPLATE_COPY,
    STATUS_ROW_UPDATE_FREQUENCY_KEY,
    STATUS_ROW_UPDATE_RULE_KEY,
    STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
    STATUS_UPDATE_FREQUENCY_REALTIME,
    parse_session_status_metadata,
)
from rpg_core.context.rendering import render_jinja_template

_DEFAULT_DESCRIPTION = "仅在剧情事实明确影响现有键时更新；不确定时保持原值。"
_UNRESOLVED_CHARACTER = object()

logger = logging.getLogger("rpg_core.status.context")


def prepare_status_context_tables(
    tables: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    prepared: list[dict[str, object]] = []
    for source in tables:
        table = dict(source)
        character_name = _character_name(table)
        if character_name is _UNRESOLVED_CHARACTER:
            mount = parse_session_status_metadata(
                str(table.get("metadata_json") or "{}")
            ).story_mount
            logger.warning(
                "excluded character-bound status table from LLM context because character name is missing session_id=%s table_id=%s character_mount_id=%s character_id=%s",
                table.get("session_id"),
                table.get("id"),
                mount.character_mount_id if mount is not None else None,
                mount.character_id if mount is not None else None,
            )
            continue
        table["context_description"] = str(table.get("description") or "").strip() or _DEFAULT_DESCRIPTION
        table["character_name"] = character_name
        context_rows = _context_rows(table)
        table["context_rows"] = context_rows
        table["has_llm_writable_rows"] = any(
            row["update_frequency"] in {
                STATUS_UPDATE_FREQUENCY_REALTIME,
                STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
            }
            for row in context_rows
        )
        prepared.append(table)
    return prepared


def render_status_tables_context(tables: Iterable[dict[str, object]]) -> str:
    prepared = prepare_status_context_tables(tables)
    if not prepared:
        return ""
    return render_jinja_template("modules/status_tables.jinja", status_tables=prepared)


def _character_name(table: dict[str, object]) -> str | object | None:
    if str(table.get("origin") or "") != STATUS_ORIGIN_TEMPLATE_COPY:
        return None
    mount = parse_session_status_metadata(
        str(table.get("metadata_json") or "{}")
    ).story_mount
    if mount is None:
        return None

    name = str(mount.character_name or "").strip()
    if name:
        return name
    if mount.character_id is not None or mount.character_mount_id is not None:
        return _UNRESOLVED_CHARACTER
    return None


def _context_rows(table: dict[str, object]) -> list[dict[str, object]]:
    raw_document = table.get("document")
    rows = raw_document.get("rows") if isinstance(raw_document, dict) else None
    if not isinstance(rows, list):
        legacy_rows = table.get("rows")
        if not isinstance(legacy_rows, list):
            return []
        return [
            {
                "key": str(row[0]),
                "value": str(row[1]) if len(row) > 1 else "",
                "update_frequency": STATUS_UPDATE_FREQUENCY_REALTIME,
                "update_rule": "",
            }
            for row in legacy_rows
            if isinstance(row, (list, tuple)) and row and str(row[0])
        ]
    return [
        {
            "key": str(row.get("key", "")),
            "value": str(row.get("value", "")),
            "update_frequency": str(
                row.get(STATUS_ROW_UPDATE_FREQUENCY_KEY)
                or STATUS_UPDATE_FREQUENCY_REALTIME
            ),
            "update_rule": str(row.get(STATUS_ROW_UPDATE_RULE_KEY) or ""),
        }
        for row in rows
        if isinstance(row, dict) and str(row.get("key", ""))
    ]
