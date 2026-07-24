#!/usr/bin/env python3
"""Dependency-free structural precheck for a Story Pack v2 JSON file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SECTIONS = {
    "story",
    "openings",
    "characters",
    "lorebook",
    "statusTables",
    "composer",
    "rpModules",
    "plotSchedule",
    "visualCatalog",
}
STATUS_ROW_FIELDS = {
    "key",
    "value",
    "runtimeKeyLocked",
    "updateRule",
    "metadata",
}
PORTRAYAL_TAGS = {
    "kind:personality",
    "kind:speech",
    "kind:behavior",
    "kind:psychology",
}
RESERVED_CHARACTER_TAGS = {
    "kind:appearance",
    "kind:background",
    "kind:relationship",
    "kind:ability",
    *PORTRAYAL_TAGS,
    "scope:npc_portrayal",
}


def validate(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["Story Pack root must be an object"]
    if value.get("schemaVersion") != "rpg-story-pack/2.0":
        errors.append("unsupported schemaVersion")
    if value.get("contractVersion") != "2.0":
        errors.append("unsupported contractVersion")
    for field in ("packId", "projectId", "storyStableId"):
        if not ID_RE.fullmatch(str(value.get(field, ""))):
            errors.append(f"invalid {field}")
    target = value.get("target")
    if not isinstance(target, dict) or not str(
        target.get("workspaceId", "")
    ).strip():
        errors.append("target.workspaceId is required")
    story = value.get("story")
    if not isinstance(story, dict) or not str(story.get("title", "")).strip():
        errors.append("story.title is required")
    sections = value.get("includedSections")
    if not isinstance(sections, list) or not sections:
        errors.append("includedSections must be a non-empty list")
    elif len(sections) != len(set(map(str, sections))):
        errors.append("includedSections contains duplicates")
    else:
        unknown = sorted(set(map(str, sections)).difference(SECTIONS))
        if unknown:
            errors.append(f"unknown includedSections: {unknown}")
    policy = value.get("applyPolicy")
    if policy != {"mode": "merge", "deleteMissing": False}:
        errors.append("Story Pack v2 applyPolicy must be merge/non-deleting")
    _validate_characters(value, errors)
    _validate_rp_modules(value, errors)
    _validate_status_tables(value, errors)
    return errors


def _validate_characters(value: dict[str, Any], errors: list[str]) -> None:
    resources = value.get("resources")
    if not isinstance(resources, dict):
        return
    characters = resources.get("characters", [])
    if not isinstance(characters, list):
        errors.append("resources.characters must be an array")
        return
    for character_index, character in enumerate(characters):
        path = f"characters[{character_index}]"
        if not isinstance(character, dict):
            errors.append(f"{path} must be an object")
            continue
        if "personality" in character or "content" in character:
            errors.append(
                f"{path} uses removed top-level personality/content fields"
            )
        if "description" in character and not isinstance(
            character["description"],
            str,
        ):
            errors.append(f"{path}.description must be a string")
        details = character.get("details", [])
        if not isinstance(details, list):
            errors.append(f"{path}.details must be an array")
            continue
        for detail_index, detail in enumerate(details):
            detail_path = f"{path}.details[{detail_index}]"
            if not isinstance(detail, dict):
                errors.append(f"{detail_path} must be an object")
                continue
            tags = detail.get("tags", [])
            if not isinstance(tags, list) or not all(
                isinstance(tag, str) for tag in tags
            ):
                errors.append(f"{detail_path}.tags must be a string array")
                continue
            normalized = {tag.strip() for tag in tags if tag.strip()}
            unsupported = sorted(
                tag
                for tag in normalized
                if (
                    tag.startswith("kind:") or tag.startswith("scope:")
                )
                and tag not in RESERVED_CHARACTER_TAGS
            )
            if unsupported:
                errors.append(
                    f"{detail_path}.tags has unsupported reserved tags: "
                    f"{unsupported}"
                )


def _validate_rp_modules(value: dict[str, Any], errors: list[str]) -> None:
    resources = value.get("resources")
    if not isinstance(resources, dict):
        return
    modules = resources.get("rpModules", [])
    if not isinstance(modules, list):
        errors.append("resources.rpModules must be an array")
        return
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            errors.append(f"rpModules[{index}] must be an object")
            continue
        if (
            module.get("moduleName") == "message_mode"
            and module.get("config", {}) != {}
        ):
            errors.append(f"rpModules[{index}].config must be empty")


def _validate_status_tables(value: dict[str, Any], errors: list[str]) -> None:
    resources = value.get("resources")
    if not isinstance(resources, dict):
        return
    tables = resources.get("statusTables", [])
    if not isinstance(tables, list):
        errors.append("resources.statusTables must be an array")
        return
    for table_index, table in enumerate(tables):
        if not isinstance(table, dict):
            errors.append(f"statusTables[{table_index}] must be an object")
            continue
        rows = table.get("rows", [])
        if not isinstance(rows, list):
            errors.append(f"statusTables[{table_index}].rows must be an array")
            continue
        for row_index, row in enumerate(rows):
            path = f"statusTables[{table_index}].rows[{row_index}]"
            if not isinstance(row, dict):
                errors.append(f"{path} must be an object")
                continue
            unknown = sorted(set(row).difference(STATUS_ROW_FIELDS))
            if unknown:
                errors.append(f"{path} has unsupported fields: {unknown}")
            if not isinstance(row.get("key"), str) or not row["key"].strip():
                errors.append(f"{path}.key is required")
            if "value" in row and not isinstance(row["value"], str):
                errors.append(f"{path}.value must be a string")
            if "runtimeKeyLocked" in row and not isinstance(
                row["runtimeKeyLocked"],
                bool,
            ):
                errors.append(f"{path}.runtimeKeyLocked must be a boolean")
            if "updateRule" in row and not isinstance(row["updateRule"], str):
                errors.append(f"{path}.updateRule must be a string")
            if "metadata" in row and not isinstance(row["metadata"], dict):
                errors.append(f"{path}.metadata must be an object")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack")
    args = parser.parse_args()
    path = Path(args.pack)
    value = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(value)
    print(json.dumps(
        {"valid": not errors, "path": str(path), "errors": errors},
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
