"""Generate neutral checked-in schemas and the initial portable revision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

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
    ("story_design_patch", False, False),
    ("story_design_create_checkpoint", False, False),
    ("story_design_list_history", True, False),
    ("story_design_diff_revisions", True, False),
    ("story_design_restore_revision", False, True),
    ("story_design_validate", True, False),
    ("story_design_build_pack", False, False),
    ("story_design_doctor", True, False),
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
    schemas = root / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    design_schema = StoryDesignDocument.model_json_schema(
        by_alias=True,
        mode="validation",
    )
    design_schema["$id"] = "story-design-v1.schema.json"
    design_schema["title"] = "Portable Story Design v1"
    pack_schema = StoryPack.model_json_schema(
        by_alias=True,
        mode="validation",
    )
    pack_schema["$id"] = "story-pack-v1.schema.json"
    pack_schema["title"] = "RPG World Story Pack v1"
    _write_json(schemas / "story-design-v1.schema.json", design_schema)
    _write_json(schemas / "story-pack-v1.schema.json", pack_schema)

    contract = {
        "schemaVersion": "rpg-mcp-contract/1.0",
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
    }
    contract_path = schemas / "rpg-mcp-contract-v1.json"
    _write_json(contract_path, contract)
    _initialize_revision(
        root,
        contract_digest=_digest(contract),
    )


def _initialize_revision(root: Path, *, contract_digest: str) -> None:
    manifest_path = root / "design-project.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("design-project.json must contain one object")
        manifest["contractVersion"] = CONTRACT_VERSION
        manifest["contractDigest"] = contract_digest
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
        },
    }
    _write_json(manifest_path, manifest)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root")
    args = parser.parse_args()
    generate(Path(args.project_root).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
