"""File-backed, relocatable Story design revision store."""

from __future__ import annotations

import copy
import difflib
import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from pydantic import ValidationError

from rpg_mcp.contracts import (
    CONTRACT_VERSION,
    PROJECT_SCHEMA_VERSION,
    RESOURCE_SECTIONS,
    StoryDesignDocument,
    StoryPack,
    build_story_pack,
    canonical_json,
    digest_json,
    utc_now,
)


class DesignStoreError(RuntimeError):
    """Base error for portable design-project operations."""


class DesignConflictError(DesignStoreError):
    """The expected head differs from the current immutable revision head."""


class DesignValidationError(DesignStoreError):
    """A proposed design document does not satisfy the neutral contract."""


_REVISION_RE = re.compile(r"^r(?P<number>\d{6})$")
_CHECKPOINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class DesignProjectStore:
    """Own one portable DesignProject without importing RPG runtime modules."""

    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve()
        self.project_path = self.root / "design-project.json"
        self.current_path = self.root / "design" / "current.json"
        self.revisions_dir = self.root / "design" / "revisions"
        self.checkpoints_dir = self.root / "design" / "checkpoints"
        self.pack_dir = self.root / "artifacts" / "story-packs"
        self.reports_dir = self.root / "reports"
        self.lock_path = self.root / ".design.lock"
        self.transaction_path = self.root / ".design-transaction.json"
        if not self.project_path.is_file():
            raise FileNotFoundError(
                f"design-project.json not found under {self.root}"
            )
        self._ensure_recovered()

    @classmethod
    def initialize(
        cls,
        project_root: str | Path,
        document: StoryDesignDocument,
        *,
        project_name: str,
    ) -> "DesignProjectStore":
        root = Path(project_root).expanduser().resolve()
        for relative in (
            "design/revisions",
            "design/checkpoints",
            "design/sources",
            "artifacts/story-packs",
            "artifacts/snapshots",
            "integrations",
            "reports",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        project_path = root / "design-project.json"
        if project_path.exists():
            raise FileExistsError(f"DesignProject already exists: {project_path}")
        now = utc_now()
        revision_id = "r000001"
        document_value = document.model_dump(by_alias=True)
        document_digest = digest_json(document_value)
        revision = {
            "schemaVersion": PROJECT_SCHEMA_VERSION,
            "revisionId": revision_id,
            "revisionNumber": 1,
            "parentRevision": None,
            "parentDigest": None,
            "documentDigest": document_digest,
            "createdAt": now,
            "reason": "Initialize portable Story design project",
            "document": document_value,
        }
        manifest = {
            "schemaVersion": PROJECT_SCHEMA_VERSION,
            "contractVersion": CONTRACT_VERSION,
            "projectId": document.project.project_id,
            "name": str(project_name),
            "currentRevision": revision_id,
            "headDigest": document_digest,
            "createdAt": now,
            "updatedAt": now,
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
        _atomic_write_json(
            root / "design" / "revisions" / f"{revision_id}.json",
            revision,
        )
        _atomic_write_json(root / "design" / "current.json", document_value)
        _atomic_write_json(project_path, manifest)
        return cls(root)

    def get_project(self) -> dict[str, Any]:
        manifest = self._manifest()
        return {
            **manifest,
            "projectRoot": str(self.root),
            "portable": True,
        }

    def get_current(self) -> dict[str, Any]:
        manifest = self._manifest()
        document = self._verified_current(manifest)
        return {
            "revision": manifest["currentRevision"],
            "headDigest": manifest["headDigest"],
            "document": document.model_dump(by_alias=True),
        }

    def get_section(self, pointer: str) -> dict[str, Any]:
        current = self.get_current()
        return {
            "revision": current["revision"],
            "headDigest": current["headDigest"],
            "pointer": pointer,
            "value": copy.deepcopy(
                _resolve_pointer(current["document"], pointer)
            ),
        }

    def get_resume_context(self, *, recent_decisions: int = 12) -> dict[str, Any]:
        current = self.get_current()
        document = StoryDesignDocument.model_validate(current["document"])
        resources = document.resources
        open_questions = [
            item.model_dump(by_alias=True)
            for item in document.open_questions
            if item.status == "open"
        ]
        decisions = [
            item.model_dump(by_alias=True)
            for item in document.decisions[-max(0, int(recent_decisions)):]
        ]
        return {
            "revision": current["revision"],
            "headDigest": current["headDigest"],
            "project": document.project.model_dump(by_alias=True),
            "target": document.target.model_dump(by_alias=True),
            "story": document.story.model_dump(by_alias=True),
            "resourceCounts": {
                "openings": len(resources.openings),
                "characters": len(resources.characters),
                "lorebook": len(resources.lorebook),
                "statusTables": len(resources.status_tables),
                "narrativeStyles": len(resources.narrative_styles),
                "quickReplies": len(resources.quick_replies),
                "rpModules": len(resources.rp_modules),
                "plotPools": len(resources.plot_schedule.pools),
                "plotEvents": len(resources.plot_schedule.events),
                "plotOutlines": len(resources.plot_schedule.outlines),
                "visualSpecifications": len(resources.visual_catalog),
            },
            "recentDecisions": decisions,
            "openQuestions": open_questions,
            "nextAction": (
                "Resolve openQuestions, save each confirmed decision with "
                "story_design_patch, then create a named checkpoint at a "
                "meaningful milestone."
            ),
        }

    def patch(
        self,
        *,
        expected_head: str,
        operations: Sequence[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        if not str(reason or "").strip():
            raise ValueError("reason must not be empty")
        with self._exclusive_lock():
            self._recover_interrupted_commit()
            manifest = self._manifest()
            self._require_expected_head(manifest, expected_head)
            current = self._verified_current(manifest).model_dump(by_alias=True)
            updated = apply_json_patch(current, operations)
            return self._commit(
                manifest,
                updated,
                reason=str(reason).strip(),
            )

    def restore_revision(
        self,
        revision_id: str,
        *,
        expected_head: str,
        reason: str,
    ) -> dict[str, Any]:
        if not str(reason or "").strip():
            raise ValueError("reason must not be empty")
        with self._exclusive_lock():
            self._recover_interrupted_commit()
            manifest = self._manifest()
            self._require_expected_head(manifest, expected_head)
            self._verified_current(manifest)
            target = self._revision(revision_id)
            return self._commit(
                manifest,
                target["document"],
                reason=f"{str(reason).strip()} (restore {revision_id})",
            )

    def create_checkpoint(
        self,
        name: str,
        *,
        expected_head: str,
        note: str = "",
    ) -> dict[str, Any]:
        normalized = str(name or "").strip()
        if not _CHECKPOINT_RE.fullmatch(normalized):
            raise ValueError(
                "checkpoint name must use 1-64 letters, digits, '.', '_' or '-'"
            )
        with self._exclusive_lock():
            self._recover_interrupted_commit()
            manifest = self._manifest()
            self._require_expected_head(manifest, expected_head)
            self._verified_current(manifest)
            path = self.checkpoints_dir / f"{normalized}.json"
            if path.exists():
                raise FileExistsError(
                    f"checkpoint is immutable and already exists: {normalized}"
                )
            value = {
                "schemaVersion": PROJECT_SCHEMA_VERSION,
                "name": normalized,
                "revision": manifest["currentRevision"],
                "documentDigest": manifest["headDigest"],
                "createdAt": utc_now(),
                "note": str(note or ""),
            }
            _atomic_write_json(path, value)
            return value

    def list_history(self, *, limit: int = 50) -> dict[str, Any]:
        manifest = self._manifest()
        rows: list[dict[str, Any]] = []
        for path in sorted(self.revisions_dir.glob("r*.json"), reverse=True):
            revision = _read_json(path)
            rows.append({
                key: revision.get(key)
                for key in (
                    "revisionId",
                    "revisionNumber",
                    "parentRevision",
                    "documentDigest",
                    "createdAt",
                    "reason",
                )
            })
            if len(rows) >= max(1, min(int(limit), 200)):
                break
        checkpoints = [
            _read_json(path)
            for path in sorted(self.checkpoints_dir.glob("*.json"))
        ]
        return {
            "currentRevision": manifest["currentRevision"],
            "headDigest": manifest["headDigest"],
            "revisions": rows,
            "checkpoints": checkpoints,
        }

    def diff_revisions(
        self,
        from_revision: str,
        to_revision: str,
    ) -> dict[str, Any]:
        before = self._revision(from_revision)
        after = self._revision(to_revision)
        before_lines = _pretty_json(before["document"]).splitlines(keepends=True)
        after_lines = _pretty_json(after["document"]).splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=from_revision,
            tofile=to_revision,
        ))
        return {
            "fromRevision": from_revision,
            "toRevision": to_revision,
            "changed": before["documentDigest"] != after["documentDigest"],
            "unifiedDiff": diff,
        }

    def validate(self, revision_id: str | None = None) -> dict[str, Any]:
        try:
            if revision_id is None:
                manifest = self._manifest()
                document = self._verified_current(manifest)
                revision = manifest["currentRevision"]
            else:
                raw = self._revision(revision_id)
                document = StoryDesignDocument.model_validate(raw["document"])
                revision = revision_id
        except (
            DesignStoreError,
            ValidationError,
            ValueError,
            TypeError,
        ) as exc:
            return {
                "valid": False,
                "revision": revision_id,
                "errors": _validation_errors(exc),
                "warnings": [],
            }
        warnings: list[str] = []
        if not document.story.title.strip():
            warnings.append("Story title is still empty; Story Pack build will fail.")
        if not document.target.workspace_id:
            warnings.append(
                "Runtime target workspaceId is unset; provide a build override "
                "before creating a Story Pack."
            )
        if not document.resources.openings:
            warnings.append(
                "No Opening is defined. This is valid, but a new Session will "
                "not have an authored opening."
            )
        if any(
            question.status == "open" for question in document.open_questions
        ):
            warnings.append("The design still contains unresolved open questions.")
        return {
            "valid": True,
            "revision": revision,
            "headDigest": digest_json(document.model_dump(by_alias=True)),
            "errors": [],
            "warnings": warnings,
        }

    def build_pack(
        self,
        *,
        expected_head: str,
        included_sections: Sequence[str] | None = None,
        target_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._exclusive_lock():
            self._recover_interrupted_commit()
            manifest = self._manifest()
            self._require_expected_head(manifest, expected_head)
            document = self._verified_current(manifest)
            revision = self._revision(str(manifest["currentRevision"]))
            pack = build_story_pack(
                document,
                source_revision=manifest["currentRevision"],
                source_digest=manifest["headDigest"],
                included_sections=list(included_sections or RESOURCE_SECTIONS),
                target_overrides=target_overrides,
                generated_at=str(revision["createdAt"]),
            )
            value = pack.model_dump(by_alias=True, exclude_none=True)
            path = self.pack_dir / f"{pack.pack_id}.json"
            if path.exists():
                existing = _read_json(path)
                if digest_json(existing) != digest_json(value):
                    raise FileExistsError(
                        f"immutable Story Pack id already exists: {pack.pack_id}"
                    )
            else:
                _atomic_write_json(path, value)
        return {
            "valid": True,
            "packId": pack.pack_id,
            "packDigest": digest_json(value),
            "sourceRevision": pack.source_revision,
            "includedSections": list(pack.included_sections),
            "path": path.relative_to(self.root).as_posix(),
            "pack": value,
        }

    def doctor(self) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        if self.transaction_path.is_file():
            errors.append(
                "an interrupted design commit journal remains; restart the "
                "MCP service to run guarded recovery"
            )
        try:
            manifest = self._manifest()
        except Exception as exc:
            return {
                "healthy": False,
                "errors": [str(exc)],
                "warnings": [],
            }
        if manifest.get("contractVersion") != CONTRACT_VERSION:
            errors.append(
                "DesignProject contractVersion differs from the installed MCP "
                f"service ({manifest.get('contractVersion')} != "
                f"{CONTRACT_VERSION})."
            )
        expected_contract_digest = manifest.get("contractDigest")
        if expected_contract_digest:
            contract_path = self.root / "schemas" / "rpg-mcp-contract-v2.json"
            try:
                contract_digest = digest_json(_read_json(contract_path))
                if contract_digest != expected_contract_digest:
                    errors.append(
                        "checked-in MCP contract digest differs from "
                        "design-project.json"
                    )
            except Exception as exc:
                errors.append(f"cannot verify MCP contract: {exc}")
        else:
            warnings.append(
                "project manifest has no contractDigest; this is valid for a "
                "minimal programmatically initialized project."
            )
        for key, value in manifest.get("paths", {}).items():
            path = str(value)
            if Path(path).is_absolute() or ".." in Path(path).parts:
                errors.append(f"manifest path {key} is not portable: {path}")
        try:
            current = self._current_document().model_dump(by_alias=True)
            if (
                current["project"]["projectId"]
                != manifest.get("projectId")
            ):
                errors.append(
                    "current design projectId differs from project manifest"
                )
            if digest_json(current) != manifest.get("headDigest"):
                errors.append("design/current.json digest differs from headDigest")
            revision = self._revision(str(manifest.get("currentRevision")))
            if revision.get("documentDigest") != manifest.get("headDigest"):
                errors.append("current revision digest differs from manifest")
        except Exception as exc:
            errors.append(str(exc))
        revision_paths = sorted(self.revisions_dir.glob("r*.json"))
        previous: dict[str, Any] | None = None
        for path in revision_paths:
            try:
                revision = _read_json(path)
                if digest_json(revision["document"]) != revision["documentDigest"]:
                    errors.append(f"revision digest mismatch: {path.name}")
                if previous is not None:
                    if revision.get("parentRevision") != previous["revisionId"]:
                        errors.append(f"broken revision parent: {path.name}")
                    if revision.get("parentDigest") != previous["documentDigest"]:
                        errors.append(f"broken revision parent digest: {path.name}")
                previous = revision
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        for path in sorted(self.checkpoints_dir.glob("*.json")):
            try:
                checkpoint = _read_json(path)
                self._revision(str(checkpoint["revision"]))
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        if (self.root / ".design.lock").exists():
            warnings.append(
                ".design.lock is a normal coordination file and may be deleted "
                "only while no design writer is running."
            )
        return {
            "healthy": not errors,
            "projectRoot": str(self.root),
            "currentRevision": manifest.get("currentRevision"),
            "errors": errors,
            "warnings": warnings,
        }

    def write_runtime_integration(
        self,
        operation: dict[str, Any],
    ) -> dict[str, str]:
        """Write post-commit integration/report files.

        The runtime database transaction must already have committed. A caller
        can safely retry this method because both outputs are deterministic for
        one operation id.
        """

        self._ensure_recovered()
        operation_id = str(operation["operationId"])
        manifest = self._manifest()
        if operation.get("projectId") != manifest.get("projectId"):
            raise DesignConflictError(
                "runtime operation projectId does not match this DesignProject"
            )
        integration_relative = "integrations/rpg-world.json"
        report_relative = f"reports/runtime-operation-{operation_id}.json"
        integration = {
            "schemaVersion": "rpg-world-integration/2.0",
            "projectId": operation["projectId"],
            "lastOperationId": operation_id,
            "lastStatus": operation["status"],
            "workspaceId": operation["workspaceId"],
            "storyStableId": operation["storyStableId"],
            "storyId": operation.get("storyId"),
            "packId": operation["packId"],
            "packDigest": operation["packDigest"],
            "updatedAt": utc_now(),
        }
        integration_path = self.root / integration_relative
        report_path = self.reports_dir / f"runtime-operation-{operation_id}.json"
        report = copy.deepcopy(operation)
        if isinstance(report.get("result"), dict):
            report["result"]["localSync"] = {
                "completed": True,
                "integrationPath": integration_relative,
                "reportPath": report_relative,
            }
        _atomic_write_json(integration_path, integration)
        _atomic_write_json(report_path, report)
        return {
            "integrationPath": integration_relative,
            "reportPath": report_relative,
        }

    def write_runtime_snapshot(
        self,
        snapshot: dict[str, Any],
    ) -> dict[str, str]:
        self._ensure_recovered()
        workspace_id = str(snapshot.get("workspaceId", "workspace"))
        story_id = str(snapshot.get("storyId", "story"))
        snapshot_digest = digest_json(snapshot)
        filename = (
            f"runtime-{workspace_id}-{story_id}-{snapshot_digest[:12]}.json"
        )
        path = self.root / "artifacts" / "snapshots" / filename
        if path.exists():
            if digest_json(_read_json(path)) != snapshot_digest:
                raise FileExistsError(
                    f"immutable runtime snapshot collision: {filename}"
                )
        else:
            _atomic_write_json(path, snapshot)
        return {
            "snapshotPath": path.relative_to(self.root).as_posix(),
            "snapshotDigest": snapshot_digest,
        }

    def _commit(
        self,
        manifest: dict[str, Any],
        document: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any]:
        try:
            validated = StoryDesignDocument.model_validate(document)
            value = validated.model_dump(by_alias=True)
            canonical_json(value)
        except (ValidationError, TypeError, ValueError) as exc:
            raise DesignValidationError(
                "; ".join(_validation_errors(exc))
            ) from exc
        old_revision = str(manifest["currentRevision"])
        old_digest = str(manifest["headDigest"])
        match = _REVISION_RE.fullmatch(old_revision)
        if match is None:
            raise DesignStoreError(
                f"invalid current revision id: {old_revision}"
            )
        number = int(match.group("number")) + 1
        revision_id = f"r{number:06d}"
        document_digest = digest_json(value)
        if document_digest == old_digest:
            raise DesignConflictError(
                "proposed change does not modify the current design document"
            )
        now = utc_now()
        revision = {
            "schemaVersion": PROJECT_SCHEMA_VERSION,
            "revisionId": revision_id,
            "revisionNumber": number,
            "parentRevision": old_revision,
            "parentDigest": old_digest,
            "documentDigest": document_digest,
            "createdAt": now,
            "reason": reason,
            "document": value,
        }
        revision_path = self.revisions_dir / f"{revision_id}.json"
        if revision_path.exists():
            raise DesignConflictError(
                f"revision already exists: {revision_id}"
            )
        updated_manifest = {
            **manifest,
            "projectId": validated.project.project_id,
            "name": validated.project.name,
            "currentRevision": revision_id,
            "headDigest": document_digest,
            "updatedAt": now,
        }
        transaction = {
            "schemaVersion": "story-design-transaction/2.0",
            "baseManifest": manifest,
            "targetManifest": updated_manifest,
            "revision": revision,
        }
        _atomic_write_json(self.transaction_path, transaction)
        try:
            _atomic_write_json(revision_path, revision)
            _atomic_write_json(self.current_path, value)
            _atomic_write_json(self.project_path, updated_manifest)
        except Exception as write_error:
            try:
                self._recover_interrupted_commit()
            except Exception as recovery_error:
                raise DesignStoreError(
                    "design commit write failed and guarded recovery could "
                    f"not complete: {write_error}; recovery: {recovery_error}"
                ) from write_error
        if self.transaction_path.exists():
            self.transaction_path.unlink()
        return {
            "revision": revision_id,
            "parentRevision": old_revision,
            "headDigest": document_digest,
            "reason": reason,
        }

    def _require_expected_head(
        self,
        manifest: dict[str, Any],
        expected_head: str,
    ) -> None:
        current = str(manifest.get("currentRevision", ""))
        if str(expected_head or "") != current:
            raise DesignConflictError(
                f"stale design head: expected {expected_head!r}, current "
                f"{current!r}; reload resume context before editing"
            )

    def _manifest(self) -> dict[str, Any]:
        value = _read_json(self.project_path)
        if value.get("schemaVersion") != PROJECT_SCHEMA_VERSION:
            raise DesignStoreError(
                "unsupported DesignProject schemaVersion: "
                f"{value.get('schemaVersion')!r}"
            )
        return value

    def _verified_current(
        self,
        manifest: dict[str, Any],
    ) -> StoryDesignDocument:
        document = self._current_document()
        value = document.model_dump(by_alias=True)
        if digest_json(value) != manifest.get("headDigest"):
            raise DesignStoreError(
                "design/current.json digest differs from project head"
            )
        revision = self._revision(str(manifest.get("currentRevision", "")))
        if revision.get("documentDigest") != manifest.get("headDigest"):
            raise DesignStoreError(
                "current immutable revision digest differs from project head"
            )
        if digest_json(revision.get("document")) != manifest.get("headDigest"):
            raise DesignStoreError("current immutable revision is corrupt")
        return document

    def _ensure_recovered(self) -> None:
        if not self.transaction_path.is_file():
            return
        with self._exclusive_lock():
            self._recover_interrupted_commit()

    def _recover_interrupted_commit(self) -> None:
        if not self.transaction_path.is_file():
            return
        transaction = _read_json(self.transaction_path)
        if transaction.get("schemaVersion") != "story-design-transaction/2.0":
            raise DesignStoreError("unsupported design transaction journal")
        base_manifest = transaction.get("baseManifest")
        target_manifest = transaction.get("targetManifest")
        revision = transaction.get("revision")
        if not all(
            isinstance(value, dict)
            for value in (base_manifest, target_manifest, revision)
        ):
            raise DesignStoreError("design transaction journal is malformed")
        assert isinstance(base_manifest, dict)
        assert isinstance(target_manifest, dict)
        assert isinstance(revision, dict)
        current_manifest = _read_json(self.project_path)
        if current_manifest not in (base_manifest, target_manifest):
            raise DesignConflictError(
                "design transaction journal conflicts with project manifest"
            )
        revision_id = str(revision.get("revisionId", ""))
        if _REVISION_RE.fullmatch(revision_id) is None:
            raise DesignStoreError(
                "design transaction contains an invalid revision id"
            )
        document = revision.get("document")
        if not isinstance(document, dict):
            raise DesignStoreError(
                "design transaction revision document is malformed"
            )
        validated = StoryDesignDocument.model_validate(document)
        document_value = validated.model_dump(by_alias=True)
        document_digest = digest_json(document_value)
        if (
            revision.get("documentDigest") != document_digest
            or revision.get("parentRevision")
            != base_manifest.get("currentRevision")
            or revision.get("parentDigest") != base_manifest.get("headDigest")
            or target_manifest.get("currentRevision") != revision_id
            or target_manifest.get("headDigest") != document_digest
        ):
            raise DesignStoreError(
                "design transaction revision chain is inconsistent"
            )
        expected_target = {
            **base_manifest,
            "projectId": validated.project.project_id,
            "name": validated.project.name,
            "currentRevision": revision_id,
            "headDigest": document_digest,
            "updatedAt": target_manifest.get("updatedAt"),
        }
        if target_manifest != expected_target:
            raise DesignStoreError(
                "design transaction target manifest is inconsistent"
            )
        revision_path = self.revisions_dir / f"{revision_id}.json"
        if revision_path.exists():
            if _read_json(revision_path) != revision:
                raise DesignConflictError(
                    f"immutable revision collision during recovery: {revision_id}"
                )
        else:
            _atomic_write_json(revision_path, revision)
        _atomic_write_json(self.current_path, document_value)
        _atomic_write_json(self.project_path, target_manifest)
        self.transaction_path.unlink()

    def _current_document(self) -> StoryDesignDocument:
        try:
            return StoryDesignDocument.model_validate(
                _read_json(self.current_path)
            )
        except ValidationError as exc:
            raise DesignValidationError(
                "; ".join(_validation_errors(exc))
            ) from exc

    def _revision(self, revision_id: str) -> dict[str, Any]:
        normalized = str(revision_id or "").strip()
        if _REVISION_RE.fullmatch(normalized) is None:
            raise ValueError(f"invalid revision id: {revision_id!r}")
        path = self.revisions_dir / f"{normalized}.json"
        if not path.is_file():
            raise FileNotFoundError(f"design revision not found: {normalized}")
        value = _read_json(path)
        if value.get("revisionId") != normalized:
            raise DesignStoreError(f"revision identity mismatch: {normalized}")
        return value

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def apply_json_patch(
    document: dict[str, Any],
    operations: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Apply a strict RFC 6902 subset: add, replace, remove and test."""

    if not operations:
        raise ValueError("operations must not be empty")
    output = copy.deepcopy(document)
    for index, operation in enumerate(operations):
        op = str(operation.get("op", "")).lower()
        path = operation.get("path")
        if op not in {"add", "replace", "remove", "test"}:
            raise ValueError(f"operation {index} uses unsupported op: {op!r}")
        if not isinstance(path, str):
            raise ValueError(f"operation {index} path must be a string")
        if op == "test":
            actual = _resolve_pointer(output, path)
            if actual != operation.get("value"):
                raise DesignConflictError(
                    f"JSON Patch test failed at {path}"
                )
            continue
        parent, token = _resolve_parent(output, path)
        if op == "remove":
            _remove_value(parent, token, path)
        elif op == "replace":
            _replace_value(parent, token, operation.get("value"), path)
        else:
            _add_value(parent, token, operation.get("value"), path)
    return output


def _resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    tokens = _pointer_tokens(pointer)
    current = document
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                raise KeyError(f"JSON pointer does not exist: {pointer}")
            current = current[token]
        elif isinstance(current, list):
            current = current[_list_index(token, len(current), pointer)]
        else:
            raise KeyError(f"JSON pointer traverses a scalar: {pointer}")
    return current


def _resolve_parent(document: Any, pointer: str) -> tuple[Any, str]:
    tokens = _pointer_tokens(pointer)
    if not tokens:
        raise ValueError("patching the document root is not supported")
    parent_pointer = "/" + "/".join(
        token.replace("~", "~0").replace("/", "~1")
        for token in tokens[:-1]
    ) if len(tokens) > 1 else ""
    return _resolve_pointer(document, parent_pointer), tokens[-1]


def _pointer_tokens(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must be empty or start with '/'")
    return [
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer[1:].split("/")
    ]


def _list_index(token: str, length: int, pointer: str) -> int:
    if token == "-":
        raise IndexError(f"'-' is only valid for list add: {pointer}")
    try:
        index = int(token)
    except ValueError as exc:
        raise IndexError(f"invalid list index at {pointer}") from exc
    if index < 0 or index >= length:
        raise IndexError(f"list index out of range at {pointer}")
    return index


def _add_value(parent: Any, token: str, value: Any, pointer: str) -> None:
    if isinstance(parent, dict):
        parent[token] = copy.deepcopy(value)
        return
    if isinstance(parent, list):
        if token == "-":
            parent.append(copy.deepcopy(value))
            return
        try:
            index = int(token)
        except ValueError as exc:
            raise IndexError(f"invalid list index at {pointer}") from exc
        if index < 0 or index > len(parent):
            raise IndexError(f"list index out of range at {pointer}")
        parent.insert(index, copy.deepcopy(value))
        return
    raise TypeError(f"JSON Patch parent is not a container: {pointer}")


def _replace_value(parent: Any, token: str, value: Any, pointer: str) -> None:
    if isinstance(parent, dict):
        if token not in parent:
            raise KeyError(f"JSON pointer does not exist: {pointer}")
        parent[token] = copy.deepcopy(value)
        return
    if isinstance(parent, list):
        parent[_list_index(token, len(parent), pointer)] = copy.deepcopy(value)
        return
    raise TypeError(f"JSON Patch parent is not a container: {pointer}")


def _remove_value(parent: Any, token: str, pointer: str) -> None:
    if isinstance(parent, dict):
        if token not in parent:
            raise KeyError(f"JSON pointer does not exist: {pointer}")
        del parent[token]
        return
    if isinstance(parent, list):
        del parent[_list_index(token, len(parent), pointer)]
        return
    raise TypeError(f"JSON Patch parent is not a container: {pointer}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise DesignStoreError(f"cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DesignStoreError(f"JSON file must contain an object: {path}")
    return value


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _pretty_json(value) + "\n"
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _pretty_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )


def _validation_errors(exc: Exception) -> list[str]:
    if isinstance(exc, ValidationError):
        return [
            f"{'.'.join(str(item) for item in error['loc'])}: "
            f"{error['msg']}"
            for error in exc.errors()
        ]
    return [str(exc)]


__all__ = [
    "DesignConflictError",
    "DesignProjectStore",
    "DesignStoreError",
    "DesignValidationError",
    "apply_json_patch",
]
