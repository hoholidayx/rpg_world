#!/usr/bin/env python3
"""Dependency-free structural precheck for a Story Pack v2 JSON file."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

PROJECT_SCHEMA_VERSION = "story-design-project/2.0"
AUTHORING_RULES_SCHEMA_VERSION = "story-authoring-rules/1.0"
AUTHORING_RULES_RELATIVE_PATH = "schemas/story-authoring-rules-v1.json"
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
OBJECTIVE_TAGS = {
    "kind:appearance",
    "kind:background",
    "kind:relationship",
    "kind:ability",
}
RESERVED_CHARACTER_TAGS = {
    *OBJECTIVE_TAGS,
    *PORTRAYAL_TAGS,
    "scope:npc_portrayal",
}
PORTRAYAL_PATTERN = re.compile(
    r"(性格|口头禅|说话(?:方式|语气|习惯)|行为倾向|"
    r"心理(?:活动|状态)|内心(?:想法|活动)|"
    r"\bpersonality\b|\bspeech pattern\b|\bbehavior tendency\b)",
    re.IGNORECASE,
)
STATUS_SCHEDULING_PATTERN = re.compile(
    r"(每.{0,10}(回合|轮|turn|分钟|小时|天)|延迟|延期更新|"
    r"定时|周期|defer(?:red)?|interval|read[\s_-]?only|"
    r"只读|手动更新|manual)",
    re.IGNORECASE,
)
PLAYER_CONTROL_PATTERN = re.compile(
    r"(玩家|用户|player|user).{0,8}"
    r"(已经|必须|决定|选择|答应|拒绝|接受|同意|"
    r"has|must|decides|chooses|agrees|refuses|accepts)",
    re.IGNORECASE,
)


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
                if tag.startswith(("kind:", "scope:"))
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


def authoring_diagnostics(
    value: dict[str, Any],
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    rules = {
        item["ruleId"]: item
        for item in catalog.get("diagnosticRules", [])
    }
    diagnostics: list[dict[str, Any]] = []

    def emit(rule_id: str, path: str) -> None:
        rule = rules.get(rule_id)
        if rule is None:
            return
        if "package" not in rule.get("profiles", []):
            return
        diagnostics.append({
            "ruleId": rule_id,
            "severity": rule["severity"],
            "path": path,
            "message": rule["message"],
            "suggestion": rule["suggestion"],
            "runtimeEffect": rule["runtimeEffect"],
        })

    story = value.get("story")
    if isinstance(story, dict):
        if not str(story.get("title", "")).strip():
            emit("package.story-title-required", "/story/title")
        if not str(story.get("storyPrompt", "")).strip():
            emit("quality.story-prompt-empty", "/story/storyPrompt")
        if len(str(story.get("summary", "")).strip()) > 240:
            emit("quality.story-summary-too-long", "/story/summary")
    target = value.get("target")
    if isinstance(target, dict):
        if not str(target.get("workspaceId", "")).strip():
            emit("package.workspace-required", "/target/workspaceId")
        if target.get("allowCreateWorkspace") is True:
            if not str(target.get("workspaceName", "")).strip():
                emit(
                    "package.workspace-name-required",
                    "/target/workspaceName",
                )
            if not str(target.get("workspaceRoot", "")).strip():
                emit(
                    "package.workspace-root-required",
                    "/target/workspaceRoot",
                )
    resources = value.get("resources")
    if not isinstance(resources, dict):
        return diagnostics
    if not resources.get("openings"):
        emit("quality.opening-missing", "/resources/openings")
    for character_index, character in enumerate(
        resources.get("characters", [])
    ):
        if not isinstance(character, dict):
            continue
        base = f"/resources/characters/{character_index}"
        if PORTRAYAL_PATTERN.search(
            str(character.get("description", ""))
        ):
            emit(
                "character.description-portrayal-leak",
                f"{base}/description",
            )
        for detail_index, detail in enumerate(character.get("details", [])):
            if not isinstance(detail, dict):
                continue
            tags = {
                tag for tag in detail.get("tags", [])
                if isinstance(tag, str)
            }
            has_objective = bool(tags.intersection(OBJECTIVE_TAGS))
            has_portrayal = bool(tags.intersection(PORTRAYAL_TAGS))
            path = f"{base}/details/{detail_index}/tags"
            if has_objective and has_portrayal:
                emit("character.detail-mixed-kinds", path)
            if str(detail.get("content", "")).strip() and not (
                has_objective or has_portrayal
            ):
                emit("character.detail-kind-missing", path)
    for table_index, table in enumerate(
        resources.get("statusTables", [])
    ):
        if not isinstance(table, dict):
            continue
        for row_index, row in enumerate(table.get("rows", [])):
            if not isinstance(row, dict):
                continue
            base = (
                f"/resources/statusTables/{table_index}/rows/{row_index}"
            )
            update_rule = str(row.get("updateRule", ""))
            if update_rule and STATUS_SCHEDULING_PATTERN.search(update_rule):
                emit("status.update-rule-scheduling", f"{base}/updateRule")
            if table.get("statusKind") == "scene" and row.get("key") == "时间":
                year_match = re.search(
                    r"第\s*(\d+)\s*年",
                    str(row.get("value", "")),
                )
                if year_match and int(year_match.group(1)) < 1000:
                    emit("status.scene-placeholder-year", f"{base}/value")
    schedule = resources.get("plotSchedule", {})
    if isinstance(schedule, dict):
        for event_index, event in enumerate(schedule.get("events", [])):
            if not isinstance(event, dict):
                continue
            base = f"/resources/plotSchedule/events/{event_index}"
            hint = str(event.get("suitabilityHint", "")).strip()
            if event.get("dispatchMode", "soft") == "soft" and not hint:
                emit("plot.soft-event-hint-empty", f"{base}/suitabilityHint")
            if event.get("dispatchMode") == "forced" and hint:
                emit(
                    "plot.forced-event-unused-hint",
                    f"{base}/suitabilityHint",
                )
            if not str(event.get("description", "")).strip():
                emit("plot.event-description-empty", f"{base}/description")
            directive = re.sub(
                r"(不得|不要|不可|避免)替玩家",
                "",
                str(event.get("directive", "")),
            )
            if PLAYER_CONTROL_PATTERN.search(directive):
                emit("plot.directive-controls-player", f"{base}/directive")
    for lore_index, entry in enumerate(resources.get("lorebook", [])):
        if isinstance(entry, dict) and not str(
            entry.get("content", "")
        ).strip():
            emit(
                "lorebook.content-empty",
                f"/resources/lorebook/{lore_index}/content",
            )
    for style_index, style in enumerate(
        resources.get("narrativeStyles", [])
    ):
        if isinstance(style, dict) and not str(
            style.get("prompt", "")
        ).strip():
            emit(
                "composer.style-prompt-empty",
                f"/resources/narrativeStyles/{style_index}/prompt",
            )
    known_refs = _known_stable_ids(value)
    for visual_index, visual in enumerate(
        resources.get("visualCatalog", [])
    ):
        if not isinstance(visual, dict):
            continue
        base = f"/resources/visualCatalog/{visual_index}"
        if not visual.get("visualAnchors"):
            emit("visual.anchors-empty", f"{base}/visualAnchors")
        for ref_index, reference in enumerate(
            visual.get("subjectRefs", [])
        ):
            if isinstance(reference, str) and reference not in known_refs:
                emit(
                    "visual.subject-ref-unresolved",
                    f"{base}/subjectRefs/{ref_index}",
                )
    return sorted(
        diagnostics,
        key=lambda item: (
            0 if item["severity"] == "error" else 1,
            item["path"],
            item["ruleId"],
        ),
    )


def _known_stable_ids(value: dict[str, Any]) -> set[str]:
    resources = value.get("resources", {})
    if not isinstance(resources, dict):
        return set()
    story = value.get("story", {})
    result = {
        str(story.get("stableId"))
        for _ in [0]
        if isinstance(story, dict) and story.get("stableId")
    }
    for key in (
        "openings",
        "characters",
        "lorebook",
        "statusTables",
        "narrativeStyles",
        "quickReplies",
        "visualCatalog",
    ):
        for item in resources.get(key, []):
            if isinstance(item, dict) and item.get("stableId"):
                result.add(str(item["stableId"]))
            if key == "characters" and isinstance(item, dict):
                for detail in item.get("details", []):
                    if isinstance(detail, dict) and detail.get("stableId"):
                        result.add(str(detail["stableId"]))
    schedule = resources.get("plotSchedule", {})
    if isinstance(schedule, dict):
        for key in ("pools", "events", "outlines"):
            for item in schedule.get(key, []):
                if isinstance(item, dict) and item.get("stableId"):
                    result.add(str(item["stableId"]))
                if key == "outlines" and isinstance(item, dict):
                    for node in item.get("nodes", []):
                        if isinstance(node, dict) and node.get("stableId"):
                            result.add(str(node["stableId"]))
    return result


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _project_path(root: Path, raw_path: object) -> Path:
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


def _load_authoring_catalog() -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[4]
    manifest = json.loads(
        (project_root / "design-project.json").read_text(encoding="utf-8")
    )
    if not isinstance(manifest, dict):
        raise TypeError("design-project.json must contain an object")
    if manifest.get("schemaVersion") != PROJECT_SCHEMA_VERSION:
        raise ValueError("unsupported DesignProject schemaVersion")
    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        raise TypeError("DesignProject paths must be an object")
    relative = str(
        paths.get("authoringRules", AUTHORING_RULES_RELATIVE_PATH)
    )
    path = _project_path(project_root, relative)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("authoring rule catalog must be an object")
    if value.get("schemaVersion") != AUTHORING_RULES_SCHEMA_VERSION:
        raise ValueError("unsupported authoring rule catalog schemaVersion")
    version = str(value.get("authoringRulesVersion", "")).strip()
    if not version:
        raise ValueError("authoringRulesVersion is missing")
    profiles = value.get("profiles")
    if not isinstance(profiles, dict) or "package" not in profiles:
        raise ValueError("authoring rule catalog has no package profile")
    declared_digest = value.get("catalogDigest")
    payload = dict(value)
    payload.pop("catalogDigest", None)
    if _digest(payload) != declared_digest:
        raise ValueError("authoring rule catalog digest is invalid")
    if version != manifest.get("authoringRulesVersion"):
        raise ValueError(
            "authoring rule catalog version differs from project manifest"
        )
    if declared_digest != manifest.get("authoringRulesDigest"):
        raise ValueError(
            "authoring rule catalog digest differs from project manifest"
        )
    declared_assets = manifest.get("authoringAssetDigests")
    if not isinstance(declared_assets, dict):
        raise TypeError("authoringAssetDigests is missing")
    expected_file_digest = declared_assets.get(relative)
    actual_file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_file_digest != actual_file_digest:
        raise ValueError(
            "authoring rule catalog file digest differs from project manifest"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack")
    args = parser.parse_args()
    path = Path(args.pack)
    value = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(value)
    catalog = _load_authoring_catalog()
    diagnostics = authoring_diagnostics(value, catalog)
    structural = [
        {
            "ruleId": "contract.structure",
            "severity": "error",
            "path": "/",
            "message": message,
            "suggestion": "按 Story Pack v2 Schema 修正后重新验证。",
            "runtimeEffect": "结构无效的 Story Pack 不允许预览或导入。",
        }
        for message in errors
    ]
    all_diagnostics = structural + diagnostics
    warnings = [
        f"{item['path']}: {item['message']}"
        for item in diagnostics
        if item["severity"] == "warning"
    ]
    print(json.dumps(
        {
            "valid": not errors
            and not any(
                item["severity"] == "error" for item in diagnostics
            ),
            "path": str(path),
            "profile": "package",
            "authoringRulesVersion": catalog["authoringRulesVersion"],
            "errors": errors,
            "warnings": warnings,
            "diagnostics": all_diagnostics,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return (
        0
        if not errors
        and not any(item["severity"] == "error" for item in diagnostics)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
