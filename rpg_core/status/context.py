"""Shared preparation and rendering for normal status-table context."""

from __future__ import annotations

import json
import logging
from typing import Iterable

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
