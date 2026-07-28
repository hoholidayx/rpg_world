#!/usr/bin/env python3
"""Read-only local web viewer for one portable Story DesignProject."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import mimetypes
import re
import threading
import time
import webbrowser
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

VIEWER_VERSION = "story-design-viewer/2.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
MAX_JSON_BYTES = 32 * 1024 * 1024
REVISION_RE = re.compile(r"^r[0-9]{6}$")
PACK_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.json$")
SCHEMA_FILES = {
    "story-design": "story-design-v2.schema.json",
    "story-pack": "story-pack-v2.schema.json",
}
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/styles.css": "styles.css",
    "/app.js": "app.js",
}


class ViewerError(RuntimeError):
    """Base error returned by the read-only viewer."""


class ViewerNotFoundError(ViewerError):
    """Requested project resource does not exist."""


class ViewerValidationError(ViewerError):
    """Requested project resource or identifier is invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except FileNotFoundError as exc:
        raise ViewerNotFoundError(f"file not found: {path.name}") from exc
    if size > MAX_JSON_BYTES:
        raise ViewerValidationError(
            f"JSON file exceeds the {MAX_JSON_BYTES} byte viewer limit"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ViewerValidationError(
            f"cannot read valid JSON from {path.name}"
        ) from exc
    if not isinstance(value, dict):
        raise ViewerValidationError(f"{path.name} must contain one JSON object")
    return value


def _json_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _pretty_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


class ProjectReader:
    """Read one DesignProject without importing RPG World modules."""

    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve()
        self.viewer_root = Path(__file__).resolve().parent
        self.manifest_path = self.root / "design-project.json"
        if not self.manifest_path.is_file():
            raise FileNotFoundError(
                f"design-project.json not found under {self.root}"
            )

    def manifest(self) -> dict[str, Any]:
        manifest = _read_json(self.manifest_path)
        if manifest.get("schemaVersion") != "story-design-project/2.0":
            raise ViewerValidationError(
                "unsupported or missing DesignProject schemaVersion"
            )
        revision_id = str(manifest.get("currentRevision", ""))
        if REVISION_RE.fullmatch(revision_id) is None:
            raise ViewerValidationError(
                "DesignProject currentRevision is invalid"
            )
        return manifest

    def project(self) -> dict[str, Any]:
        manifest = self.manifest()
        return {
            "viewerVersion": VIEWER_VERSION,
            "project": manifest,
            "live": self.snapshot(manifest=manifest),
        }

    def snapshot(
        self,
        *,
        manifest: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = dict(manifest) if manifest is not None else self.manifest()
        return {
            "currentRevision": current.get("currentRevision"),
            "headDigest": current.get("headDigest"),
            "updatedAt": current.get("updatedAt"),
            "authoringAssetsDigest": current.get(
                "authoringAssetsDigest"
            ),
            "packSignature": self.story_pack_signature(),
        }

    def revision(self, revision_id: str) -> dict[str, Any]:
        normalized = str(revision_id or "").strip()
        if REVISION_RE.fullmatch(normalized) is None:
            raise ViewerValidationError("revision id must use rNNNNNN")
        path = self._project_path(
            str(
                Path(
                    self._manifest_path("revisions", "design/revisions")
                )
                / f"{normalized}.json"
            )
        )
        value = _read_json(path)
        if value.get("revisionId") != normalized:
            raise ViewerValidationError(
                f"revision file identity does not match {normalized}"
            )
        if not isinstance(value.get("document"), dict):
            raise ViewerValidationError(
                f"revision {normalized} has no document object"
            )
        return value

    def history(self) -> dict[str, Any]:
        manifest = self.manifest()
        revision_dir = self._project_path(
            self._manifest_path("revisions", "design/revisions")
        )
        rows: list[dict[str, Any]] = []
        for path in revision_dir.glob("r*.json"):
            try:
                safe_path = self._project_path(
                    path.relative_to(self.root).as_posix()
                )
                revision = _read_json(safe_path)
            except ViewerError:
                continue
            revision_id = str(revision.get("revisionId", ""))
            if REVISION_RE.fullmatch(revision_id) is None:
                continue
            rows.append({
                key: revision.get(key)
                for key in (
                    "revisionId",
                    "revisionNumber",
                    "parentRevision",
                    "parentDigest",
                    "documentDigest",
                    "createdAt",
                    "reason",
                )
            })
        rows.sort(
            key=lambda item: int(item.get("revisionNumber") or 0),
            reverse=True,
        )

        checkpoints_dir = self._project_path(
            self._manifest_path("checkpoints", "design/checkpoints")
        )
        checkpoints: list[dict[str, Any]] = []
        if checkpoints_dir.is_dir():
            for path in sorted(checkpoints_dir.glob("*.json")):
                try:
                    safe_path = self._project_path(
                        path.relative_to(self.root).as_posix()
                    )
                    checkpoints.append(_read_json(safe_path))
                except ViewerError:
                    continue
        return {
            "currentRevision": manifest["currentRevision"],
            "headDigest": manifest.get("headDigest"),
            "revisions": rows[:200],
            "checkpoints": checkpoints,
        }

    def diff(self, from_revision: str, to_revision: str) -> dict[str, Any]:
        before = self.revision(from_revision)
        after = self.revision(to_revision)
        before_document = before["document"]
        after_document = after["document"]
        unified = "".join(difflib.unified_diff(
            _pretty_json(before_document).splitlines(keepends=True),
            _pretty_json(after_document).splitlines(keepends=True),
            fromfile=str(from_revision),
            tofile=str(to_revision),
        ))
        return {
            "fromRevision": from_revision,
            "toRevision": to_revision,
            "changed": before.get("documentDigest")
            != after.get("documentDigest"),
            "changedSections": _changed_sections(
                before_document,
                after_document,
            ),
            "unifiedDiff": unified,
        }

    def schema(self, schema_name: str) -> dict[str, Any]:
        filename = SCHEMA_FILES.get(schema_name)
        if filename is None:
            raise ViewerNotFoundError(f"unknown schema: {schema_name}")
        return _read_json(self.root / "schemas" / filename)

    def authoring_rules(self) -> dict[str, Any]:
        manifest = self.manifest()
        relative = self._manifest_path_from(
            manifest,
            "authoringRules",
            "schemas/story-authoring-rules-v1.json",
        )
        catalog = _read_json(self._project_path(relative))
        if catalog.get("authoringRulesVersion") != manifest.get(
            "authoringRulesVersion"
        ):
            raise ViewerValidationError(
                "authoringRulesVersion differs from project manifest"
            )
        declared_digest = catalog.get("catalogDigest")
        payload = dict(catalog)
        payload.pop("catalogDigest", None)
        if _json_digest(payload) != declared_digest:
            raise ViewerValidationError(
                "authoring rule catalog digest is invalid"
            )
        if declared_digest != manifest.get("authoringRulesDigest"):
            raise ViewerValidationError(
                "authoring rule catalog differs from project manifest"
            )
        return catalog

    def diagnostics(
        self,
        revision_id: str,
        *,
        profile: str,
    ) -> dict[str, Any]:
        normalized_profile = str(profile or "draft").strip().lower()
        if normalized_profile not in {"draft", "package"}:
            raise ViewerValidationError(
                "diagnostic profile must be draft or package"
            )
        revision = self.revision(revision_id)
        catalog = self.authoring_rules()
        diagnostics = _authoring_diagnostics(
            revision["document"],
            catalog,
            profile=normalized_profile,
        )
        errors = [
            item for item in diagnostics
            if item["severity"] == "error"
        ]
        warnings = [
            item for item in diagnostics
            if item["severity"] == "warning"
        ]
        return {
            "valid": not errors,
            "revision": revision_id,
            "profile": normalized_profile,
            "authoringRulesVersion": catalog["authoringRulesVersion"],
            "errors": errors,
            "warnings": warnings,
            "diagnostics": diagnostics,
        }

    def story_packs(self) -> dict[str, Any]:
        pack_dir = self._project_path(
            self._manifest_path("storyPacks", "artifacts/story-packs")
        )
        rows: list[dict[str, Any]] = []
        if pack_dir.is_dir():
            for path in sorted(pack_dir.glob("*.json"), reverse=True):
                if PACK_FILENAME_RE.fullmatch(path.name) is None:
                    continue
                try:
                    safe_path = self._project_path(
                        path.relative_to(self.root).as_posix()
                    )
                    pack = _read_json(safe_path)
                except ViewerError:
                    continue
                story = pack.get("story")
                if not isinstance(story, dict):
                    story = {}
                rows.append({
                    "filename": path.name,
                    "packId": pack.get("packId"),
                    "projectId": pack.get("projectId"),
                    "storyStableId": pack.get("storyStableId"),
                    "storyTitle": story.get("title"),
                    "sourceRevision": pack.get("sourceRevision"),
                    "sourceDigest": pack.get("sourceDigest"),
                    "generatedAt": pack.get("generatedAt"),
                    "includedSections": pack.get("includedSections", []),
                    "target": pack.get("target", {}),
                    "sizeBytes": safe_path.stat().st_size,
                })
        rows.sort(
            key=lambda item: str(item.get("generatedAt") or ""),
            reverse=True,
        )
        return {
            "signature": self.story_pack_signature(),
            "packs": rows,
        }

    def story_pack(self, filename: str) -> dict[str, Any]:
        normalized = str(filename or "").strip()
        if PACK_FILENAME_RE.fullmatch(normalized) is None:
            raise ViewerValidationError("invalid Story Pack filename")
        path = self._project_path(
            str(
                Path(
                    self._manifest_path(
                        "storyPacks",
                        "artifacts/story-packs",
                    )
                )
                / normalized
            )
        )
        return _read_json(path)

    def story_pack_signature(self) -> str:
        manifest = self.manifest() if self.manifest_path.is_file() else {}
        pack_dir = self._project_path(
            self._manifest_path_from(
                manifest,
                "storyPacks",
                "artifacts/story-packs",
            )
        )
        rows: list[tuple[str, int, int]] = []
        if pack_dir.is_dir():
            for path in sorted(pack_dir.glob("*.json")):
                if PACK_FILENAME_RE.fullmatch(path.name) is None:
                    continue
                try:
                    safe_path = self._project_path(
                        path.relative_to(self.root).as_posix()
                    )
                    stat = safe_path.stat()
                except (OSError, ViewerError):
                    continue
                rows.append((path.name, stat.st_mtime_ns, stat.st_size))
        return _json_digest(rows)

    def _manifest_path(self, name: str, default: str) -> str:
        return self._manifest_path_from(self.manifest(), name, default)

    @staticmethod
    def _manifest_path_from(
        manifest: Mapping[str, Any],
        name: str,
        default: str,
    ) -> str:
        paths = manifest.get("paths")
        if not isinstance(paths, Mapping):
            return default
        value = paths.get(name, default)
        return str(value or default)

    def _project_path(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute():
            raise ViewerValidationError(
                "DesignProject paths must remain relative"
            )
        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ViewerValidationError(
                "DesignProject path escapes the project root"
            ) from exc
        return resolved


def _changed_sections(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> list[dict[str, Any]]:
    names = sorted(set(before) | set(after))
    rows: list[dict[str, Any]] = []
    for name in names:
        left = before.get(name)
        right = after.get(name)
        if left == right:
            continue
        rows.append({
            "section": name,
            "beforeDigest": _json_digest(left),
            "afterDigest": _json_digest(right),
        })
    return rows


def _authoring_diagnostics(
    document: Mapping[str, Any],
    catalog: Mapping[str, Any],
    *,
    profile: str,
) -> list[dict[str, Any]]:
    rules = {
        str(item["ruleId"]): item
        for item in catalog.get("diagnosticRules", [])
    }
    output: list[dict[str, Any]] = []

    def emit(rule_id: str, path: str) -> None:
        rule = rules.get(rule_id)
        if rule is None:
            return
        if profile not in rule["profiles"]:
            return
        output.append({
            "ruleId": rule_id,
            "severity": rule["severity"],
            "path": path,
            "message": rule["message"],
            "suggestion": rule["suggestion"],
            "runtimeEffect": rule["runtimeEffect"],
        })

    story = _mapping(document.get("story"))
    target = _mapping(document.get("target"))
    resources = _mapping(document.get("resources"))
    if not str(story.get("title", "")).strip():
        emit(
            (
                "package.story-title-required"
                if profile == "package"
                else "quality.story-title-empty"
            ),
            "/story/title",
        )
    if not str(target.get("workspaceId", "")).strip():
        emit(
            (
                "package.workspace-required"
                if profile == "package"
                else "quality.target-unset"
            ),
            "/target/workspaceId",
        )
    if target.get("allowCreateWorkspace") is True:
        if not str(target.get("workspaceName", "")).strip():
            emit("package.workspace-name-required", "/target/workspaceName")
        if not str(target.get("workspaceRoot", "")).strip():
            emit("package.workspace-root-required", "/target/workspaceRoot")
    if not _sequence(resources.get("openings")):
        emit("quality.opening-missing", "/resources/openings")
    if profile == "package" and not str(
        story.get("storyPrompt", "")
    ).strip():
        emit("quality.story-prompt-empty", "/story/storyPrompt")
    if len(str(story.get("summary", "")).strip()) > 240:
        emit("quality.story-summary-too-long", "/story/summary")
    for index, question in enumerate(
        _sequence(document.get("openQuestions"))
    ):
        if _mapping(question).get("status", "open") == "open":
            emit(
                "workflow.open-question-unresolved",
                f"/openQuestions/{index}",
            )

    portrayal_pattern = re.compile(
        r"(性格|口头禅|说话(?:方式|语气|习惯)|行为倾向|"
        r"心理(?:活动|状态)|内心(?:想法|活动)|"
        r"\bpersonality\b|\bspeech pattern\b|\bbehavior tendency\b)",
        re.IGNORECASE,
    )
    objective_tags = {
        "kind:appearance",
        "kind:background",
        "kind:relationship",
        "kind:ability",
    }
    portrayal_tags = {
        "kind:personality",
        "kind:speech",
        "kind:behavior",
        "kind:psychology",
    }
    for character_index, raw_character in enumerate(
        _sequence(resources.get("characters"))
    ):
        character = _mapping(raw_character)
        base = f"/resources/characters/{character_index}"
        if portrayal_pattern.search(
            str(character.get("description", ""))
        ):
            emit(
                "character.description-portrayal-leak",
                f"{base}/description",
            )
        for detail_index, raw_detail in enumerate(
            _sequence(character.get("details"))
        ):
            detail = _mapping(raw_detail)
            tags = {
                str(tag)
                for tag in _sequence(detail.get("tags"))
                if isinstance(tag, str)
            }
            objective = bool(tags.intersection(objective_tags))
            portrayal = bool(tags.intersection(portrayal_tags))
            path = f"{base}/details/{detail_index}/tags"
            if objective and portrayal:
                emit("character.detail-mixed-kinds", path)
            if str(detail.get("content", "")).strip() and not (
                objective or portrayal
            ):
                emit("character.detail-kind-missing", path)

    scheduling_pattern = re.compile(
        r"(每.{0,10}(回合|轮|turn|分钟|小时|天)|延迟|延期更新|"
        r"定时|周期|defer(?:red)?|interval|read[\s_-]?only|"
        r"只读|手动更新|manual)",
        re.IGNORECASE,
    )
    for table_index, raw_table in enumerate(
        _sequence(resources.get("statusTables"))
    ):
        table = _mapping(raw_table)
        for row_index, raw_row in enumerate(
            _sequence(table.get("rows"))
        ):
            row = _mapping(raw_row)
            base = (
                f"/resources/statusTables/{table_index}/rows/{row_index}"
            )
            update_rule = str(row.get("updateRule", ""))
            if update_rule and scheduling_pattern.search(update_rule):
                emit("status.update-rule-scheduling", f"{base}/updateRule")
            if table.get("statusKind") == "scene" and row.get("key") == "时间":
                match = re.search(
                    r"(\d+)\s*年",
                    str(row.get("value", "")),
                )
                if match and int(match.group(1)) < 1000:
                    emit("status.scene-placeholder-year", f"{base}/value")

    player_control_pattern = re.compile(
        r"(玩家|用户|player|user).{0,8}"
        r"(已经|必须|决定|选择|答应|拒绝|接受|同意|"
        r"has|must|decides|chooses|agrees|refuses|accepts)",
        re.IGNORECASE,
    )
    schedule = _mapping(resources.get("plotSchedule"))
    for event_index, raw_event in enumerate(
        _sequence(schedule.get("events"))
    ):
        event = _mapping(raw_event)
        base = f"/resources/plotSchedule/events/{event_index}"
        hint = str(event.get("suitabilityHint", "")).strip()
        if event.get("dispatchMode", "soft") == "soft" and not hint:
            emit("plot.soft-event-hint-empty", f"{base}/suitabilityHint")
        if event.get("dispatchMode") == "forced" and hint:
            emit("plot.forced-event-unused-hint", f"{base}/suitabilityHint")
        if not str(event.get("description", "")).strip():
            emit("plot.event-description-empty", f"{base}/description")
        directive = re.sub(
            r"(不得|不要|不可|避免)替玩家",
            "",
            str(event.get("directive", "")),
        )
        if player_control_pattern.search(directive):
            emit("plot.directive-controls-player", f"{base}/directive")

    for lore_index, raw_lore in enumerate(
        _sequence(resources.get("lorebook"))
    ):
        lore = _mapping(raw_lore)
        if not str(lore.get("content", "")).strip():
            emit(
                "lorebook.content-empty",
                f"/resources/lorebook/{lore_index}/content",
            )
    for style_index, raw_style in enumerate(
        _sequence(resources.get("narrativeStyles"))
    ):
        style = _mapping(raw_style)
        if not str(style.get("prompt", "")).strip():
            emit(
                "composer.style-prompt-empty",
                f"/resources/narrativeStyles/{style_index}/prompt",
            )
    known_ids = _viewer_stable_ids(document)
    for visual_index, raw_visual in enumerate(
        _sequence(resources.get("visualCatalog"))
    ):
        visual = _mapping(raw_visual)
        base = f"/resources/visualCatalog/{visual_index}"
        if not _sequence(visual.get("visualAnchors")):
            emit("visual.anchors-empty", f"{base}/visualAnchors")
        for ref_index, reference in enumerate(
            _sequence(visual.get("subjectRefs"))
        ):
            if isinstance(reference, str) and reference not in known_ids:
                emit(
                    "visual.subject-ref-unresolved",
                    f"{base}/subjectRefs/{ref_index}",
                )
    return sorted(
        output,
        key=lambda item: (
            0 if item["severity"] == "error" else 1,
            item["path"],
            item["ruleId"],
        ),
    )


def _viewer_stable_ids(document: Mapping[str, Any]) -> set[str]:
    story = _mapping(document.get("story"))
    resources = _mapping(document.get("resources"))
    result = {
        str(story["stableId"])
        for _ in [0]
        if story.get("stableId")
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
        for raw_item in _sequence(resources.get(key)):
            item = _mapping(raw_item)
            if item.get("stableId"):
                result.add(str(item["stableId"]))
            if key == "characters":
                for raw_detail in _sequence(item.get("details")):
                    detail = _mapping(raw_detail)
                    if detail.get("stableId"):
                        result.add(str(detail["stableId"]))
    schedule = _mapping(resources.get("plotSchedule"))
    for key in ("pools", "events", "outlines"):
        for raw_item in _sequence(schedule.get(key)):
            item = _mapping(raw_item)
            if item.get("stableId"):
                result.add(str(item["stableId"]))
            if key == "outlines":
                for raw_node in _sequence(item.get("nodes")):
                    node = _mapping(raw_node)
                    if node.get("stableId"):
                        result.add(str(node["stableId"]))
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, list) else ()


class ViewerHTTPServer(ThreadingHTTPServer):
    """Threaded loopback server with a shared immutable project reader."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        reader: ProjectReader,
    ) -> None:
        self.reader = reader
        self.stop_event = threading.Event()
        super().__init__(server_address, ViewerRequestHandler)

    def server_close(self) -> None:
        self.stop_event.set()
        super().server_close()


class ViewerRequestHandler(BaseHTTPRequestHandler):
    """Serve static UI, read-only APIs, and revision events."""

    server: ViewerHTTPServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/events":
                self._serve_events()
                return
            if path == "/api/project":
                self._send_json(self.server.reader.project())
                return
            if path == "/api/revisions":
                self._send_json(self.server.reader.history())
                return
            if path == "/api/diff":
                query = parse_qs(parsed.query)
                from_revision = _single_query_value(query, "from")
                to_revision = _single_query_value(query, "to")
                self._send_json(
                    self.server.reader.diff(from_revision, to_revision)
                )
                return
            if path.startswith("/api/revisions/"):
                revision_id = path.removeprefix("/api/revisions/")
                if "/" in revision_id:
                    raise ViewerNotFoundError("revision route not found")
                self._send_json(self.server.reader.revision(revision_id))
                return
            if path.startswith("/api/schemas/"):
                schema_name = path.removeprefix("/api/schemas/")
                if "/" in schema_name:
                    raise ViewerNotFoundError("schema route not found")
                self._send_json(self.server.reader.schema(schema_name))
                return
            if path == "/api/authoring-rules":
                self._send_json(self.server.reader.authoring_rules())
                return
            if path == "/api/diagnostics":
                query = parse_qs(parsed.query)
                revision_id = _single_query_value(query, "revision")
                profile = (
                    query.get("profile", ["draft"])[0]
                    if query.get("profile")
                    else "draft"
                )
                self._send_json(
                    self.server.reader.diagnostics(
                        revision_id,
                        profile=profile,
                    )
                )
                return
            if path == "/api/story-packs":
                self._send_json(self.server.reader.story_packs())
                return
            if path.startswith("/api/story-packs/"):
                filename = path.removeprefix("/api/story-packs/")
                if "/" in filename:
                    raise ViewerNotFoundError("Story Pack route not found")
                self._send_json(self.server.reader.story_pack(filename))
                return
            if path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_security_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._serve_static(path)
        except ViewerNotFoundError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except ViewerValidationError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except (OSError, ValueError, TypeError) as exc:
            self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"viewer could not read the project: {exc}",
            )

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in STATIC_FILES:
            self._serve_static(parsed.path, include_body=False)
            return
        if parsed.path.startswith("/api/"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_security_headers()
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, "route not found")

    def do_POST(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self._send_error_json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "Story Design Viewer is read-only",
            extra_headers={"Allow": "GET, HEAD"},
        )

    def _serve_static(
        self,
        path: str,
        *,
        include_body: bool = True,
    ) -> None:
        filename = STATIC_FILES.get(path)
        if filename is None:
            raise ViewerNotFoundError("route not found")
        asset_path = self.server.reader.viewer_root / filename
        try:
            payload = asset_path.read_bytes()
        except FileNotFoundError as exc:
            raise ViewerNotFoundError(f"viewer asset missing: {filename}") from exc
        content_type = mimetypes.guess_type(filename)[0]
        if content_type is None:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type == (
            "application/javascript"
        ):
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self._send_security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def _serve_events(self) -> None:
        previous = self.server.reader.snapshot()
        self.send_response(HTTPStatus.OK)
        self._send_security_headers()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            self._write_event("snapshot", previous)
            last_heartbeat = time.monotonic()
            while not self.server.stop_event.wait(0.5):
                try:
                    current = self.server.reader.snapshot()
                except ViewerError:
                    continue
                revision_changed = (
                    current.get("currentRevision"),
                    current.get("headDigest"),
                ) != (
                    previous.get("currentRevision"),
                    previous.get("headDigest"),
                )
                packs_changed = current.get(
                    "packSignature"
                ) != previous.get("packSignature")
                authoring_rules_changed = current.get(
                    "authoringAssetsDigest"
                ) != previous.get("authoringAssetsDigest")
                if revision_changed:
                    self._write_event("revision", current)
                if packs_changed:
                    self._write_event("packs", current)
                if authoring_rules_changed:
                    self._write_event("authoring-rules", current)
                if (
                    revision_changed
                    or packs_changed
                    or authoring_rules_changed
                ):
                    previous = current
                if time.monotonic() - last_heartbeat >= 15:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    last_heartbeat = time.monotonic()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def _write_event(self, event: str, value: Mapping[str, Any]) -> None:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        event_id = (
            f"{value.get('currentRevision', 'unknown')}:"
            f"{str(value.get('headDigest', ''))[:12]}"
        )
        message = (
            f"id: {event_id}\n"
            f"event: {event}\n"
            f"data: {payload}\n\n"
        )
        self.wfile.write(message.encode("utf-8"))
        self.wfile.flush()

    def _send_json(
        self,
        value: object,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self._send_security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        for name, header_value in (extra_headers or {}).items():
            self.send_header(name, header_value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _send_error_json(
        self,
        status: HTTPStatus,
        message: str,
        *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._send_json(
            {
                "error": status.phrase,
                "message": message,
                "status": int(status),
            },
            status=status,
            extra_headers=extra_headers,
        )

    def _send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'",
        )

    def log_message(self, format: str, *args: object) -> None:
        if self.path == "/events":
            return
        super().log_message(format, *args)


def _single_query_value(
    query: Mapping[str, list[str]],
    name: str,
) -> str:
    values = query.get(name, [])
    if len(values) != 1 or not values[0]:
        raise ViewerValidationError(f"query parameter {name!r} is required")
    return values[0]


def create_server(
    project_root: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ViewerHTTPServer:
    if host != DEFAULT_HOST:
        raise ValueError("Story Design Viewer is loopback-only")
    if not 0 <= int(port) <= 65535:
        raise ValueError("port must be between 0 and 65535")
    return ViewerHTTPServer(
        (host, int(port)),
        ProjectReader(project_root),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only local Story DesignProject viewer.",
    )
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="DesignProject root; defaults to the viewer parent directory.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Loopback port; defaults to {DEFAULT_PORT}.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the viewer in the default browser after startup.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    server = create_server(
        args.project_root,
        port=args.port,
    )
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    print(f"Story Design Viewer: {url}", flush=True)
    print("Press Ctrl+C to stop. The viewer is read-only.", flush=True)
    if args.open:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ProjectReader",
    "ViewerError",
    "ViewerNotFoundError",
    "ViewerValidationError",
    "build_parser",
    "create_server",
    "main",
]
