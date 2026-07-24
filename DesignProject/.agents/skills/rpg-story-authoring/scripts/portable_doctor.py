#!/usr/bin/env python3
"""Read-only, dependency-free integrity check for a moved DesignProject."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

PROJECT_SCHEMA_VERSION = "story-design-project/2.0"
CONTRACT_VERSION = "2.0"
AUTHORING_RULES_SCHEMA_VERSION = "story-authoring-rules/1.0"
REVISION_RE = re.compile(r"^r[0-9]{6}$")
MANAGED_AUTHORING_ASSET_PATHS = frozenset({
    ".agents/skills/rpg-story-authoring/SKILL.md",
    (
        ".agents/skills/rpg-story-authoring/references/"
        "fields-characters-lorebook.md"
    ),
    (
        ".agents/skills/rpg-story-authoring/references/"
        "fields-plot-rp-composer.md"
    ),
    (
        ".agents/skills/rpg-story-authoring/references/"
        "fields-project-story.md"
    ),
    (
        ".agents/skills/rpg-story-authoring/references/"
        "fields-status-scene.md"
    ),
    (
        ".agents/skills/rpg-story-authoring/references/"
        "fields-visual-workflow.md"
    ),
    (
        ".agents/skills/rpg-story-authoring/references/"
        "story-design-contract.md"
    ),
    "schemas/rpg-mcp-contract-v2.json",
    "schemas/story-authoring-rules-v1.json",
    "schemas/story-design-v2.schema.json",
    "schemas/story-pack-v2.schema.json",
})


def digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def project_path(root: Path, raw_path: object) -> Path:
    candidate = Path(str(raw_path))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"non-portable project path: {raw_path}")
    resolved_root = root.resolve()
    try:
        resolved = (resolved_root / candidate).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(
            f"project path cannot be resolved safely: {raw_path}"
        ) from exc
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"project path escapes the DesignProject root: {raw_path}"
        ) from exc
    return resolved


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
    if manifest.get("schemaVersion") != PROJECT_SCHEMA_VERSION:
        errors.append(
            "unsupported DesignProject schemaVersion; v1 projects must be "
            "re-created as v2 because no converter is provided"
        )
    if manifest.get("contractVersion") != CONTRACT_VERSION:
        errors.append("unsupported DesignProject contractVersion")
    authoring_rules_version = str(
        manifest.get("authoringRulesVersion", "")
    )
    if not authoring_rules_version:
        errors.append("DesignProject authoringRulesVersion is missing")
    raw_paths = manifest.get("paths")
    if isinstance(raw_paths, dict):
        paths = raw_paths
    else:
        paths = {}
        errors.append("DesignProject paths must be an object")
    for key, raw in paths.items():
        try:
            project_path(root, raw)
        except ValueError:
            errors.append(f"non-portable path {key}: {raw}")
    try:
        current = load(project_path(root, paths["current"]))
        if current.get("schemaVersion") != "story-design/2.0":
            errors.append("unsupported current Story Design schemaVersion")
        if current.get("project", {}).get("projectId") != manifest.get(
            "projectId"
        ):
            errors.append("current projectId differs from manifest")
        if digest(current) != manifest.get("headDigest"):
            errors.append("current document digest differs from manifest")
        revision_id = str(manifest.get("currentRevision", ""))
        if REVISION_RE.fullmatch(revision_id) is None:
            raise ValueError("currentRevision must use rNNNNNN")
        revision_path = project_path(
            root,
            Path(str(paths["revisions"])) / f"{revision_id}.json",
        )
        revision = load(revision_path)
        if revision.get("documentDigest") != manifest.get("headDigest"):
            errors.append("current revision digest differs from manifest")
        if digest(revision.get("document")) != revision.get("documentDigest"):
            errors.append("current revision document is corrupt")
    except Exception as exc:
        errors.append(str(exc))
    try:
        contract = load(
            project_path(root, "schemas/rpg-mcp-contract-v2.json")
        )
        if contract.get("schemaVersion") != "rpg-mcp-contract/2.0":
            errors.append("unsupported MCP contract schemaVersion")
        if digest(contract) != manifest.get("contractDigest"):
            errors.append("MCP contract digest differs from manifest")
        rule_contract = contract.get("authoringRules", {})
        if rule_contract.get("version") != authoring_rules_version:
            errors.append("MCP contract authoring rule version differs")
        if rule_contract.get("digest") != manifest.get(
            "authoringRulesDigest"
        ):
            errors.append("MCP contract authoring rule digest differs")
    except Exception as exc:
        errors.append(str(exc))
    try:
        rule_path = project_path(
            root,
            paths.get(
                "authoringRules",
                "schemas/story-authoring-rules-v1.json",
            ),
        )
        catalog = load(rule_path)
        if catalog.get("schemaVersion") != AUTHORING_RULES_SCHEMA_VERSION:
            errors.append("unsupported authoring rule catalog schemaVersion")
        if catalog.get("authoringRulesVersion") != authoring_rules_version:
            errors.append("authoring rule catalog version differs")
        declared_catalog_digest = catalog.get("catalogDigest")
        catalog_payload = dict(catalog)
        catalog_payload.pop("catalogDigest", None)
        if digest(catalog_payload) != declared_catalog_digest:
            errors.append("authoring rule catalog digest is invalid")
        if declared_catalog_digest != manifest.get("authoringRulesDigest"):
            errors.append("authoring rule catalog digest differs from manifest")
        for schema_name in (
            "story-design-v2.schema.json",
            "story-pack-v2.schema.json",
        ):
            schema = load(project_path(root, Path("schemas") / schema_name))
            if schema.get("x-authoringRulesVersion") != (
                authoring_rules_version
            ):
                errors.append(
                    f"{schema_name} authoring rule version is stale"
                )
            if schema.get("x-authoringRulesDigest") != (
                declared_catalog_digest
            ):
                errors.append(
                    f"{schema_name} authoring rule digest differs"
                )
    except Exception as exc:
        errors.append(str(exc))
    try:
        declared_assets = manifest.get("authoringAssetDigests")
        if not isinstance(declared_assets, dict) or not declared_assets:
            errors.append("authoringAssetDigests is missing")
        else:
            declared_paths = {str(path) for path in declared_assets}
            missing_paths = sorted(
                MANAGED_AUTHORING_ASSET_PATHS - declared_paths
            )
            unexpected_paths = sorted(
                declared_paths - MANAGED_AUTHORING_ASSET_PATHS
            )
            if missing_paths:
                errors.append(
                    "authoringAssetDigests omits managed assets: "
                    f"{missing_paths}"
                )
            if unexpected_paths:
                errors.append(
                    "authoringAssetDigests contains unexpected managed assets: "
                    f"{unexpected_paths}"
                )
            for raw_path, expected_digest in declared_assets.items():
                try:
                    path = project_path(root, raw_path)
                except ValueError:
                    errors.append(
                        f"non-portable managed authoring asset: {raw_path}"
                    )
                    continue
                actual_digest = file_digest(path)
                if actual_digest != expected_digest:
                    errors.append(
                        f"managed authoring asset digest mismatch: {raw_path}"
                    )
            if digest(declared_assets) != manifest.get(
                "authoringAssetsDigest"
            ):
                errors.append(
                    "authoringAssetsDigest differs from managed asset map"
                )
    except Exception as exc:
        errors.append(str(exc))
    try:
        skill_path = project_path(
            root,
            ".agents/skills/rpg-story-authoring/SKILL.md",
        )
        skill = skill_path.read_text(encoding="utf-8")
        if (
            f"authoring-rules-version: {authoring_rules_version}"
            not in skill
            or (
                "authoring-rules-digest: "
                + str(manifest.get("authoringRulesDigest"))
            )
            not in skill
        ):
            errors.append("workspace Skill authoring rule marker is stale")
    except Exception as exc:
        errors.append(str(exc))
    try:
        if not project_path(root, ".codex/config.toml").is_file():
            warnings.append(".codex/config.toml is missing")
    except ValueError as exc:
        errors.append(str(exc))
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
