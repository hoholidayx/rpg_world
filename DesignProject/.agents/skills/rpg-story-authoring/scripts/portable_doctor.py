#!/usr/bin/env python3
"""Read-only, dependency-free integrity check for a moved DesignProject."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def check(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if (root / ".design-transaction.json").is_file():
        errors.append(
            "an interrupted design commit journal exists; start "
            "rpg-world-mcp once to recover it before continuing"
        )
    manifest_path = root / "design-project.json"
    try:
        manifest = load(manifest_path)
    except Exception as exc:
        return {"healthy": False, "errors": [str(exc)], "warnings": []}
    if manifest.get("schemaVersion") != "story-design-project/2.0":
        errors.append(
            "unsupported DesignProject schemaVersion; v1 projects must be "
            "re-created as v2 because no converter is provided"
        )
    if manifest.get("contractVersion") != "2.0":
        errors.append("unsupported DesignProject contractVersion")
    for key, raw in manifest.get("paths", {}).items():
        value = Path(str(raw))
        if value.is_absolute() or ".." in value.parts:
            errors.append(f"non-portable path {key}: {raw}")
    try:
        current = load(root / str(manifest["paths"]["current"]))
        if current.get("schemaVersion") != "story-design/2.0":
            errors.append("unsupported current Story Design schemaVersion")
        if current.get("project", {}).get("projectId") != manifest.get(
            "projectId"
        ):
            errors.append("current projectId differs from manifest")
        if digest(current) != manifest.get("headDigest"):
            errors.append("current document digest differs from manifest")
        revision_path = (
            root
            / str(manifest["paths"]["revisions"])
            / f"{manifest['currentRevision']}.json"
        )
        revision = load(revision_path)
        if revision.get("documentDigest") != manifest.get("headDigest"):
            errors.append("current revision digest differs from manifest")
        if digest(revision.get("document")) != revision.get("documentDigest"):
            errors.append("current revision document is corrupt")
    except Exception as exc:
        errors.append(str(exc))
    try:
        contract = load(root / "schemas/rpg-mcp-contract-v2.json")
        if contract.get("schemaVersion") != "rpg-mcp-contract/2.0":
            errors.append("unsupported MCP contract schemaVersion")
        if digest(contract) != manifest.get("contractDigest"):
            errors.append("MCP contract digest differs from manifest")
    except Exception as exc:
        errors.append(str(exc))
    if not (root / ".codex" / "config.toml").is_file():
        warnings.append(".codex/config.toml is missing")
    if not (
        root / ".agents" / "skills" / "rpg-story-authoring" / "SKILL.md"
    ).is_file():
        errors.append("workspace Story Authoring Skill is missing")
    return {
        "healthy": not errors,
        "projectRoot": str(root),
        "currentRevision": manifest.get("currentRevision"),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        default=".",
        help="DesignProject root (default: current directory)",
    )
    args = parser.parse_args()
    result = check(Path(args.project_root).expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
