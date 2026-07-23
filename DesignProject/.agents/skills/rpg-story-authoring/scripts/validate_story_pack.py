#!/usr/bin/env python3
"""Dependency-free structural precheck for a Story Pack v1 JSON file."""

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


def validate(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["Story Pack root must be an object"]
    if value.get("schemaVersion") != "rpg-story-pack/1.0":
        errors.append("unsupported schemaVersion")
    if value.get("contractVersion") != "1.0":
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
        errors.append("Story Pack v1 applyPolicy must be merge/non-deleting")
    return errors


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
