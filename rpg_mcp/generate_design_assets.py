"""Generate neutral v2 schemas and initialize a new portable revision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from rpg_mcp.authoring_rules import (
    AUTHORING_RULES_RELATIVE_PATH,
    AUTHORING_RULES_VERSION,
    authoring_rules_catalog,
    enrich_schema,
    render_contract_reference,
    render_reference_files,
    render_skill_document,
)
from rpg_mcp.contracts import (
    CONTRACT_VERSION,
    PROJECT_SCHEMA_VERSION,
    StoryDesignDocument,
    StoryPack,
    canonical_json,
)

DESIGN_TOOLS = (
    ("story_design_get_project", True, False),
    ("story_design_get_resume_context", True, False),
    ("story_design_get_section", True, False),
    ("story_design_get_authoring_rules", True, False),
    ("story_design_patch", False, False),
    ("story_design_create_checkpoint", False, False),
    ("story_design_list_history", True, False),
    ("story_design_diff_revisions", True, False),
    ("story_design_restore_revision", False, True),
    ("story_design_validate", True, False),
    ("story_design_build_pack", False, False),
    ("story_design_doctor", True, False),
    ("story_design_preview_authoring_rules_refresh", True, False),
    ("story_design_apply_authoring_rules_refresh", False, True),
)

RUNTIME_TOOLS = (
    ("rpg_list_workspaces", True, False),
    ("rpg_list_stories", True, False),
    ("rpg_search_story_resources", True, False),
    ("rpg_get_story_resource", True, False),
    ("rpg_validate_story_pack", True, False),
    ("rpg_preview_story_pack", False, False),
    ("rpg_apply_story_pack", False, True),
    ("rpg_preview_changes", False, False),
    ("rpg_apply_changes", False, True),
    ("rpg_export_story_snapshot", False, False),
    ("rpg_get_operation_result", True, False),
)

ALL_TOOLS = (
    ("story_design_compare_runtime", True, False),
    ("story_design_preview_runtime_sync", False, False),
    ("story_design_apply_runtime_sync", False, True),
    ("story_design_reconcile_from_runtime", False, True),
)


def _tool_contract(
    name: str,
    read_only: bool,
    destructive: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "openWorldHint": False,
        },
    }


def generate(root: Path) -> None:
    manifest_path = root / "design-project.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("design-project.json must contain one object")
        if manifest.get("schemaVersion") != PROJECT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported DesignProject schemaVersion: "
                f"{manifest.get('schemaVersion')!r}; v1 projects must be "
                "re-created as v2 because no converter is provided"
            )
    assets = build_managed_authoring_assets()
    _write_managed_assets(root, assets)
    metadata = managed_authoring_asset_metadata(assets)
    _initialize_revision(
        root,
        contract_digest=metadata["contractDigest"],
        authoring_rules_digest=metadata["authoringRulesDigest"],
        authoring_asset_digests=metadata["authoringAssetDigests"],
        authoring_assets_digest=metadata["authoringAssetsDigest"],
    )


def generate_schema_assets(root: Path) -> dict[str, Any]:
    """Write managed v2 authoring assets without mutating design revisions."""

    assets = build_managed_authoring_assets()
    _write_managed_assets(root, assets)
    return json.loads(assets["schemas/rpg-mcp-contract-v2.json"])


def build_managed_authoring_assets() -> dict[str, str]:
    """Build deterministic portable assets from the authoring rule source."""

    catalog = authoring_rules_catalog()
    design_schema = StoryDesignDocument.model_json_schema(
        by_alias=True,
        mode="validation",
    )
    design_schema["$id"] = "story-design-v2.schema.json"
    design_schema["title"] = "Portable Story Design v2"
    design_schema = enrich_schema(
        design_schema,
        root_model="StoryDesignDocument",
        catalog=catalog,
    )
    pack_schema = StoryPack.model_json_schema(
        by_alias=True,
        mode="validation",
    )
    pack_schema["$id"] = "story-pack-v2.schema.json"
    pack_schema["title"] = "RPG World Story Pack v2"
    pack_schema = enrich_schema(
        pack_schema,
        root_model="StoryPack",
        catalog=catalog,
    )

    contract = {
        "schemaVersion": "rpg-mcp-contract/2.0",
        "contractVersion": CONTRACT_VERSION,
        "command": "rpg-world-mcp",
        "defaultTransport": "stdio",
        "inspectorTransport": {
            "type": "streamable-http",
            "loopbackOnly": True,
        },
        "modes": {
            "design": {
                "importsRpgRuntime": False,
                "tools": [
                    _tool_contract(*item) for item in DESIGN_TOOLS
                ],
            },
            "runtime": {
                "importsRpgRuntime": True,
                "tools": [
                    _tool_contract(*item) for item in RUNTIME_TOOLS
                ],
            },
            "all": {
                "importsRpgRuntime": True,
                "includes": ["design", "runtime"],
                "tools": [
                    _tool_contract(*item) for item in ALL_TOOLS
                ],
            },
        },
        "confirmation": {
            "previewAndApplyAreSeparateTools": True,
            "applyUsesOpaqueOperationId": True,
            "booleanConfirmationArgumentsForbidden": True,
        },
        "runtimePolicy": {
            "oneStoryPerPack": True,
            "mergeOnly": True,
            "deleteMissing": False,
            "visualCatalogIsArchiveOnly": True,
            "createsSessions": False,
        },
        "characterCards": {
            "topLevelFields": ["name", "description"],
            "objectiveDetailTags": [
                "kind:appearance",
                "kind:background",
                "kind:relationship",
                "kind:ability",
            ],
            "portrayalDetailTags": [
                "kind:personality",
                "kind:speech",
                "kind:behavior",
                "kind:psychology",
            ],
            "portrayalScopeTag": "scope:npc_portrayal",
        },
        "messageMode": {
            "moduleName": "message_mode",
            "modes": ["neutral", "ic", "ooc", "gm"],
            "defaultMode": "neutral",
            "promptsAreCodeOwned": True,
            "workspaceConfiguration": False,
        },
        "authoringRules": {
            "version": AUTHORING_RULES_VERSION,
            "digest": catalog["catalogDigest"],
            "path": AUTHORING_RULES_RELATIVE_PATH,
            "profiles": ["draft", "package"],
            "structuredDiagnostics": [
                "ruleId",
                "severity",
                "path",
                "message",
                "suggestion",
                "runtimeEffect",
            ],
            "managedAssetRefresh": {
                "previewAndApplyAreSeparateTools": True,
                "changesDesignRevision": False,
                "changesStoryPacks": False,
                "changesRuntimeIntegration": False,
            },
        },
    }
    assets = {
        "schemas/story-design-v2.schema.json": _json_text(design_schema),
        "schemas/story-pack-v2.schema.json": _json_text(pack_schema),
        "schemas/rpg-mcp-contract-v2.json": _json_text(contract),
        AUTHORING_RULES_RELATIVE_PATH: _json_text(catalog),
        (
            ".agents/skills/rpg-story-authoring/SKILL.md"
        ): render_skill_document(catalog),
        (
            ".agents/skills/rpg-story-authoring/references/"
            "story-design-contract.md"
        ): render_contract_reference(catalog),
    }
    for filename, content in render_reference_files(catalog).items():
        assets[
            ".agents/skills/rpg-story-authoring/references/" + filename
        ] = content
    return dict(sorted(assets.items()))


def managed_authoring_asset_metadata(
    assets: dict[str, str] | None = None,
) -> dict[str, Any]:
    values = assets or build_managed_authoring_assets()
    asset_digests = {
        path: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for path, content in sorted(values.items())
    }
    contract = json.loads(values["schemas/rpg-mcp-contract-v2.json"])
    catalog = json.loads(values[AUTHORING_RULES_RELATIVE_PATH])
    return {
        "contractDigest": _digest(contract),
        "authoringRulesVersion": AUTHORING_RULES_VERSION,
        "authoringRulesDigest": catalog["catalogDigest"],
        "authoringAssetDigests": asset_digests,
        "authoringAssetsDigest": _digest(asset_digests),
    }


def _write_managed_assets(root: Path, assets: dict[str, str]) -> None:
    for relative, content in assets.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _initialize_revision(
    root: Path,
    *,
    contract_digest: str,
    authoring_rules_digest: str,
    authoring_asset_digests: dict[str, str],
    authoring_assets_digest: str,
) -> None:
    manifest_path = root / "design-project.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("design-project.json must contain one object")
        if manifest.get("schemaVersion") != PROJECT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported DesignProject schemaVersion: "
                f"{manifest.get('schemaVersion')!r}; v1 projects must be "
                "re-created as v2 because no converter is provided"
            )
        manifest["contractVersion"] = CONTRACT_VERSION
        manifest["contractDigest"] = contract_digest
        manifest["authoringRulesVersion"] = AUTHORING_RULES_VERSION
        manifest["authoringRulesDigest"] = authoring_rules_digest
        manifest["authoringAssetDigests"] = authoring_asset_digests
        manifest["authoringAssetsDigest"] = authoring_assets_digest
        paths = manifest.setdefault("paths", {})
        paths["authoringRules"] = AUTHORING_RULES_RELATIVE_PATH
        _write_json(manifest_path, manifest)
        return
    current_path = root / "design" / "current.json"
    document = StoryDesignDocument.model_validate_json(
        current_path.read_text(encoding="utf-8")
    ).model_dump(by_alias=True)
    document_digest = _digest(document)
    revision_id = "r000001"
    created_at = "2026-07-23T00:00:00Z"
    revision = {
        "schemaVersion": PROJECT_SCHEMA_VERSION,
        "revisionId": revision_id,
        "revisionNumber": 1,
        "parentRevision": None,
        "parentDigest": None,
        "documentDigest": document_digest,
        "createdAt": created_at,
        "reason": "Initialize portable Story design project",
        "document": document,
    }
    revision_path = root / "design" / "revisions" / f"{revision_id}.json"
    revision_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(revision_path, revision)
    manifest = {
        "schemaVersion": PROJECT_SCHEMA_VERSION,
        "contractVersion": CONTRACT_VERSION,
        "contractDigest": contract_digest,
        "authoringRulesVersion": AUTHORING_RULES_VERSION,
        "authoringRulesDigest": authoring_rules_digest,
        "authoringAssetDigests": authoring_asset_digests,
        "authoringAssetsDigest": authoring_assets_digest,
        "projectId": document["project"]["projectId"],
        "name": document["project"]["name"],
        "currentRevision": revision_id,
        "headDigest": document_digest,
        "createdAt": created_at,
        "updatedAt": created_at,
        "paths": {
            "current": "design/current.json",
            "revisions": "design/revisions",
            "checkpoints": "design/checkpoints",
            "sources": "design/sources",
            "storyPacks": "artifacts/story-packs",
            "snapshots": "artifacts/snapshots",
            "integration": "integrations/rpg-world.json",
            "reports": "reports",
            "authoringRules": AUTHORING_RULES_RELATIVE_PATH,
        },
    }
    _write_json(manifest_path, manifest)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(value), encoding="utf-8")


def _json_text(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root")
    args = parser.parse_args()
    generate(Path(args.project_root).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
