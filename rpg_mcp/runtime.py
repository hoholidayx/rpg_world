"""RPG World runtime preview/apply adapter for neutral Story Pack v2."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from pydantic import ValidationError

from commons.scene_time import SceneTime
from commons.types import JsonValue
from rpg_core.rp_modules.plot_scheduler.commands import (
    CreatePlotEventCommand,
    CreatePlotNodeCommand,
    CreatePlotOutlineCommand,
    CreatePlotPoolCommand,
    UpdatePlotEventCommand,
    UpdatePlotNodeCommand,
    UpdatePlotOutlineCommand,
    UpdatePlotPoolCommand,
)
from rpg_data import models as data_models
from rpg_data.model.status import StatusTableDocument, StatusTableRow
from rpg_data.model.story_pack import (
    STORY_PACK_OPERATION_APPLIED,
    STORY_PACK_OPERATION_FAILED,
    STORY_PACK_OPERATION_LOCAL_SYNC_PENDING,
    STORY_PACK_OPERATION_PREVIEWED,
    StoryPackBinding,
    StoryPackOperation,
)
from rpg_mcp.contracts import (
    STORY_DESIGN_SCHEMA_VERSION,
    STORY_PACK_SCHEMA_VERSION,
    STORY_RUNTIME_METADATA_KEY,
    StoryPack,
    digest_json,
    utc_now,
)
from rpg_mcp.runtime_ports import RuntimeServices


RESOURCE_STORY = "story"
RESOURCE_OPENING = "opening"
RESOURCE_CHARACTER = "character"
RESOURCE_CHARACTER_DETAIL = "character_detail"
RESOURCE_LOREBOOK = "lorebook"
RESOURCE_STATUS_TABLE = "status_table"
RESOURCE_NARRATIVE_STYLE = "narrative_style"
RESOURCE_QUICK_REPLY = "quick_reply"
RESOURCE_RP_MODULE = "rp_module"
RESOURCE_PLOT_POOL = "plot_pool"
RESOURCE_PLOT_EVENT = "plot_event"
RESOURCE_PLOT_OUTLINE = "plot_outline"
RESOURCE_PLOT_NODE = "plot_node"
RESOURCE_VISUAL_SPEC = "visual_spec"

WRITABLE_RESOURCE_KINDS = (
    RESOURCE_OPENING,
    RESOURCE_CHARACTER,
    RESOURCE_CHARACTER_DETAIL,
    RESOURCE_LOREBOOK,
    RESOURCE_STATUS_TABLE,
    RESOURCE_NARRATIVE_STYLE,
    RESOURCE_QUICK_REPLY,
    RESOURCE_RP_MODULE,
    RESOURCE_PLOT_POOL,
    RESOURCE_PLOT_EVENT,
    RESOURCE_PLOT_OUTLINE,
    RESOURCE_PLOT_NODE,
)


class StoryPackRuntimeError(RuntimeError):
    """Base runtime import error."""


class StoryPackConflictError(StoryPackRuntimeError):
    """The preview contains conflicts and cannot be applied."""


class StoryPackPreviewStaleError(StoryPackRuntimeError):
    """Runtime state changed after preview."""


@dataclass(frozen=True)
class _IncomingResource:
    kind: str
    source_id: str
    name: str
    payload: dict[str, Any]
    parent_ref: str | None = None
    natural_identity: bool = False

    @property
    def source_digest(self) -> str:
        return digest_json(self.payload)


@dataclass
class _RuntimeState:
    story: Any
    objects: dict[str, dict[str, Any]]
    names: dict[str, dict[str, list[Any]]]
    bindings: dict[tuple[str, str], StoryPackBinding]
    style_mounts: list[Any]


class RuntimeApplication:
    """Own Story Pack planning, confirmation boundary, and atomic application."""

    def __init__(self, services: RuntimeServices) -> None:
        self._services = services

    # ------------------------------------------------------------------
    # Public runtime reads
    # ------------------------------------------------------------------

    def list_workspaces(self) -> dict[str, Any]:
        return {
            "workspaces": [
                {
                    "id": item.id,
                    "name": item.name,
                    "rootPath": item.root_path,
                    "description": item.description,
                    "version": item.version,
                }
                for item in self._services.catalog.list_workspaces()
            ]
        }

    def list_stories(self, workspace_id: str) -> dict[str, Any]:
        stories = self._services.catalog.list_stories(str(workspace_id))
        if stories is None:
            raise FileNotFoundError(f"workspace not found: {workspace_id}")
        return {
            "workspaceId": str(workspace_id),
            "stories": [
                {
                    "id": item.id,
                    "title": item.title,
                    "summary": item.summary,
                    "version": item.version,
                    "openingCount": len(item.openings),
                }
                for item in stories
            ],
        }

    def search_story_resources(
        self,
        workspace_id: str,
        story_id: int,
        *,
        query: str = "",
        kinds: Sequence[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        story = self._require_story(workspace_id, story_id)
        state = self._load_state(workspace_id, story)
        selected = set(kinds or WRITABLE_RESOURCE_KINDS)
        unknown = sorted(selected.difference(
            set(WRITABLE_RESOURCE_KINDS) | {RESOURCE_STORY}
        ))
        if unknown:
            raise ValueError(f"unknown resource kind(s): {unknown}")
        needle = str(query or "").strip().casefold()
        results: list[dict[str, Any]] = []
        if RESOURCE_STORY in selected:
            results.append({
                "kind": RESOURCE_STORY,
                "id": str(story.id),
                "name": story.title,
                "version": story.version,
            })
        for kind in WRITABLE_RESOURCE_KINDS:
            if kind not in selected:
                continue
            for item in state.objects.get(kind, {}).values():
                name = _object_name(kind, item)
                searchable = f"{name} {_object_summary(kind, item)}".casefold()
                if needle and needle not in searchable:
                    continue
                results.append({
                    "kind": kind,
                    "id": _object_id(kind, item),
                    "name": name,
                    "version": _object_version(item),
                    "summary": _object_summary(kind, item),
                })
        results.sort(key=lambda item: (item["kind"], item["name"], item["id"]))
        capped = max(1, min(int(limit), 200))
        return {
            "workspaceId": str(workspace_id),
            "storyId": int(story_id),
            "query": str(query or ""),
            "results": results[:capped],
            "hasMore": len(results) > capped,
        }

    def get_story_resource(
        self,
        workspace_id: str,
        story_id: int,
        resource_kind: str,
        resource_id: str | int,
    ) -> dict[str, Any]:
        story = self._require_story(workspace_id, story_id)
        kind = str(resource_kind)
        if kind == RESOURCE_STORY:
            if str(story.id) != str(resource_id):
                raise FileNotFoundError(f"Story resource not found: {resource_id}")
            return {
                "kind": kind,
                "resource": _jsonable(story),
            }
        state = self._load_state(workspace_id, story)
        item = state.objects.get(kind, {}).get(str(resource_id))
        if item is None:
            raise FileNotFoundError(
                f"Story resource not found: {kind}/{resource_id}"
            )
        return {
            "kind": kind,
            "resource": _jsonable(item),
            "binding": _binding_dict(
                next(
                    (
                        binding
                        for binding in state.bindings.values()
                        if binding.resource_kind == kind
                        and binding.resource_id == str(resource_id)
                    ),
                    None,
                )
            ),
        }

    # ------------------------------------------------------------------
    # Validation, comparison, preview and apply
    # ------------------------------------------------------------------

    def validate_story_pack(self, value: Mapping[str, Any]) -> dict[str, Any]:
        try:
            pack = StoryPack.model_validate(value)
        except ValidationError as exc:
            return {
                "valid": False,
                "schemaVersion": value.get("schemaVersion"),
                "errors": _validation_errors(exc),
                "warnings": [],
            }
        warnings = []
        if "visualCatalog" in pack.included_sections and pack.resources.visual_catalog:
            warnings.append(
                "Visual specifications are archived in the operation/Story Pack "
                "only; no Media Asset or generation job will be created."
            )
        if not pack.resources.openings and "openings" in pack.included_sections:
            warnings.append(
                "The openings section is empty. Merge-only import preserves "
                "existing openings and creates none."
            )
        return {
            "valid": True,
            "schemaVersion": STORY_PACK_SCHEMA_VERSION,
            "contractVersion": pack.contract_version,
            "packId": pack.pack_id,
            "packDigest": digest_json(
                pack.model_dump(by_alias=True, exclude_none=True)
            ),
            "includedSections": list(pack.included_sections),
            "errors": [],
            "warnings": warnings,
        }

    def compare_story_pack(self, value: Mapping[str, Any]) -> dict[str, Any]:
        pack = StoryPack.model_validate(value)
        return self._build_plan(pack)

    def preview_story_pack(
        self,
        value: Mapping[str, Any],
        *,
        operation_kind: str = "story_pack",
    ) -> dict[str, Any]:
        pack = StoryPack.model_validate(value)
        pack_value = pack.model_dump(by_alias=True, exclude_none=True)
        pack_digest = digest_json(pack_value)
        completed = self._services.story_packs.find_completed_operation(
            pack.target.workspace_id,
            pack.story_stable_id,
            pack_digest,
            operation_kind=str(operation_kind),
        )
        if completed is not None:
            result = self.operation_result(completed.id)
            return {
                **result,
                "alreadyApplied": True,
                "requiresConfirmation": False,
            }
        plan = self._build_plan(pack)
        operation_id = f"sp_{uuid4().hex}"
        operation = self._services.story_packs.create_operation(
            operation_id,
            operation_kind=str(operation_kind),
            project_id=pack.project_id,
            pack_id=pack.pack_id,
            pack_digest=pack_digest,
            workspace_id=pack.target.workspace_id,
            story_stable_id=pack.story_stable_id,
            story_id=plan.get("targetStoryId"),
            pack=pack_value,
            plan=plan,
        )
        return {
            **_operation_dict(operation),
            "requiresConfirmation": not bool(plan["conflicts"]),
            "confirmationInstruction": (
                "Show this preview to the user. Call the separate apply tool "
                "with operationId only after explicit confirmation."
            ),
        }

    def apply_story_pack(
        self,
        operation_id: str,
        *,
        expected_operation_kind: str | None = None,
        local_sync: Callable[[dict[str, Any]], dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        operation = self._services.story_packs.get_operation(operation_id)
        if operation is None:
            raise FileNotFoundError(
                f"Story Pack operation not found: {operation_id}"
            )
        if (
            expected_operation_kind is not None
            and operation.operation_kind != str(expected_operation_kind)
        ):
            raise StoryPackRuntimeError(
                f"operation kind is {operation.operation_kind!r}, expected "
                f"{expected_operation_kind!r}; use its matching apply tool"
            )
        if operation.status == STORY_PACK_OPERATION_LOCAL_SYNC_PENDING:
            if local_sync is None:
                return {
                    **_operation_dict(operation),
                    "recoveryInstruction": (
                        "Database changes are already committed. Retry through "
                        "all mode with a valid DesignProject root to repair only "
                        "the local integration files."
                    ),
                }
            return self._retry_local_sync(operation, local_sync)
        if operation.status == STORY_PACK_OPERATION_APPLIED:
            local_sync_state = operation.result.get("localSync")
            already_synced = (
                isinstance(local_sync_state, Mapping)
                and local_sync_state.get("completed") is True
            )
            if local_sync is not None and not already_synced:
                return self._finish_local_sync(operation, local_sync)
            return _operation_dict(operation)
        if operation.status == STORY_PACK_OPERATION_FAILED:
            raise StoryPackRuntimeError(
                f"operation is failed and requires a new preview: {operation.id}"
            )
        if operation.status != STORY_PACK_OPERATION_PREVIEWED:
            raise StoryPackRuntimeError(
                f"operation cannot be applied from status {operation.status!r}"
            )
        pack = StoryPack.model_validate(operation.pack)
        if operation.plan.get("conflicts"):
            raise StoryPackConflictError(
                "preview contains conflicts; resolve them and create a new preview"
            )
        try:
            with self._services.transaction():
                fresh_plan = self._build_plan(pack)
                if (
                    fresh_plan.get("planDigest")
                    != operation.plan.get("planDigest")
                ):
                    raise StoryPackPreviewStaleError(
                        "runtime state changed after preview; create a new preview"
                    )
                claimed = self._services.story_packs.claim_operation(operation.id)
                if claimed is None:
                    raise StoryPackRuntimeError(
                        "operation was concurrently claimed or changed"
                    )
                result = self._apply_pack(
                    pack,
                    fresh_plan,
                    operation_kind=operation.operation_kind,
                )
                completed = self._services.story_packs.complete_operation(
                    operation.id,
                    story_id=int(result["storyId"]),
                    result=result,
                )
                if completed is None:
                    raise StoryPackRuntimeError(
                        "operation completion CAS failed"
                    )
        except Exception as exc:
            self._services.story_packs.fail_operation(
                operation.id,
                error_code=(
                    "preview_stale"
                    if isinstance(exc, StoryPackPreviewStaleError)
                    else "apply_failed"
                ),
                error_message=str(exc),
            )
            raise
        completed = self._services.story_packs.get_operation(operation.id)
        if completed is None:
            raise StoryPackRuntimeError("completed operation disappeared")
        if local_sync is None:
            return _operation_dict(completed)
        return self._finish_local_sync(completed, local_sync)

    def operation_result(self, operation_id: str) -> dict[str, Any]:
        operation = self._services.story_packs.get_operation(operation_id)
        if operation is None:
            raise FileNotFoundError(
                f"Story Pack operation not found: {operation_id}"
            )
        return _operation_dict(operation)

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _build_plan(self, pack: StoryPack) -> dict[str, Any]:
        changes: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        warnings: list[str] = []
        workspace = self._services.catalog.get_workspace(
            pack.target.workspace_id
        )
        story = None
        story_binding: StoryPackBinding | None = None
        if workspace is None:
            if not pack.target.allow_create_workspace:
                conflicts.append({
                    "kind": "workspace",
                    "code": "workspace_missing",
                    "message": (
                        "Target workspace does not exist and "
                        "allowCreateWorkspace is false."
                    ),
                    "workspaceId": pack.target.workspace_id,
                })
            else:
                changes.append({
                    "kind": "workspace",
                    "sourceId": pack.target.workspace_id,
                    "action": "create",
                    "name": pack.target.workspace_name,
                })
        else:
            changes.append({
                "kind": "workspace",
                "sourceId": workspace.id,
                "resourceId": workspace.id,
                "action": "unchanged",
                "name": workspace.name,
            })
            story, story_binding, resolution_conflicts = (
                self._resolve_story(pack)
            )
            conflicts.extend(resolution_conflicts)

        story_payload = pack.story.model_dump(by_alias=True)
        story_digest = digest_json(story_payload)
        if workspace is None and pack.target.allow_create_workspace:
            changes.append({
                "kind": RESOURCE_STORY,
                "sourceId": pack.story_stable_id,
                "action": "create",
                "name": pack.story.title,
                "sourceDigest": story_digest,
            })
        elif story is None and not conflicts:
            changes.append({
                "kind": RESOURCE_STORY,
                "sourceId": pack.story_stable_id,
                "action": "create",
                "name": pack.story.title,
                "sourceDigest": story_digest,
            })
        elif story is not None:
            if story_binding is None:
                action = (
                    "adopt_update"
                    if "story" in pack.included_sections
                    else "bind"
                )
                changes.append({
                    "kind": RESOURCE_STORY,
                    "sourceId": pack.story_stable_id,
                    "resourceId": str(story.id),
                    "action": action,
                    "name": pack.story.title,
                    "sourceDigest": story_digest,
                    "expectedResourceVersion": story.version,
                })
            elif "story" not in pack.included_sections:
                changes.append({
                    "kind": RESOURCE_STORY,
                    "sourceId": pack.story_stable_id,
                    "resourceId": str(story.id),
                    "action": "unchanged",
                    "name": story.title,
                    "sourceDigest": story_binding.source_digest,
                    "expectedResourceVersion": story.version,
                })
            else:
                planned, conflict, warning = _plan_bound_resource(
                    _IncomingResource(
                        kind=RESOURCE_STORY,
                        source_id=pack.story_stable_id,
                        name=pack.story.title,
                        payload=story_payload,
                    ),
                    story_binding,
                    story,
                )
                changes.append(planned)
                if conflict is not None:
                    conflicts.append(conflict)
                if warning is not None:
                    warnings.append(warning)

        state: _RuntimeState | None = None
        if story is not None:
            state = self._load_state(pack.target.workspace_id, story)
        if story is not None or not conflicts:
            for incoming in _incoming_resources(pack):
                if incoming.kind == RESOURCE_VISUAL_SPEC:
                    changes.append({
                        "kind": incoming.kind,
                        "sourceId": incoming.source_id,
                        "action": "archive",
                        "name": incoming.name,
                        "sourceDigest": incoming.source_digest,
                    })
                    continue
                if state is None:
                    if (
                        incoming.kind == RESOURCE_NARRATIVE_STYLE
                        and workspace is not None
                    ):
                        same_name = [
                            item
                            for item in (
                                self._services.composer.list_styles(
                                    pack.target.workspace_id
                                ) or []
                            )
                            if item.name == incoming.name
                        ]
                        if same_name:
                            changes.append({
                                "kind": incoming.kind,
                                "sourceId": incoming.source_id,
                                "action": "conflict",
                                "name": incoming.name,
                                "sourceDigest": incoming.source_digest,
                            })
                            conflicts.append({
                                "kind": incoming.kind,
                                "sourceId": incoming.source_id,
                                "code": "unbound_name_collision",
                                "message": (
                                    "A workspace-owned narrative style with "
                                    "the same name exists but has no binding "
                                    "for the new Story."
                                ),
                                "candidateResourceIds": [
                                    str(item.id) for item in same_name
                                ],
                            })
                            continue
                    changes.append({
                        "kind": incoming.kind,
                        "sourceId": incoming.source_id,
                        "action": "create",
                        "name": incoming.name,
                        "sourceDigest": incoming.source_digest,
                        "parentRef": incoming.parent_ref,
                    })
                    continue
                planned, conflict, warning = self._plan_resource(
                    incoming,
                    state,
                    project_id=pack.project_id,
                )
                changes.append(planned)
                if conflict is not None:
                    conflicts.append(conflict)
                if warning is not None:
                    warnings.append(warning)

        if state is not None and "openings" in pack.included_sections:
            conflicts.extend(
                self._opening_merge_conflicts(pack, state, changes)
            )
        if (
            "statusTables" in pack.included_sections
            and "characters" not in pack.included_sections
        ):
            conflicts.extend(
                self._status_character_reference_conflicts(pack, state)
            )
        if "rpModules" in pack.included_sections:
            known_modules = {
                item.module_name
                for item in self._services.rp_module_data.list_catalog()
            }
            conflicts.extend(
                {
                    "kind": RESOURCE_RP_MODULE,
                    "sourceId": spec.module_name,
                    "code": "unknown_rp_module",
                    "message": (
                        "The Story Pack references an RP Module that is not "
                        "present in the runtime catalog."
                    ),
                }
                for spec in pack.resources.rp_modules
                if spec.module_name not in known_modules
            )
        if pack.resources.visual_catalog and "visualCatalog" in pack.included_sections:
            warnings.append(
                "Visual specifications will remain archived in the Story Pack "
                "and operation result; no media write is planned."
            )
        counts: dict[str, int] = {}
        for item in changes:
            action = str(item["action"])
            counts[action] = counts.get(action, 0) + 1
        plan_core = {
            "packId": pack.pack_id,
            "packDigest": digest_json(
                pack.model_dump(by_alias=True, exclude_none=True)
            ),
            "projectId": pack.project_id,
            "workspaceId": pack.target.workspace_id,
            "targetStoryId": int(story.id) if story is not None else None,
            "storyStableId": pack.story_stable_id,
            "includedSections": list(pack.included_sections),
            "changes": changes,
            "conflicts": conflicts,
            "warnings": sorted(set(warnings)),
            "counts": counts,
            "limitations": [
                "Story Pack v2 is merge-only and does not delete omitted resources.",
                "Visual specifications are archived and do not create media.",
                "No Session, message, Media Job, TTS Job, or binary is created.",
            ],
        }
        return {
            **plan_core,
            "planDigest": digest_json(plan_core),
        }

    def _resolve_story(
        self,
        pack: StoryPack,
    ) -> tuple[Any | None, StoryPackBinding | None, list[dict[str, Any]]]:
        workspace_id = pack.target.workspace_id
        conflicts: list[dict[str, Any]] = []
        project_bindings = [
            item
            for item in self._services.story_packs.find_bindings(
                workspace_id,
                RESOURCE_STORY,
                pack.story_stable_id,
            )
            if item.metadata.get("projectId") == pack.project_id
        ]
        if len(project_bindings) > 1:
            conflicts.append({
                "kind": RESOURCE_STORY,
                "code": "ambiguous_story_binding",
                "message": (
                    "Multiple Story bindings match this project/story stable id."
                ),
            })
            return None, None, conflicts
        bound = project_bindings[0] if project_bindings else None
        if pack.target.story_id is not None:
            story = self._services.catalog.get_story(
                workspace_id,
                int(pack.target.story_id),
            )
            if story is None:
                conflicts.append({
                    "kind": RESOURCE_STORY,
                    "code": "target_story_missing",
                    "message": (
                        f"Explicit target Story does not exist: "
                        f"{pack.target.story_id}"
                    ),
                })
                return None, None, conflicts
            if bound is not None and bound.story_id != int(story.id):
                conflicts.append({
                    "kind": RESOURCE_STORY,
                    "code": "story_binding_mismatch",
                    "message": (
                        "The project stable Story is already bound to a "
                        "different runtime Story."
                    ),
                    "boundStoryId": bound.story_id,
                    "targetStoryId": story.id,
                })
                return story, None, conflicts
            target_binding = self._services.story_packs.get_binding(
                workspace_id,
                int(story.id),
                RESOURCE_STORY,
                pack.story_stable_id,
            )
            if (
                target_binding is not None
                and target_binding.metadata.get("projectId") != pack.project_id
            ):
                conflicts.append({
                    "kind": RESOURCE_STORY,
                    "code": "story_project_binding_conflict",
                    "message": (
                        "The explicit target Story stable id is already owned "
                        "by a different Story design project."
                    ),
                    "bindingProjectId": target_binding.metadata.get("projectId"),
                })
                return story, None, conflicts
            return story, target_binding, conflicts
        if bound is not None:
            story = self._services.catalog.get_story(
                workspace_id,
                bound.story_id,
            )
            if story is None:
                conflicts.append({
                    "kind": RESOURCE_STORY,
                    "code": "bound_story_missing",
                    "message": "The Story binding points to a missing Story.",
                })
                return None, bound, conflicts
            return story, bound, conflicts
        stories = self._services.catalog.list_stories(workspace_id) or []
        title_matches = [item for item in stories if item.title == pack.story.title]
        if title_matches:
            conflicts.append({
                "kind": RESOURCE_STORY,
                "code": "unbound_story_title_collision",
                "message": (
                    "A Story with the same title exists but has no matching "
                    "stable binding. Set target.storyId explicitly to adopt it."
                ),
                "candidateStoryIds": [item.id for item in title_matches],
            })
            return None, None, conflicts
        return None, None, conflicts

    def _plan_resource(
        self,
        incoming: _IncomingResource,
        state: _RuntimeState,
        *,
        project_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        binding = state.bindings.get((incoming.kind, incoming.source_id))
        if binding is not None:
            if binding.metadata.get("projectId") != project_id:
                planned = {
                    "kind": incoming.kind,
                    "sourceId": incoming.source_id,
                    "resourceId": binding.resource_id,
                    "action": "conflict",
                    "name": incoming.name,
                    "sourceDigest": incoming.source_digest,
                    "parentRef": incoming.parent_ref,
                }
                return planned, {
                    "kind": incoming.kind,
                    "sourceId": incoming.source_id,
                    "code": "resource_project_binding_conflict",
                    "message": (
                        "The stable resource id is already owned by a "
                        "different Story design project."
                    ),
                    "bindingProjectId": binding.metadata.get("projectId"),
                }, None
            current = state.objects.get(incoming.kind, {}).get(
                binding.resource_id
            )
            if current is None:
                planned = {
                    "kind": incoming.kind,
                    "sourceId": incoming.source_id,
                    "resourceId": binding.resource_id,
                    "action": "conflict",
                    "name": incoming.name,
                    "sourceDigest": incoming.source_digest,
                    "parentRef": incoming.parent_ref,
                }
                return planned, {
                    "kind": incoming.kind,
                    "sourceId": incoming.source_id,
                    "code": "bound_resource_missing",
                    "message": "Stable binding points to a missing runtime resource.",
                    "resourceId": binding.resource_id,
                }, None
            if incoming.kind == RESOURCE_NARRATIVE_STYLE:
                return self._plan_bound_narrative_style(
                    incoming,
                    binding,
                    current,
                    state,
                )
            return _plan_bound_resource(incoming, binding, current)

        same_name = state.names.get(incoming.kind, {}).get(incoming.name, [])
        if (
            incoming.kind == RESOURCE_CHARACTER_DETAIL
            and incoming.parent_ref is not None
        ):
            parent_binding = state.bindings.get(
                (RESOURCE_CHARACTER, incoming.parent_ref)
            )
            if parent_binding is None:
                same_name = []
            else:
                same_name = [
                    item
                    for item in same_name
                    if str(item.story_character_id)
                    == parent_binding.resource_id
                ]
        if same_name and incoming.natural_identity:
            current = same_name[0]
            return {
                "kind": incoming.kind,
                "sourceId": incoming.source_id,
                "resourceId": _object_id(incoming.kind, current),
                "action": "adopt_update",
                "name": incoming.name,
                "sourceDigest": incoming.source_digest,
                "expectedResourceVersion": _object_version(current),
                "parentRef": incoming.parent_ref,
            }, None, None
        if same_name:
            return {
                "kind": incoming.kind,
                "sourceId": incoming.source_id,
                "action": "conflict",
                "name": incoming.name,
                "sourceDigest": incoming.source_digest,
                "parentRef": incoming.parent_ref,
            }, {
                "kind": incoming.kind,
                "sourceId": incoming.source_id,
                "code": "unbound_name_collision",
                "message": (
                    f"Unbound runtime {incoming.kind} with the same name "
                    f"already exists: {incoming.name}"
                ),
                "candidateResourceIds": [
                    _object_id(incoming.kind, item) for item in same_name
                ],
            }, None
        return {
            "kind": incoming.kind,
            "sourceId": incoming.source_id,
            "action": "create",
            "name": incoming.name,
            "sourceDigest": incoming.source_digest,
            "parentRef": incoming.parent_ref,
        }, None, None

    @staticmethod
    def _plan_bound_narrative_style(
        incoming: _IncomingResource,
        binding: StoryPackBinding,
        current: Any,
        state: _RuntimeState,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        current_version = _object_version(current)
        mount = next(
            (
                item
                for item in state.style_mounts
                if str(item.narrative_style_id) == binding.resource_id
            ),
            None,
        )
        baseline_mount_id = binding.metadata.get("mountId")
        baseline_mount_version = binding.metadata.get("mountVersion")
        baseline_is_base = binding.metadata.get("isBase")
        mount_changed = (
            mount is None
            or str(baseline_mount_id or "") != str(mount.id)
            or not isinstance(baseline_mount_version, int)
            or isinstance(baseline_mount_version, bool)
            or baseline_mount_version != int(mount.version)
            or not isinstance(baseline_is_base, bool)
            or baseline_is_base != bool(mount.is_base)
        )
        runtime_changed = (
            current_version != binding.resource_version or mount_changed
        )
        base = {
            "kind": incoming.kind,
            "sourceId": incoming.source_id,
            "resourceId": _object_id(incoming.kind, current),
            "name": incoming.name,
            "sourceDigest": incoming.source_digest,
            "expectedResourceVersion": current_version,
            "expectedMountVersion": (
                int(mount.version) if mount is not None else None
            ),
            "parentRef": incoming.parent_ref,
        }
        if incoming.source_digest == binding.source_digest:
            if not runtime_changed:
                return {**base, "action": "unchanged"}, None, None
            warning = (
                "Runtime narrative_style/"
                f"{incoming.source_id} or its Story mount changed after the "
                "last Story Pack, while this pack did not change that source. "
                "It will be preserved as runtime_modified."
            )
            return {**base, "action": "runtime_modified"}, None, warning
        if runtime_changed:
            conflict = {
                "kind": incoming.kind,
                "sourceId": incoming.source_id,
                "resourceId": binding.resource_id,
                "code": "concurrent_runtime_change",
                "message": (
                    "Both the Story design source and the runtime narrative "
                    "style or its Story mount changed since their last binding "
                    "baseline."
                ),
                "baselineVersion": binding.resource_version,
                "runtimeVersion": current_version,
                "baselineMountVersion": baseline_mount_version,
                "runtimeMountVersion": (
                    int(mount.version) if mount is not None else None
                ),
            }
            return {**base, "action": "conflict"}, conflict, None
        return {**base, "action": "update"}, None, None

    def _opening_merge_conflicts(
        self,
        pack: StoryPack,
        state: _RuntimeState,
        changes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        action_by_source = {
            (item["kind"], item["sourceId"]): item
            for item in changes
        }
        incoming_ids: set[str] = set()
        desired_titles: list[str] = []
        for opening in sorted(
            pack.resources.openings,
            key=lambda item: (item.sort_order, item.stable_id),
        ):
            change = action_by_source[(RESOURCE_OPENING, opening.stable_id)]
            binding = state.bindings.get(
                (RESOURCE_OPENING, opening.stable_id)
            )
            if binding is not None:
                incoming_ids.add(binding.resource_id)
            if change["action"] == "runtime_modified" and binding is not None:
                current = state.objects[RESOURCE_OPENING][binding.resource_id]
                desired_titles.append(current.title)
            else:
                desired_titles.append(opening.title)
        existing = list(state.objects.get(RESOURCE_OPENING, {}).values())
        preserved = [
            item for item in existing if str(item.id) not in incoming_ids
        ]
        desired_titles.extend(item.title for item in preserved)
        conflicts: list[dict[str, Any]] = []
        if len(desired_titles) > data_models.MAX_STORY_OPENINGS:
            conflicts.append({
                "kind": RESOURCE_OPENING,
                "code": "opening_limit_exceeded",
                "message": (
                    f"Merge would create {len(desired_titles)} openings; "
                    f"runtime supports at most {data_models.MAX_STORY_OPENINGS}."
                ),
            })
        if len(desired_titles) != len(set(desired_titles)):
            conflicts.append({
                "kind": RESOURCE_OPENING,
                "code": "opening_title_collision",
                "message": "Merged opening titles would not be unique.",
            })
        return conflicts

    def _status_character_reference_conflicts(
        self,
        pack: StoryPack,
        state: _RuntimeState | None,
    ) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        for table in pack.resources.status_tables:
            character_ref = table.character_ref
            if character_ref is None:
                continue
            binding = (
                state.bindings.get((RESOURCE_CHARACTER, character_ref))
                if state is not None
                else None
            )
            current = (
                state.objects[RESOURCE_CHARACTER].get(binding.resource_id)
                if state is not None and binding is not None
                else None
            )
            if (
                binding is not None
                and binding.metadata.get("projectId") == pack.project_id
                and current is not None
            ):
                continue
            code = "missing_character_binding"
            message = (
                "A statusTables-only pack can reference a Character from an "
                "earlier pack only when that stable Character binding exists "
                "in the target Story."
            )
            if (
                binding is not None
                and binding.metadata.get("projectId") != pack.project_id
            ):
                code = "character_project_binding_conflict"
                message = (
                    "The referenced Character stable id belongs to a different "
                    "Story design project."
                )
            elif binding is not None and current is None:
                code = "bound_character_missing"
                message = (
                    "The referenced Character binding points to a missing "
                    "runtime Character."
                )
            conflicts.append({
                "kind": RESOURCE_STATUS_TABLE,
                "sourceId": table.stable_id,
                "characterRef": character_ref,
                "code": code,
                "message": message,
            })
        return conflicts

    # ------------------------------------------------------------------
    # Atomic mutation
    # ------------------------------------------------------------------

    def _apply_pack(
        self,
        pack: StoryPack,
        plan: Mapping[str, Any],
        *,
        operation_kind: str,
    ) -> dict[str, JsonValue]:
        action_map = {
            (str(item["kind"]), str(item["sourceId"])): item
            for item in plan["changes"]
        }
        workspace_id = pack.target.workspace_id
        workspace_action = action_map[("workspace", workspace_id)]["action"]
        if workspace_action == "create":
            self._services.catalog.create_workspace(
                workspace_id,
                name=pack.target.workspace_name,
                root_path=pack.target.workspace_root,
                description=f"Created from Story design project {pack.project_id}.",
                metadata={
                    "storyDesignProjectId": pack.project_id,
                    "storyPackContractVersion": pack.contract_version,
                },
            )
        story_action = action_map[
            (RESOURCE_STORY, pack.story_stable_id)
        ]["action"]
        existing_story_id = plan.get("targetStoryId")
        existing_story = (
            self._services.catalog.get_story(
                workspace_id,
                int(existing_story_id),
            )
            if existing_story_id is not None
            else None
        )
        pre_state = (
            self._load_state(workspace_id, existing_story)
            if existing_story is not None
            else None
        )
        opening_inputs = (
            self._opening_inputs(pack, pre_state, action_map)
            if "openings" in pack.included_sections
            else None
        )
        story_metadata_json = _story_metadata_json(pack)
        if existing_story is None:
            story = self._required(
                self._services.stories.create_story(
                    workspace_id,
                    title=pack.story.title,
                    summary=pack.story.summary,
                    story_prompt=pack.story.story_prompt,
                    openings=tuple(opening_inputs or ()),
                    metadata_json=story_metadata_json,
                ),
                "created Story",
            )
        else:
            should_update_story = (
                story_action in {"update", "adopt_update"}
                or opening_inputs is not None
            )
            if should_update_story:
                story = self._required(
                    self._services.stories.update_story(
                        workspace_id,
                        int(existing_story.id),
                        title=(
                            pack.story.title
                            if "story" in pack.included_sections
                            else None
                        ),
                        summary=(
                            pack.story.summary
                            if "story" in pack.included_sections
                            else None
                        ),
                        story_prompt=(
                            pack.story.story_prompt
                            if "story" in pack.included_sections
                            else None
                        ),
                        openings=(
                            tuple(opening_inputs)
                            if opening_inputs is not None
                            else None
                        ),
                        metadata_json=(
                            story_metadata_json
                            if "story" in pack.included_sections
                            else None
                        ),
                    ),
                    "updated Story",
                )
            else:
                story = existing_story
        story = self._required(
            self._services.catalog.get_story(workspace_id, int(story.id)),
            "refreshed Story",
        )
        mapping: dict[str, dict[str, str]] = {
            kind: {} for kind in (RESOURCE_STORY, *WRITABLE_RESOURCE_KINDS)
        }
        mapping[RESOURCE_STORY][pack.story_stable_id] = str(story.id)
        story_incoming = _IncomingResource(
                kind=RESOURCE_STORY,
                source_id=pack.story_stable_id,
                name=pack.story.title,
                payload=pack.story.model_dump(by_alias=True),
        )
        story_action_value = str(
            action_map[(RESOURCE_STORY, pack.story_stable_id)]["action"]
        )
        self._upsert_binding(
            pack,
            story,
            story_incoming,
            story,
            story_action_value,
        )
        if story_action_value == "unchanged" and pre_state is not None:
            previous = pre_state.bindings.get(
                (RESOURCE_STORY, pack.story_stable_id)
            )
            if (
                previous is not None
                and previous.resource_version != int(story.version)
            ):
                self._services.story_packs.upsert_binding(
                    story.workspace_id,
                    int(story.id),
                    RESOURCE_STORY,
                    pack.story_stable_id,
                    resource_id=str(story.id),
                    source_digest=previous.source_digest,
                    resource_version=int(story.version),
                    metadata=previous.metadata,
                )
        if "openings" in pack.included_sections:
            self._bind_openings(pack, story, pre_state, action_map, mapping)

        state = self._load_state(workspace_id, story)
        self._apply_characters(pack, story, state, action_map, mapping)
        state = self._load_state(workspace_id, story)
        self._apply_lorebook(pack, story, state, action_map, mapping)
        self._apply_status(pack, story, state, action_map, mapping)
        self._apply_composer(pack, story, state, action_map, mapping)
        state = self._load_state(workspace_id, story)
        self._apply_rp_modules(pack, story, state, action_map, mapping)
        self._apply_plot(pack, story, state, action_map, mapping)

        applied_counts: dict[str, int] = {}
        for item in plan["changes"]:
            action = str(item["action"])
            applied_counts[action] = applied_counts.get(action, 0) + 1
        return {
            "operationKind": str(operation_kind),
            "packId": pack.pack_id,
            "packDigest": digest_json(
                pack.model_dump(by_alias=True, exclude_none=True)
            ),
            "projectId": pack.project_id,
            "workspaceId": workspace_id,
            "storyId": int(story.id),
            "storyStableId": pack.story_stable_id,
            "includedSections": list(pack.included_sections),
            "counts": applied_counts,
            "idMapping": mapping,
            "archivedVisualSpecifications": [
                item.model_dump(by_alias=True)
                for item in pack.resources.visual_catalog
            ] if "visualCatalog" in pack.included_sections else [],
            "warnings": list(plan["warnings"]),
            "localSync": {"completed": False},
            "appliedAt": utc_now(),
        }

    def _opening_inputs(
        self,
        pack: StoryPack,
        state: _RuntimeState | None,
        action_map: Mapping[tuple[str, str], Mapping[str, Any]],
    ) -> list[data_models.StoryOpeningInput]:
        if state is None:
            return [
                data_models.StoryOpeningInput(
                    title=item.title,
                    message=item.message,
                )
                for item in sorted(
                    pack.resources.openings,
                    key=lambda value: (value.sort_order, value.stable_id),
                )
            ]
        values: list[data_models.StoryOpeningInput] = []
        referenced_ids: set[str] = set()
        for item in sorted(
            pack.resources.openings,
            key=lambda value: (value.sort_order, value.stable_id),
        ):
            binding = state.bindings.get((RESOURCE_OPENING, item.stable_id))
            action = action_map[(RESOURCE_OPENING, item.stable_id)]["action"]
            if binding is None:
                values.append(data_models.StoryOpeningInput(
                    title=item.title,
                    message=item.message,
                ))
                continue
            current = state.objects[RESOURCE_OPENING][binding.resource_id]
            referenced_ids.add(binding.resource_id)
            if action == "runtime_modified":
                values.append(data_models.StoryOpeningInput(
                    id=int(current.id),
                    title=current.title,
                    message=current.message,
                ))
            else:
                values.append(data_models.StoryOpeningInput(
                    id=int(current.id),
                    title=item.title,
                    message=item.message,
                ))
        for current in sorted(
            state.objects.get(RESOURCE_OPENING, {}).values(),
            key=lambda item: (item.sort_order, item.id),
        ):
            if str(current.id) in referenced_ids:
                continue
            values.append(data_models.StoryOpeningInput(
                id=int(current.id),
                title=current.title,
                message=current.message,
            ))
        return values

    def _bind_openings(
        self,
        pack: StoryPack,
        story: Any,
        pre_state: _RuntimeState | None,
        action_map: Mapping[tuple[str, str], Mapping[str, Any]],
        mapping: dict[str, dict[str, str]],
    ) -> None:
        by_title = {item.title: item for item in story.openings}
        by_id = {str(item.id): item for item in story.openings}
        for spec in pack.resources.openings:
            action = str(action_map[(RESOURCE_OPENING, spec.stable_id)]["action"])
            old_binding = (
                pre_state.bindings.get((RESOURCE_OPENING, spec.stable_id))
                if pre_state is not None
                else None
            )
            current = (
                by_id.get(old_binding.resource_id)
                if old_binding is not None
                else by_title.get(spec.title)
            )
            if current is None:
                raise StoryPackRuntimeError(
                    f"cannot resolve imported Opening: {spec.stable_id}"
                )
            mapping[RESOURCE_OPENING][spec.stable_id] = str(current.id)
            self._upsert_binding(
                pack,
                story,
                _IncomingResource(
                    kind=RESOURCE_OPENING,
                    source_id=spec.stable_id,
                    name=spec.title,
                    payload=spec.model_dump(by_alias=True),
                ),
                current,
                action,
            )

    def _apply_characters(
        self,
        pack: StoryPack,
        story: Any,
        state: _RuntimeState,
        action_map: Mapping[tuple[str, str], Mapping[str, Any]],
        mapping: dict[str, dict[str, str]],
    ) -> None:
        if "characters" not in pack.included_sections:
            return
        character_objects: dict[str, Any] = {}
        for spec in pack.resources.characters:
            payload = spec.model_dump(by_alias=True)
            payload.pop("details", None)
            incoming = _IncomingResource(
                kind=RESOURCE_CHARACTER,
                source_id=spec.stable_id,
                name=spec.name,
                payload=payload,
            )
            action = str(action_map[(incoming.kind, incoming.source_id)]["action"])
            current = self._bound_current(state, incoming)
            metadata = {
                **spec.metadata,
                "stableId": spec.stable_id,
                "storyDesignProjectId": pack.project_id,
                "aliases": list(spec.aliases),
                "visual": dict(spec.visual),
            }
            if action == "create":
                current = self._required(
                    self._services.characters.create_character(
                        story.workspace_id,
                        int(story.id),
                        name=spec.name,
                        description=spec.description,
                        sort_order=spec.sort_order,
                        metadata=metadata,
                    ),
                    f"character {spec.stable_id}",
                )
            elif action in {"update", "adopt_update"}:
                current = self._required(
                    self._services.characters.update_character(
                        story.workspace_id,
                        int(story.id),
                        int(current.id),
                        name=spec.name,
                        description=spec.description,
                        sort_order=spec.sort_order,
                        metadata=metadata,
                    ),
                    f"character {spec.stable_id}",
                )
            if current is None:
                raise StoryPackRuntimeError(
                    f"cannot resolve character {spec.stable_id}"
                )
            character_objects[spec.stable_id] = current
            mapping[RESOURCE_CHARACTER][spec.stable_id] = str(current.id)
            self._upsert_binding(pack, story, incoming, current, action)

        refreshed = self._load_state(story.workspace_id, story)
        for character in pack.resources.characters:
            parent = character_objects[character.stable_id]
            for spec in character.details:
                payload = {
                    **spec.model_dump(by_alias=True),
                    "characterRef": character.stable_id,
                }
                incoming = _IncomingResource(
                    kind=RESOURCE_CHARACTER_DETAIL,
                    source_id=spec.stable_id,
                    name=spec.name,
                    payload=payload,
                    parent_ref=character.stable_id,
                )
                action = str(
                    action_map[(incoming.kind, incoming.source_id)]["action"]
                )
                current = self._bound_current(refreshed, incoming)
                if action == "create":
                    current = self._required(
                        self._services.characters.create_detail(
                            story.workspace_id,
                            int(story.id),
                            int(parent.id),
                            name=spec.name,
                            content=spec.content,
                            tags=spec.tags,
                            sort_order=spec.sort_order,
                        ),
                        f"character detail {spec.stable_id}",
                    )
                elif action in {"update", "adopt_update"}:
                    current = self._required(
                        self._services.characters.update_detail(
                            story.workspace_id,
                            int(story.id),
                            int(parent.id),
                            int(current.id),
                            name=spec.name,
                            content=spec.content,
                            tags=spec.tags,
                            sort_order=spec.sort_order,
                        ),
                        f"character detail {spec.stable_id}",
                    )
                if current is None:
                    raise StoryPackRuntimeError(
                        f"cannot resolve character detail {spec.stable_id}"
                    )
                mapping[RESOURCE_CHARACTER_DETAIL][spec.stable_id] = str(
                    current.id
                )
                self._upsert_binding(pack, story, incoming, current, action)

    def _apply_lorebook(
        self,
        pack: StoryPack,
        story: Any,
        state: _RuntimeState,
        action_map: Mapping[tuple[str, str], Mapping[str, Any]],
        mapping: dict[str, dict[str, str]],
    ) -> None:
        if "lorebook" not in pack.included_sections:
            return
        for spec in pack.resources.lorebook:
            incoming = _IncomingResource(
                kind=RESOURCE_LOREBOOK,
                source_id=spec.stable_id,
                name=spec.name,
                payload=spec.model_dump(by_alias=True),
            )
            action = str(action_map[(incoming.kind, incoming.source_id)]["action"])
            current = self._bound_current(state, incoming)
            metadata = {
                **spec.metadata,
                "stableId": spec.stable_id,
                "storyDesignProjectId": pack.project_id,
                "visual": dict(spec.visual),
            }
            if action == "create":
                current = self._required(
                    self._services.lorebook.create_entry(
                        story.workspace_id,
                        int(story.id),
                        name=spec.name,
                        content=spec.content,
                        description=spec.description,
                        tags=spec.tags,
                        sort_order=spec.sort_order,
                        metadata=metadata,
                    ),
                    f"lorebook entry {spec.stable_id}",
                )
            elif action in {"update", "adopt_update"}:
                current = self._required(
                    self._services.lorebook.update_entry(
                        story.workspace_id,
                        int(story.id),
                        int(current.id),
                        name=spec.name,
                        content=spec.content,
                        description=spec.description,
                        tags=spec.tags,
                        sort_order=spec.sort_order,
                        metadata=metadata,
                    ),
                    f"lorebook entry {spec.stable_id}",
                )
            if current is None:
                raise StoryPackRuntimeError(
                    f"cannot resolve lorebook entry {spec.stable_id}"
                )
            mapping[RESOURCE_LOREBOOK][spec.stable_id] = str(current.id)
            self._upsert_binding(pack, story, incoming, current, action)

    def _apply_status(
        self,
        pack: StoryPack,
        story: Any,
        state: _RuntimeState,
        action_map: Mapping[tuple[str, str], Mapping[str, Any]],
        mapping: dict[str, dict[str, str]],
    ) -> None:
        if "statusTables" not in pack.included_sections:
            return
        for spec in pack.resources.status_tables:
            incoming = _IncomingResource(
                kind=RESOURCE_STATUS_TABLE,
                source_id=spec.stable_id,
                name=spec.name,
                payload=spec.model_dump(by_alias=True),
            )
            action = str(action_map[(incoming.kind, incoming.source_id)]["action"])
            current = self._bound_current(state, incoming)
            character_id = None
            if spec.character_ref is not None:
                character_id = self._resource_id_for_source(
                    state,
                    mapping,
                    RESOURCE_CHARACTER,
                    spec.character_ref,
                )
            document = StatusTableDocument.from_rows(
                rows=[
                    StatusTableRow(
                        key=row.key,
                        value=row.value,
                        runtime_key_locked=row.runtime_key_locked,
                        update_rule=row.update_rule,
                        metadata=row.metadata,
                    )
                    for row in spec.rows
                ],
                metadata={
                    **spec.metadata,
                    "stableId": spec.stable_id,
                    "storyDesignProjectId": pack.project_id,
                },
            )
            metadata_json = json.dumps(
                {
                    **spec.metadata,
                    "stableId": spec.stable_id,
                    "storyDesignProjectId": pack.project_id,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if action == "create":
                current = self._services.status.create_story_table(
                    story.workspace_id,
                    int(story.id),
                    spec.name,
                    status_kind=spec.status_kind,
                    story_character_id=character_id,
                    document=document,
                    description=spec.description,
                    sort_order=spec.sort_order,
                    metadata_json=metadata_json,
                )
            elif action in {"update", "adopt_update"}:
                current = self._services.status.update_story_table(
                    story.workspace_id,
                    int(story.id),
                    int(current.id),
                    name=spec.name,
                    status_kind=spec.status_kind,
                    story_character_id=character_id,
                    update_story_character=True,
                    document=document,
                    description=spec.description,
                    sort_order=spec.sort_order,
                    metadata_json=metadata_json,
                )
            if current is None:
                raise StoryPackRuntimeError(
                    f"cannot resolve status table {spec.stable_id}"
                )
            mapping[RESOURCE_STATUS_TABLE][spec.stable_id] = str(current.id)
            self._upsert_binding(pack, story, incoming, current, action)

    def _apply_composer(
        self,
        pack: StoryPack,
        story: Any,
        state: _RuntimeState,
        action_map: Mapping[tuple[str, str], Mapping[str, Any]],
        mapping: dict[str, dict[str, str]],
    ) -> None:
        if "composer" not in pack.included_sections:
            return
        style_objects: dict[str, Any] = {}
        style_incoming: dict[str, _IncomingResource] = {}
        style_actions: dict[str, str] = {}
        for spec in pack.resources.narrative_styles:
            incoming = _IncomingResource(
                kind=RESOURCE_NARRATIVE_STYLE,
                source_id=spec.stable_id,
                name=spec.name,
                payload=spec.model_dump(by_alias=True),
            )
            action = str(action_map[(incoming.kind, incoming.source_id)]["action"])
            style_incoming[spec.stable_id] = incoming
            style_actions[spec.stable_id] = action
            current = self._bound_current(state, incoming)
            if action == "create":
                current = self._required(
                    self._services.composer.create_style(
                        story.workspace_id,
                        name=spec.name,
                        prompt=spec.prompt,
                        sort_order=spec.sort_order,
                    ),
                    f"narrative style {spec.stable_id}",
                )
            elif action in {"update", "adopt_update"}:
                current = self._required(
                    self._services.composer.update_style(
                        story.workspace_id,
                        int(current.id),
                        name=spec.name,
                        prompt=spec.prompt,
                        sort_order=spec.sort_order,
                    ),
                    f"narrative style {spec.stable_id}",
                )
            if current is None:
                raise StoryPackRuntimeError(
                    f"cannot resolve narrative style {spec.stable_id}"
                )
            style_objects[spec.stable_id] = current
            mapping[RESOURCE_NARRATIVE_STYLE][spec.stable_id] = str(current.id)
        mounts = self._services.composer.list_story_styles(
            story.workspace_id,
            int(story.id),
        ) or []
        mounted_by_style = {
            int(item.narrative_style_id): item for item in mounts
        }
        for spec in pack.resources.narrative_styles:
            style = style_objects[spec.stable_id]
            if (
                style_actions[spec.stable_id]
                in {"create", "update", "adopt_update"}
                and int(style.id) not in mounted_by_style
            ):
                mount = self._required(
                    self._services.composer.mount_story_style(
                        story.workspace_id,
                        int(story.id),
                        int(style.id),
                    ),
                    f"narrative style mount {spec.stable_id}",
                )
                mounted_by_style[int(style.id)] = mount
        base = next(
            (item for item in pack.resources.narrative_styles if item.is_base),
            None,
        )
        if (
            base is not None
            and style_actions[base.stable_id]
            in {"create", "update", "adopt_update"}
        ):
            style = style_objects[base.stable_id]
            mount = mounted_by_style[int(style.id)]
            self._services.composer.set_story_base_style(
                story.workspace_id,
                int(story.id),
                int(mount.id),
            )
        elif any(
            mount.is_base
            and any(
                int(style_objects[spec.stable_id].id)
                == int(mount.narrative_style_id)
                and not spec.is_base
                and style_actions[spec.stable_id]
                in {"create", "update", "adopt_update"}
                for spec in pack.resources.narrative_styles
            )
            for mount in mounts
        ):
            self._services.composer.set_story_base_style(
                story.workspace_id,
                int(story.id),
                None,
            )
        final_mounts = {
            int(item.narrative_style_id): item
            for item in (
                self._services.composer.list_story_styles(
                    story.workspace_id,
                    int(story.id),
                )
                or []
            )
        }
        for spec in pack.resources.narrative_styles:
            action = style_actions[spec.stable_id]
            if action not in {"create", "update", "adopt_update"}:
                continue
            style = style_objects[spec.stable_id]
            mount = self._required(
                final_mounts.get(int(style.id)),
                f"narrative style mount {spec.stable_id}",
            )
            self._upsert_binding(
                pack,
                story,
                style_incoming[spec.stable_id],
                style,
                action,
                metadata={
                    "mountId": int(mount.id),
                    "mountVersion": int(mount.version),
                    "isBase": bool(mount.is_base),
                },
            )

        for spec in pack.resources.quick_replies:
            incoming = _IncomingResource(
                kind=RESOURCE_QUICK_REPLY,
                source_id=spec.stable_id,
                name=spec.title,
                payload=spec.model_dump(by_alias=True),
            )
            action = str(action_map[(incoming.kind, incoming.source_id)]["action"])
            current = self._bound_current(state, incoming)
            if action == "create":
                current = self._required(
                    self._services.composer.create_quick_reply(
                        story.workspace_id,
                        int(story.id),
                        title=spec.title,
                        message=spec.message,
                        sort_order=spec.sort_order,
                        enabled=spec.enabled,
                    ),
                    f"quick reply {spec.stable_id}",
                )
            elif action in {"update", "adopt_update"}:
                current = self._required(
                    self._services.composer.update_quick_reply(
                        story.workspace_id,
                        int(story.id),
                        int(current.id),
                        title=spec.title,
                        message=spec.message,
                        sort_order=spec.sort_order,
                        enabled=spec.enabled,
                    ),
                    f"quick reply {spec.stable_id}",
                )
            if current is None:
                raise StoryPackRuntimeError(
                    f"cannot resolve quick reply {spec.stable_id}"
                )
            mapping[RESOURCE_QUICK_REPLY][spec.stable_id] = str(current.id)
            self._upsert_binding(pack, story, incoming, current, action)

    def _apply_rp_modules(
        self,
        pack: StoryPack,
        story: Any,
        state: _RuntimeState,
        action_map: Mapping[tuple[str, str], Mapping[str, Any]],
        mapping: dict[str, dict[str, str]],
    ) -> None:
        if "rpModules" not in pack.included_sections:
            return
        for spec in pack.resources.rp_modules:
            incoming = _IncomingResource(
                kind=RESOURCE_RP_MODULE,
                source_id=spec.module_name,
                name=spec.module_name,
                payload=spec.model_dump(by_alias=True),
                natural_identity=True,
            )
            action = str(action_map[(incoming.kind, incoming.source_id)]["action"])
            if action in {"create", "update", "adopt_update"}:
                self._required(
                    self._services.rp_modules.patch_story_module(
                        story.workspace_id,
                        int(story.id),
                        spec.module_name,
                        enabled=spec.enabled,
                        config=spec.config,
                    ),
                    f"RP module {spec.module_name}",
                )
            current = self._required(
                self._services.rp_module_data.get_story_module(
                    story.workspace_id,
                    int(story.id),
                    spec.module_name,
                ),
                f"RP module row {spec.module_name}",
            )
            mapping[RESOURCE_RP_MODULE][spec.module_name] = spec.module_name
            self._upsert_binding(pack, story, incoming, current, action)

    def _apply_plot(
        self,
        pack: StoryPack,
        story: Any,
        state: _RuntimeState,
        action_map: Mapping[tuple[str, str], Mapping[str, Any]],
        mapping: dict[str, dict[str, str]],
    ) -> None:
        if "plotSchedule" not in pack.included_sections:
            return
        pools: dict[str, Any] = {}
        for spec in pack.resources.plot_schedule.pools:
            incoming = _IncomingResource(
                kind=RESOURCE_PLOT_POOL,
                source_id=spec.stable_id,
                name=spec.name,
                payload=spec.model_dump(by_alias=True),
            )
            action = str(action_map[(incoming.kind, incoming.source_id)]["action"])
            current = self._bound_current(state, incoming)
            if action == "create":
                current = self._services.plot.create_pool(CreatePlotPoolCommand(
                    workspace_id=story.workspace_id,
                    story_id=int(story.id),
                    name=spec.name,
                    description=spec.description,
                    selection_mode=spec.selection_mode,
                    priority=spec.priority,
                    enabled=spec.enabled,
                ))
            elif action in {"update", "adopt_update"}:
                current = self._services.plot.update_pool(UpdatePlotPoolCommand(
                    workspace_id=story.workspace_id,
                    story_id=int(story.id),
                    pool_id=int(current.id),
                    name=spec.name,
                    description=spec.description,
                    selection_mode=spec.selection_mode,
                    priority=spec.priority,
                    enabled=spec.enabled,
                ))
            if current is None:
                raise StoryPackRuntimeError(
                    f"cannot resolve plot pool {spec.stable_id}"
                )
            pools[spec.stable_id] = current
            mapping[RESOURCE_PLOT_POOL][spec.stable_id] = str(current.id)
            self._upsert_binding(pack, story, incoming, current, action)

        events: dict[str, Any] = {}
        for spec in pack.resources.plot_schedule.events:
            incoming = _IncomingResource(
                kind=RESOURCE_PLOT_EVENT,
                source_id=spec.stable_id,
                name=spec.title,
                payload=spec.model_dump(by_alias=True),
                parent_ref=spec.pool_ref,
            )
            action = str(action_map[(incoming.kind, incoming.source_id)]["action"])
            current = self._bound_current(state, incoming)
            pool = pools.get(spec.pool_ref)
            if pool is None:
                pool_id = self._resource_id_for_source(
                    state,
                    mapping,
                    RESOURCE_PLOT_POOL,
                    spec.pool_ref,
                )
            else:
                pool_id = int(pool.id)
            if action == "create":
                current = self._services.plot.create_event(
                    CreatePlotEventCommand(
                        workspace_id=story.workspace_id,
                        story_id=int(story.id),
                        pool_id=int(pool_id),
                        title=spec.title,
                        directive=spec.directive,
                        description=spec.description,
                        suitability_hint=spec.suitability_hint,
                        dispatch_mode=spec.dispatch_mode,
                        scheduled_time=(
                            SceneTime.parse(spec.scheduled_time)
                            if spec.scheduled_time is not None
                            else None
                        ),
                        deadline_time=(
                            SceneTime.parse(spec.deadline_time)
                            if spec.deadline_time is not None
                            else None
                        ),
                        position=spec.position,
                        enabled=spec.enabled,
                        allow_repeat=spec.allow_repeat,
                        repeat_cooldown_minutes=spec.repeat_cooldown_minutes,
                    )
                )
            elif action in {"update", "adopt_update"}:
                current = self._services.plot.update_event(
                    UpdatePlotEventCommand(
                        workspace_id=story.workspace_id,
                        story_id=int(story.id),
                        event_id=int(current.id),
                        pool_id=int(pool_id),
                        title=spec.title,
                        directive=spec.directive,
                        description=spec.description,
                        suitability_hint=spec.suitability_hint,
                        dispatch_mode=spec.dispatch_mode,
                        scheduled_time=(
                            SceneTime.parse(spec.scheduled_time)
                            if spec.scheduled_time is not None
                            else None
                        ),
                        deadline_time=(
                            SceneTime.parse(spec.deadline_time)
                            if spec.deadline_time is not None
                            else None
                        ),
                        position=spec.position,
                        enabled=spec.enabled,
                        allow_repeat=spec.allow_repeat,
                        repeat_cooldown_minutes=spec.repeat_cooldown_minutes,
                    )
                )
            if current is None:
                raise StoryPackRuntimeError(
                    f"cannot resolve plot event {spec.stable_id}"
                )
            events[spec.stable_id] = current
            mapping[RESOURCE_PLOT_EVENT][spec.stable_id] = str(current.id)
            self._upsert_binding(pack, story, incoming, current, action)

        outlines: dict[str, Any] = {}
        for spec in pack.resources.plot_schedule.outlines:
            payload = spec.model_dump(by_alias=True)
            payload.pop("nodes", None)
            incoming = _IncomingResource(
                kind=RESOURCE_PLOT_OUTLINE,
                source_id=spec.stable_id,
                name=spec.name,
                payload=payload,
            )
            action = str(action_map[(incoming.kind, incoming.source_id)]["action"])
            current = self._bound_current(state, incoming)
            if action == "create":
                current = self._services.plot.create_outline(
                    CreatePlotOutlineCommand(
                        workspace_id=story.workspace_id,
                        story_id=int(story.id),
                        name=spec.name,
                        description=spec.description,
                        priority=spec.priority,
                        enabled=spec.enabled,
                    )
                )
            elif action in {"update", "adopt_update"}:
                current = self._services.plot.update_outline(
                    UpdatePlotOutlineCommand(
                        workspace_id=story.workspace_id,
                        story_id=int(story.id),
                        outline_id=int(current.id),
                        name=spec.name,
                        description=spec.description,
                        priority=spec.priority,
                        enabled=spec.enabled,
                    )
                )
            if current is None:
                raise StoryPackRuntimeError(
                    f"cannot resolve plot outline {spec.stable_id}"
                )
            outlines[spec.stable_id] = current
            mapping[RESOURCE_PLOT_OUTLINE][spec.stable_id] = str(current.id)
            self._upsert_binding(pack, story, incoming, current, action)

        for outline_spec in pack.resources.plot_schedule.outlines:
            outline = outlines[outline_spec.stable_id]
            for spec in outline_spec.nodes:
                payload = {
                    **spec.model_dump(by_alias=True),
                    "outlineRef": outline_spec.stable_id,
                }
                incoming = _IncomingResource(
                    kind=RESOURCE_PLOT_NODE,
                    source_id=spec.stable_id,
                    name=spec.stable_id,
                    payload=payload,
                    parent_ref=outline_spec.stable_id,
                )
                action = str(
                    action_map[(incoming.kind, incoming.source_id)]["action"]
                )
                current = self._bound_current(state, incoming)
                event = events.get(spec.event_ref)
                event_id = (
                    int(event.id)
                    if event is not None
                    else self._resource_id_for_source(
                        state,
                        mapping,
                        RESOURCE_PLOT_EVENT,
                        spec.event_ref,
                    )
                )
                if action == "create":
                    current = self._services.plot.create_node(
                        CreatePlotNodeCommand(
                            workspace_id=story.workspace_id,
                            story_id=int(story.id),
                            outline_id=int(outline.id),
                            event_id=int(event_id),
                            scheduled_time=SceneTime.parse(spec.scheduled_time),
                            dispatch_mode=spec.dispatch_mode,
                            position=spec.position,
                            enabled=spec.enabled,
                        )
                    )
                elif action in {"update", "adopt_update"}:
                    current = self._services.plot.update_node(
                        UpdatePlotNodeCommand(
                            workspace_id=story.workspace_id,
                            story_id=int(story.id),
                            outline_id=int(outline.id),
                            node_id=int(current.id),
                            event_id=int(event_id),
                            scheduled_time=SceneTime.parse(spec.scheduled_time),
                            dispatch_mode=spec.dispatch_mode,
                            position=spec.position,
                            enabled=spec.enabled,
                        )
                    )
                if current is None:
                    raise StoryPackRuntimeError(
                        f"cannot resolve plot node {spec.stable_id}"
                    )
                mapping[RESOURCE_PLOT_NODE][spec.stable_id] = str(current.id)
                self._upsert_binding(pack, story, incoming, current, action)

    # ------------------------------------------------------------------
    # Snapshot export
    # ------------------------------------------------------------------

    def export_story_snapshot(
        self,
        workspace_id: str,
        story_id: int,
    ) -> dict[str, Any]:
        story = self._require_story(workspace_id, story_id)
        state = self._load_state(workspace_id, story)
        bindings_by_resource = {
            (item.resource_kind, item.resource_id): item
            for item in state.bindings.values()
        }

        def stable(kind: str, resource_id: str | int) -> str:
            binding = bindings_by_resource.get((kind, str(resource_id)))
            return (
                binding.source_id
                if binding is not None
                else f"runtime-{kind.replace('_', '-')}-{resource_id}"
            )

        characters = []
        character_stable_by_id: dict[int, str] = {}
        for item in sorted(
            state.objects[RESOURCE_CHARACTER].values(),
            key=lambda value: (value.sort_order, value.id),
        ):
            source_id = stable(RESOURCE_CHARACTER, item.id)
            character_stable_by_id[int(item.id)] = source_id
            details = [
                detail
                for detail in state.objects[RESOURCE_CHARACTER_DETAIL].values()
                if int(detail.story_character_id) == int(item.id)
            ]
            metadata = _json_object(item.metadata_json)
            characters.append({
                "stableId": source_id,
                "name": item.name,
                "description": item.description,
                "aliases": metadata.get("aliases", []),
                "details": [
                    {
                        "stableId": stable(RESOURCE_CHARACTER_DETAIL, detail.id),
                        "name": detail.name,
                        "content": detail.content,
                        "tags": _json_list(detail.tags_json),
                        "sortOrder": detail.sort_order,
                    }
                    for detail in sorted(
                        details,
                        key=lambda value: (value.sort_order, value.id),
                    )
                ],
                "visual": metadata.get("visual", {}),
                "sortOrder": item.sort_order,
                "metadata": _without_internal_metadata(metadata),
            })
        lorebook = []
        for item in sorted(
            state.objects[RESOURCE_LOREBOOK].values(),
            key=lambda value: (value.sort_order, value.id),
        ):
            metadata = _json_object(item.metadata_json)
            lorebook.append({
                "stableId": stable(RESOURCE_LOREBOOK, item.id),
                "name": item.name,
                "content": item.content,
                "description": item.description,
                "tags": _json_list(item.tags_json),
                "visual": metadata.get("visual", {}),
                "sortOrder": item.sort_order,
                "metadata": _without_internal_metadata(metadata),
            })
        status_tables = []
        for item in sorted(
            state.objects[RESOURCE_STATUS_TABLE].values(),
            key=lambda value: (value.sort_order, value.id),
        ):
            character_ref = (
                character_stable_by_id.get(int(item.story_character_id))
                if item.story_character_id is not None
                else None
            )
            status_tables.append({
                "stableId": stable(RESOURCE_STATUS_TABLE, item.id),
                "name": item.name,
                "statusKind": item.status_kind,
                "characterRef": character_ref,
                "description": item.description,
                "rows": [
                    row.to_json_dict() for row in item.document.rows
                ],
                "sortOrder": item.sort_order,
                "metadata": _without_internal_metadata(
                    dict(item.document.metadata)
                ),
            })
        style_mount_by_id = {
            int(item.narrative_style_id): item for item in state.style_mounts
        }
        styles = []
        for style_id, mount in sorted(
            style_mount_by_id.items(),
            key=lambda pair: (pair[1].sort_order, pair[0]),
        ):
            item = state.objects[RESOURCE_NARRATIVE_STYLE][str(style_id)]
            styles.append({
                "stableId": stable(RESOURCE_NARRATIVE_STYLE, style_id),
                "name": item.name,
                "prompt": item.prompt,
                "isBase": mount.is_base,
                "sortOrder": item.sort_order,
            })
        quick_replies = [
            {
                "stableId": stable(RESOURCE_QUICK_REPLY, item.id),
                "title": item.title,
                "message": item.message,
                "enabled": item.enabled,
                "sortOrder": item.sort_order,
            }
            for item in sorted(
                state.objects[RESOURCE_QUICK_REPLY].values(),
                key=lambda value: (value.sort_order, value.id),
            )
        ]
        modules = [
            {
                "moduleName": item.module_name,
                "enabled": item.enabled,
                "config": dict(item.config),
            }
            for item in sorted(
                state.objects[RESOURCE_RP_MODULE].values(),
                key=lambda value: value.module_name,
            )
        ]
        schedule = self._snapshot_plot(state, stable)
        story_binding = state.bindings.get(
            (RESOURCE_STORY, next(
                (
                    binding.source_id
                    for binding in state.bindings.values()
                    if binding.resource_kind == RESOURCE_STORY
                    and binding.resource_id == str(story.id)
                ),
                "",
            ))
        )
        story_stable_id = (
            story_binding.source_id
            if story_binding is not None
            else f"runtime-story-{story.id}"
        )
        project_id = (
            str(story_binding.metadata.get("projectId"))
            if story_binding is not None
            and story_binding.metadata.get("projectId")
            else f"runtime-workspace-{workspace_id}"
        )
        workspace = self._services.catalog.get_workspace(workspace_id)
        assert workspace is not None
        story_metadata = _json_object(story.metadata_json)
        archived_story_design = story_metadata.pop(
            STORY_RUNTIME_METADATA_KEY,
            {},
        )
        if not isinstance(archived_story_design, dict):
            archived_story_design = {}
        document = {
            "schemaVersion": STORY_DESIGN_SCHEMA_VERSION,
            "project": {
                "projectId": project_id,
                "name": story.title,
                "language": "zh-CN",
                "phase": "runtime_synced",
            },
            "target": {
                "workspaceId": workspace_id,
                "workspaceName": workspace.name,
                "workspaceRoot": workspace.root_path,
                "storyId": int(story.id),
                "allowCreateWorkspace": False,
            },
            "story": {
                "stableId": story_stable_id,
                "title": story.title,
                "summary": story.summary,
                "storyPrompt": story.story_prompt,
                "timeSetting": str(
                    archived_story_design.get("timeSetting", "")
                ),
                "logline": str(archived_story_design.get("logline", "")),
                "themes": _string_values(
                    archived_story_design.get("themes")
                ),
                "boundaries": _string_values(
                    archived_story_design.get("boundaries")
                ),
                "metadata": story_metadata,
            },
            "resources": {
                "openings": [
                    {
                        "stableId": stable(RESOURCE_OPENING, item.id),
                        "title": item.title,
                        "message": item.message,
                        "sortOrder": item.sort_order,
                    }
                    for item in story.openings
                ],
                "characters": characters,
                "lorebook": lorebook,
                "statusTables": status_tables,
                "narrativeStyles": styles,
                "quickReplies": quick_replies,
                "rpModules": modules,
                "plotSchedule": schedule,
                "visualCatalog": [],
            },
            "decisions": [],
            "openQuestions": [],
            "sources": [],
            "notes": [
                "Exported from RPG World runtime; visual catalog is not stored "
                "in runtime and is therefore empty."
            ],
        }
        return {
            "schemaVersion": "rpg-story-snapshot/1.0",
            "exportedAt": utc_now(),
            "workspaceId": workspace_id,
            "storyId": int(story.id),
            "designDocument": document,
            "bindings": [
                _binding_dict(item)
                for item in sorted(
                    state.bindings.values(),
                    key=lambda value: (
                        value.resource_kind,
                        value.source_id,
                    ),
                )
            ],
        }

    # ------------------------------------------------------------------
    # State and shared helpers
    # ------------------------------------------------------------------

    def _load_state(self, workspace_id: str, story: Any) -> _RuntimeState:
        objects: dict[str, dict[str, Any]] = {
            kind: {} for kind in WRITABLE_RESOURCE_KINDS
        }
        for item in story.openings:
            objects[RESOURCE_OPENING][str(item.id)] = item
        characters = self._services.characters.list_characters(
            workspace_id,
            int(story.id),
        ) or []
        for item in characters:
            objects[RESOURCE_CHARACTER][str(item.id)] = item
            for detail in self._services.characters.list_details(
                workspace_id,
                int(story.id),
                int(item.id),
            ) or []:
                objects[RESOURCE_CHARACTER_DETAIL][str(detail.id)] = detail
        for item in self._services.lorebook.list_entries(
            workspace_id,
            int(story.id),
        ) or []:
            objects[RESOURCE_LOREBOOK][str(item.id)] = item
        for item in self._services.status.list_story_tables(
            workspace_id,
            int(story.id),
        ):
            objects[RESOURCE_STATUS_TABLE][str(item.id)] = item
        for item in self._services.composer.list_styles(workspace_id) or []:
            objects[RESOURCE_NARRATIVE_STYLE][str(item.id)] = item
        for item in self._services.composer.list_quick_replies(
            workspace_id,
            int(story.id),
        ) or []:
            objects[RESOURCE_QUICK_REPLY][str(item.id)] = item
        for item in self._services.rp_module_data.list_story_modules(
            workspace_id,
            int(story.id),
        ) or []:
            objects[RESOURCE_RP_MODULE][str(item.module_name)] = item
        schedule = self._services.plot.get_story_schedule(
            workspace_id,
            int(story.id),
        )
        if schedule is not None:
            for item in schedule.pools:
                objects[RESOURCE_PLOT_POOL][str(item.id)] = item
            for item in schedule.events:
                objects[RESOURCE_PLOT_EVENT][str(item.id)] = item
            for outline in schedule.outlines:
                objects[RESOURCE_PLOT_OUTLINE][str(outline.id)] = outline
                for node in outline.nodes:
                    objects[RESOURCE_PLOT_NODE][str(node.id)] = node
        names: dict[str, dict[str, list[Any]]] = {}
        for kind, values in objects.items():
            grouped: dict[str, list[Any]] = {}
            for item in values.values():
                grouped.setdefault(_object_name(kind, item), []).append(item)
            names[kind] = grouped
        bindings = {
            (item.resource_kind, item.source_id): item
            for item in self._services.story_packs.list_bindings(
                workspace_id,
                int(story.id),
            )
        }
        return _RuntimeState(
            story=story,
            objects=objects,
            names=names,
            bindings=bindings,
            style_mounts=self._services.composer.list_story_styles(
                workspace_id,
                int(story.id),
            ) or [],
        )

    def _bound_current(
        self,
        state: _RuntimeState,
        incoming: _IncomingResource,
    ) -> Any | None:
        binding = state.bindings.get((incoming.kind, incoming.source_id))
        if binding is not None:
            return state.objects.get(incoming.kind, {}).get(binding.resource_id)
        if incoming.natural_identity:
            same_name = state.names.get(incoming.kind, {}).get(
                incoming.name,
                [],
            )
            return same_name[0] if same_name else None
        return None

    def _upsert_binding(
        self,
        pack: StoryPack,
        story: Any,
        incoming: _IncomingResource,
        current: Any,
        action: str,
        *,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> None:
        if action in {"unchanged", "runtime_modified"}:
            return
        self._services.story_packs.upsert_binding(
            story.workspace_id,
            int(story.id),
            incoming.kind,
            incoming.source_id,
            resource_id=_object_id(incoming.kind, current),
            source_digest=incoming.source_digest,
            resource_version=_object_version(current),
            metadata={
                "projectId": pack.project_id,
                "packId": pack.pack_id,
                "parentRef": incoming.parent_ref,
                **dict(metadata or {}),
            },
        )

    def _resource_id_for_source(
        self,
        state: _RuntimeState,
        mapping: Mapping[str, Mapping[str, str]],
        kind: str,
        source_id: str,
    ) -> int:
        mapped = mapping.get(kind, {}).get(source_id)
        if mapped is not None:
            return int(mapped)
        binding = state.bindings.get((kind, source_id))
        if binding is None:
            raise StoryPackRuntimeError(
                f"missing resource binding for {kind}/{source_id}"
            )
        return int(binding.resource_id)

    def _snapshot_plot(
        self,
        state: _RuntimeState,
        stable: Callable[[str, str | int], str],
    ) -> dict[str, Any]:
        pools = [
            {
                "stableId": stable(RESOURCE_PLOT_POOL, item.id),
                "name": item.name,
                "description": item.description,
                "selectionMode": item.selection_mode,
                "priority": item.priority,
                "enabled": item.enabled,
            }
            for item in sorted(
                state.objects[RESOURCE_PLOT_POOL].values(),
                key=lambda value: (-value.priority, value.id),
            )
        ]
        pool_ref_by_id = {
            int(item.id): stable(RESOURCE_PLOT_POOL, item.id)
            for item in state.objects[RESOURCE_PLOT_POOL].values()
        }
        events = [
            {
                "stableId": stable(RESOURCE_PLOT_EVENT, item.id),
                "poolRef": pool_ref_by_id[int(item.pool_id)],
                "title": item.title,
                "directive": item.directive,
                "description": item.description,
                "suitabilityHint": item.suitability_hint,
                "dispatchMode": item.dispatch_mode,
                "scheduledTime": (
                    item.scheduled_time.format()
                    if item.scheduled_time is not None
                    else None
                ),
                "deadlineTime": (
                    item.deadline_time.format()
                    if item.deadline_time is not None
                    else None
                ),
                "position": item.position,
                "enabled": item.enabled,
                "allowRepeat": item.allow_repeat,
                "repeatCooldownMinutes": item.repeat_cooldown_minutes,
            }
            for item in sorted(
                state.objects[RESOURCE_PLOT_EVENT].values(),
                key=lambda value: (value.pool_id, value.position, value.id),
            )
        ]
        event_ref_by_id = {
            int(item.id): stable(RESOURCE_PLOT_EVENT, item.id)
            for item in state.objects[RESOURCE_PLOT_EVENT].values()
        }
        outlines = []
        for item in sorted(
            state.objects[RESOURCE_PLOT_OUTLINE].values(),
            key=lambda value: (-value.priority, value.id),
        ):
            outlines.append({
                "stableId": stable(RESOURCE_PLOT_OUTLINE, item.id),
                "name": item.name,
                "description": item.description,
                "priority": item.priority,
                "enabled": item.enabled,
                "nodes": [
                    {
                        "stableId": stable(RESOURCE_PLOT_NODE, node.id),
                        "eventRef": event_ref_by_id[int(node.event_id)],
                        "scheduledTime": node.scheduled_time.format(),
                        "dispatchMode": node.dispatch_mode,
                        "position": node.position,
                        "enabled": node.enabled,
                    }
                    for node in sorted(
                        item.nodes,
                        key=lambda value: (value.position, value.id),
                    )
                ],
            })
        return {"pools": pools, "events": events, "outlines": outlines}

    def _require_story(self, workspace_id: str, story_id: int) -> Any:
        return self._required(
            self._services.catalog.get_story(str(workspace_id), int(story_id)),
            f"Story {workspace_id}/{story_id}",
        )

    @staticmethod
    def _required(value: Any | None, label: str) -> Any:
        if value is None:
            raise FileNotFoundError(f"{label} not found")
        return value

    def _finish_local_sync(
        self,
        operation: StoryPackOperation,
        local_sync: Callable[[dict[str, Any]], dict[str, str]],
    ) -> dict[str, Any]:
        try:
            paths = local_sync(_operation_dict(operation))
        except Exception as exc:
            pending = self._services.story_packs.mark_local_sync_pending(
                operation.id,
                error_message=str(exc),
            )
            if pending is None:
                raise StoryPackRuntimeError(
                    "database applied but local-sync pending transition failed"
                ) from exc
            return {
                **_operation_dict(pending),
                "recoveryInstruction": (
                    "Database changes are committed. Fix the DesignProject "
                    "path/files and retry this same operationId; do not preview "
                    "or apply the pack again."
                ),
            }
        result = {
            **dict(operation.result),
            "localSync": {"completed": True, **paths},
        }
        updated = self._services.story_packs.update_applied_result(
            operation.id,
            result=result,
        )
        if updated is None:
            raise StoryPackRuntimeError(
                "local files were written but operation result update failed"
            )
        return _operation_dict(updated)

    def _retry_local_sync(
        self,
        operation: StoryPackOperation,
        local_sync: Callable[[dict[str, Any]], dict[str, str]],
    ) -> dict[str, Any]:
        try:
            paths = local_sync({
                **_operation_dict(operation),
                "status": STORY_PACK_OPERATION_APPLIED,
                "errorCode": "",
                "errorMessage": "",
            })
        except Exception as exc:
            return {
                **_operation_dict(operation),
                "recoveryError": str(exc),
            }
        result = {
            **dict(operation.result),
            "localSync": {"completed": True, **paths},
        }
        updated = self._services.story_packs.mark_local_sync_complete(
            operation.id,
            result=result,
        )
        if updated is None:
            latest = self._services.story_packs.get_operation(operation.id)
            local_sync_state = (
                latest.result.get("localSync")
                if latest is not None
                else None
            )
            if (
                latest is not None
                and latest.status == STORY_PACK_OPERATION_APPLIED
                and isinstance(local_sync_state, Mapping)
                and local_sync_state.get("completed") is True
            ):
                return _operation_dict(latest)
            raise StoryPackRuntimeError(
                "local-sync recovery CAS failed"
            )
        return _operation_dict(updated)


def _incoming_resources(pack: StoryPack) -> list[_IncomingResource]:
    values: list[_IncomingResource] = []
    sections = set(pack.included_sections)
    if "openings" in sections:
        values.extend(
            _IncomingResource(
                kind=RESOURCE_OPENING,
                source_id=item.stable_id,
                name=item.title,
                payload=item.model_dump(by_alias=True),
            )
            for item in pack.resources.openings
        )
    if "characters" in sections:
        for item in pack.resources.characters:
            payload = item.model_dump(by_alias=True)
            payload.pop("details", None)
            values.append(_IncomingResource(
                kind=RESOURCE_CHARACTER,
                source_id=item.stable_id,
                name=item.name,
                payload=payload,
            ))
            values.extend(
                _IncomingResource(
                    kind=RESOURCE_CHARACTER_DETAIL,
                    source_id=detail.stable_id,
                    name=detail.name,
                    payload={
                        **detail.model_dump(by_alias=True),
                        "characterRef": item.stable_id,
                    },
                    parent_ref=item.stable_id,
                )
                for detail in item.details
            )
    if "lorebook" in sections:
        values.extend(
            _IncomingResource(
                kind=RESOURCE_LOREBOOK,
                source_id=item.stable_id,
                name=item.name,
                payload=item.model_dump(by_alias=True),
            )
            for item in pack.resources.lorebook
        )
    if "statusTables" in sections:
        values.extend(
            _IncomingResource(
                kind=RESOURCE_STATUS_TABLE,
                source_id=item.stable_id,
                name=item.name,
                payload=item.model_dump(by_alias=True),
            )
            for item in pack.resources.status_tables
        )
    if "composer" in sections:
        values.extend(
            _IncomingResource(
                kind=RESOURCE_NARRATIVE_STYLE,
                source_id=item.stable_id,
                name=item.name,
                payload=item.model_dump(by_alias=True),
            )
            for item in pack.resources.narrative_styles
        )
        values.extend(
            _IncomingResource(
                kind=RESOURCE_QUICK_REPLY,
                source_id=item.stable_id,
                name=item.title,
                payload=item.model_dump(by_alias=True),
            )
            for item in pack.resources.quick_replies
        )
    if "rpModules" in sections:
        values.extend(
            _IncomingResource(
                kind=RESOURCE_RP_MODULE,
                source_id=item.module_name,
                name=item.module_name,
                payload=item.model_dump(by_alias=True),
                natural_identity=True,
            )
            for item in pack.resources.rp_modules
        )
    if "plotSchedule" in sections:
        values.extend(
            _IncomingResource(
                kind=RESOURCE_PLOT_POOL,
                source_id=item.stable_id,
                name=item.name,
                payload=item.model_dump(by_alias=True),
            )
            for item in pack.resources.plot_schedule.pools
        )
        values.extend(
            _IncomingResource(
                kind=RESOURCE_PLOT_EVENT,
                source_id=item.stable_id,
                name=item.title,
                payload=item.model_dump(by_alias=True),
                parent_ref=item.pool_ref,
            )
            for item in pack.resources.plot_schedule.events
        )
        for outline in pack.resources.plot_schedule.outlines:
            payload = outline.model_dump(by_alias=True)
            payload.pop("nodes", None)
            values.append(_IncomingResource(
                kind=RESOURCE_PLOT_OUTLINE,
                source_id=outline.stable_id,
                name=outline.name,
                payload=payload,
            ))
            values.extend(
                _IncomingResource(
                    kind=RESOURCE_PLOT_NODE,
                    source_id=node.stable_id,
                    name=node.stable_id,
                    payload={
                        **node.model_dump(by_alias=True),
                        "outlineRef": outline.stable_id,
                    },
                    parent_ref=outline.stable_id,
                )
                for node in outline.nodes
            )
    if "visualCatalog" in sections:
        values.extend(
            _IncomingResource(
                kind=RESOURCE_VISUAL_SPEC,
                source_id=item.stable_id,
                name=item.title,
                payload=item.model_dump(by_alias=True),
            )
            for item in pack.resources.visual_catalog
        )
    return values


def _plan_bound_resource(
    incoming: _IncomingResource,
    binding: StoryPackBinding,
    current: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    current_version = _object_version(current)
    base = {
        "kind": incoming.kind,
        "sourceId": incoming.source_id,
        "resourceId": _object_id(incoming.kind, current),
        "name": incoming.name,
        "sourceDigest": incoming.source_digest,
        "expectedResourceVersion": current_version,
        "parentRef": incoming.parent_ref,
    }
    if incoming.source_digest == binding.source_digest:
        if current_version == binding.resource_version:
            return {**base, "action": "unchanged"}, None, None
        warning = (
            f"Runtime {incoming.kind}/{incoming.source_id} changed after the "
            "last Story Pack, while this pack did not change that source. It "
            "will be preserved as runtime_modified."
        )
        return {**base, "action": "runtime_modified"}, None, warning
    if current_version != binding.resource_version:
        conflict = {
            "kind": incoming.kind,
            "sourceId": incoming.source_id,
            "resourceId": binding.resource_id,
            "code": "concurrent_runtime_change",
            "message": (
                "Both the Story design source and runtime resource changed "
                "since their last binding baseline."
            ),
            "baselineVersion": binding.resource_version,
            "runtimeVersion": current_version,
        }
        return {**base, "action": "conflict"}, conflict, None
    return {**base, "action": "update"}, None, None


def _object_id(kind: str, value: Any) -> str:
    if kind == RESOURCE_RP_MODULE:
        return str(value.module_name)
    return str(value.id)


def _object_version(value: Any) -> int:
    try:
        version = value.version
    except AttributeError as exc:
        raise StoryPackRuntimeError(
            f"runtime resource lacks a version field: {value!r}"
        ) from exc
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise StoryPackRuntimeError(
            f"runtime resource lacks a positive version: {value!r}"
        )
    return version


def _object_name(kind: str, value: Any) -> str:
    if kind in {RESOURCE_OPENING, RESOURCE_QUICK_REPLY, RESOURCE_PLOT_EVENT}:
        return str(value.title)
    if kind == RESOURCE_RP_MODULE:
        return str(value.module_name)
    if kind == RESOURCE_PLOT_NODE:
        return str(value.id)
    return str(value.name)


def _object_summary(kind: str, value: Any) -> str:
    if kind == RESOURCE_CHARACTER:
        return str(value.description)
    if kind == RESOURCE_LOREBOOK:
        return str(value.description)
    if kind == RESOURCE_STATUS_TABLE:
        return str(value.description)
    if kind == RESOURCE_OPENING:
        return str(value.message)[:240]
    if kind == RESOURCE_QUICK_REPLY:
        return str(value.message)[:240]
    if kind == RESOURCE_PLOT_EVENT:
        return str(value.description or value.directive)[:240]
    if kind == RESOURCE_PLOT_OUTLINE:
        return str(value.description)
    return ""


def _operation_dict(operation: StoryPackOperation) -> dict[str, Any]:
    return {
        "operationId": operation.id,
        "operationKind": operation.operation_kind,
        "status": operation.status,
        "projectId": operation.project_id,
        "packId": operation.pack_id,
        "packDigest": operation.pack_digest,
        "workspaceId": operation.workspace_id,
        "storyStableId": operation.story_stable_id,
        "storyId": operation.story_id,
        "plan": dict(operation.plan),
        "result": dict(operation.result),
        "errorCode": operation.error_code,
        "errorMessage": operation.error_message,
        "version": operation.version,
        "createdAt": operation.created_at,
        "updatedAt": operation.updated_at,
        "appliedAt": operation.applied_at,
    }


def _binding_dict(
    binding: StoryPackBinding | None,
) -> dict[str, Any] | None:
    if binding is None:
        return None
    return {
        "workspaceId": binding.workspace_id,
        "storyId": binding.story_id,
        "resourceKind": binding.resource_kind,
        "sourceId": binding.source_id,
        "resourceId": binding.resource_id,
        "sourceDigest": binding.source_digest,
        "resourceVersion": binding.resource_version,
        "metadata": dict(binding.metadata),
        "version": binding.version,
    }


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, SceneTime):
        return value.format()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _story_metadata_json(pack: StoryPack) -> str:
    value = {
        **pack.story.metadata,
        STORY_RUNTIME_METADATA_KEY: {
            "projectId": pack.project_id,
            "storyStableId": pack.story_stable_id,
            "timeSetting": pack.story.time_setting,
            "logline": pack.story.logline,
            "themes": list(pack.story.themes),
            "boundaries": list(pack.story.boundaries),
        },
    }
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _string_values(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _without_internal_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if key not in {
            "stableId",
            "storyDesignProjectId",
            "aliases",
            "visual",
        }
    }


def _validation_errors(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(item) for item in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    ]


__all__ = [
    "RuntimeApplication",
    "StoryPackConflictError",
    "StoryPackPreviewStaleError",
    "StoryPackRuntimeError",
]
