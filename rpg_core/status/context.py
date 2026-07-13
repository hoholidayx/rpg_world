"""Shared preparation and rendering for normal status-table context."""

from __future__ import annotations

import json
import logging
from typing import Iterable

from rpg_data.models import (
    STATUS_ROW_UPDATE_FREQUENCY_KEY,
    STATUS_ROW_UPDATE_RULE_KEY,
    STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
    STATUS_UPDATE_FREQUENCY_REALTIME,
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
            metadata = _metadata_object(table.get("metadata_json"))
            mount = metadata.get("storyStatusMount")
            logger.warning(
                "excluded character-bound status table from LLM context because character name is missing session_id=%s table_id=%s character_mount_id=%s character_id=%s",
                table.get("session_id"),
                table.get("id"),
                mount.get("characterMountId") if isinstance(mount, dict) else None,
                mount.get("characterId") if isinstance(mount, dict) else None,
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
    if str(table.get("origin") or "") != "template_copy":
        return None
    metadata = _metadata_object(table.get("metadata_json"))
    mount = metadata.get("storyStatusMount")
    if not isinstance(mount, dict):
        return None

    name = str(mount.get("characterName") or "").strip()
    if name:
        return name
    if (
        mount.get("characterId") is not None
        or mount.get("characterMountId") is not None
    ):
        return _UNRESOLVED_CHARACTER
    return None


def _metadata_object(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
