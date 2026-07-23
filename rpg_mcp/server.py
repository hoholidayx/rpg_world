"""Mode-scoped MCP tool registration.

The runtime composition is imported lazily so design mode cannot initialize
or import RPG World business/data modules.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from rpg_mcp.contracts import StoryDesignDocument, build_story_pack
from rpg_mcp.design_store import DesignProjectStore


MCP_INSTRUCTIONS = (
    "Resume Story design with story_design_get_resume_context before editing. "
    "Persist confirmed decisions through expected-head CAS. Never apply RPG "
    "runtime changes without first showing the separate preview to the user "
    "and receiving explicit confirmation; apply tools intentionally accept an "
    "opaque operation id instead of a confirmation boolean. Story Pack v1 is "
    "merge-only, one-Story-per-pack, and never deletes omitted resources. "
    "Character, lorebook, and status resources are Story-owned. Visual specs "
    "are archived only and never create media jobs."
)


def _annotations(
    *,
    read_only: bool,
    destructive: bool = False,
    idempotent: bool | None = None,
) -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=False,
    )


@dataclass
class ServerBundle:
    server: FastMCP
    close: Callable[[], None]


def build_server(
    *,
    mode: Literal["design", "runtime", "all"],
    project_root: str | Path | None = None,
    db_path: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ServerBundle:
    if mode not in {"design", "runtime", "all"}:
        raise ValueError(f"unsupported MCP mode: {mode}")
    store = (
        DesignProjectStore(project_root or ".")
        if mode in {"design", "all"}
        else None
    )
    runtime_composition = None
    runtime = None
    if mode in {"runtime", "all"}:
        module = importlib.import_module("rpg_mcp.composition")
        runtime_composition = module.build_runtime_composition(db_path)
        runtime = runtime_composition.application
    server = FastMCP(
        name="rpg-world",
        instructions=MCP_INSTRUCTIONS,
        host=str(host),
        port=int(port),
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=False,
        log_level="INFO",
    )
    if store is not None:
        _register_design_tools(server, store)
    if runtime is not None:
        _register_runtime_tools(
            server,
            runtime,
            project_root=(
                Path(project_root).expanduser().resolve()
                if project_root is not None
                else None
            ),
            store=store,
        )
    if mode == "all":
        assert store is not None and runtime is not None
        _register_all_tools(server, store, runtime)

    def close() -> None:
        if runtime_composition is not None:
            runtime_composition.close()

    return ServerBundle(server=server, close=close)


def _register_design_tools(
    server: FastMCP,
    store: DesignProjectStore,
) -> None:
    @server.tool(
        name="story_design_get_project",
        title="Get Story design project",
        description="Read portable project identity, current head, and paths.",
        annotations=_annotations(read_only=True),
    )
    def get_project() -> dict[str, Any]:
        return store.get_project()

    @server.tool(
        name="story_design_get_resume_context",
        title="Resume Story design",
        description=(
            "Read the compact durable context required to continue after a "
            "new session or context compression."
        ),
        annotations=_annotations(read_only=True),
    )
    def get_resume_context(recent_decisions: int = 12) -> dict[str, Any]:
        return store.get_resume_context(recent_decisions=recent_decisions)

    @server.tool(
        name="story_design_get_section",
        title="Read Story design section",
        description="Read one JSON Pointer section from the current design.",
        annotations=_annotations(read_only=True),
    )
    def get_section(pointer: str) -> dict[str, Any]:
        return store.get_section(pointer)

    @server.tool(
        name="story_design_patch",
        title="Save confirmed Story design changes",
        description=(
            "Apply add/replace/remove/test JSON Patch operations and create one "
            "immutable revision. expected_head is mandatory CAS protection."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=False,
            idempotent=False,
        ),
    )
    def patch(
        expected_head: str,
        operations: list[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        return store.patch(
            expected_head=expected_head,
            operations=operations,
            reason=reason,
        )

    @server.tool(
        name="story_design_create_checkpoint",
        title="Create Story design checkpoint",
        description=(
            "Create an immutable named pointer to the current design revision."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=False,
            idempotent=False,
        ),
    )
    def create_checkpoint(
        name: str,
        expected_head: str,
        note: str = "",
    ) -> dict[str, Any]:
        return store.create_checkpoint(
            name,
            expected_head=expected_head,
            note=note,
        )

    @server.tool(
        name="story_design_list_history",
        title="List Story design history",
        description="List immutable revisions and named checkpoints.",
        annotations=_annotations(read_only=True),
    )
    def list_history(limit: int = 50) -> dict[str, Any]:
        return store.list_history(limit=limit)

    @server.tool(
        name="story_design_diff_revisions",
        title="Diff Story design revisions",
        description="Return a unified JSON diff between two immutable revisions.",
        annotations=_annotations(read_only=True),
    )
    def diff_revisions(
        from_revision: str,
        to_revision: str,
    ) -> dict[str, Any]:
        return store.diff_revisions(from_revision, to_revision)

    @server.tool(
        name="story_design_restore_revision",
        title="Restore Story design revision",
        description=(
            "Create a new head whose document equals an older revision; old "
            "history remains immutable."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=True,
            idempotent=False,
        ),
    )
    def restore_revision(
        revision_id: str,
        expected_head: str,
        reason: str,
    ) -> dict[str, Any]:
        return store.restore_revision(
            revision_id,
            expected_head=expected_head,
            reason=reason,
        )

    @server.tool(
        name="story_design_validate",
        title="Validate Story design",
        description="Validate the current or selected immutable revision.",
        annotations=_annotations(read_only=True),
    )
    def validate(revision_id: str | None = None) -> dict[str, Any]:
        return store.validate(revision_id)

    @server.tool(
        name="story_design_build_pack",
        title="Build Story Pack",
        description=(
            "Build an immutable full or section-scoped, merge-only Story Pack "
            "from the current expected head."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=False,
            idempotent=True,
        ),
    )
    def build_pack(
        expected_head: str,
        included_sections: list[str] | None = None,
        target_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return store.build_pack(
            expected_head=expected_head,
            included_sections=included_sections,
            target_overrides=target_overrides,
        )

    @server.tool(
        name="story_design_doctor",
        title="Check Story design project",
        description=(
            "Read-only integrity, portability, revision-chain, and contract check."
        ),
        annotations=_annotations(read_only=True),
    )
    def doctor() -> dict[str, Any]:
        return store.doctor()


def _register_runtime_tools(
    server: FastMCP,
    runtime: Any,
    *,
    project_root: Path | None,
    store: DesignProjectStore | None,
) -> None:
    @server.tool(
        name="rpg_list_workspaces",
        title="List RPG World workspaces",
        description="List enabled runtime workspaces.",
        annotations=_annotations(read_only=True),
    )
    def list_workspaces() -> dict[str, Any]:
        return runtime.list_workspaces()

    @server.tool(
        name="rpg_list_stories",
        title="List RPG World Stories",
        description="List Stories owned by one runtime workspace.",
        annotations=_annotations(read_only=True),
    )
    def list_stories(workspace_id: str) -> dict[str, Any]:
        return runtime.list_stories(workspace_id)

    @server.tool(
        name="rpg_search_story_resources",
        title="Search Story resources",
        description=(
            "Search Story-owned character, lorebook, status, composer, RP "
            "module, and plot resources."
        ),
        annotations=_annotations(read_only=True),
    )
    def search_story_resources(
        workspace_id: str,
        story_id: int,
        query: str = "",
        kinds: list[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return runtime.search_story_resources(
            workspace_id,
            story_id,
            query=query,
            kinds=kinds,
            limit=limit,
        )

    @server.tool(
        name="rpg_get_story_resource",
        title="Get Story resource",
        description="Read one runtime Story resource and its stable binding.",
        annotations=_annotations(read_only=True),
    )
    def get_story_resource(
        workspace_id: str,
        story_id: int,
        resource_kind: str,
        resource_id: str,
    ) -> dict[str, Any]:
        return runtime.get_story_resource(
            workspace_id,
            story_id,
            resource_kind,
            resource_id,
        )

    @server.tool(
        name="rpg_validate_story_pack",
        title="Validate Story Pack",
        description=(
            "Validate Story Pack v1 without creating a preview or changing "
            "runtime business data."
        ),
        annotations=_annotations(read_only=True),
    )
    def validate_story_pack(
        pack: dict[str, Any] | None = None,
        pack_path: str | None = None,
    ) -> dict[str, Any]:
        return runtime.validate_story_pack(
            _load_pack(pack, pack_path, project_root)
        )

    @server.tool(
        name="rpg_preview_story_pack",
        title="Preview Story Pack import",
        description=(
            "Persist a non-destructive preview ledger with per-resource create, "
            "update, drift, conflict, and archive actions."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=False,
            idempotent=False,
        ),
    )
    def preview_story_pack(
        pack: dict[str, Any] | None = None,
        pack_path: str | None = None,
    ) -> dict[str, Any]:
        return runtime.preview_story_pack(
            _load_pack(pack, pack_path, project_root),
            operation_kind="story_pack",
        )

    @server.tool(
        name="rpg_apply_story_pack",
        title="Apply confirmed Story Pack",
        description=(
            "Apply a previously previewed operation id atomically. Call only "
            "after the user explicitly confirms the separate preview."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=True,
            idempotent=True,
        ),
    )
    def apply_story_pack(operation_id: str) -> dict[str, Any]:
        return runtime.apply_story_pack(
            operation_id,
            expected_operation_kind="story_pack",
        )

    @server.tool(
        name="rpg_preview_changes",
        title="Preview Story changes",
        description=(
            "Preview a section-scoped Story Pack as a generic runtime change set."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=False,
            idempotent=False,
        ),
    )
    def preview_changes(
        pack: dict[str, Any] | None = None,
        pack_path: str | None = None,
    ) -> dict[str, Any]:
        return runtime.preview_story_pack(
            _load_pack(pack, pack_path, project_root),
            operation_kind="changes",
        )

    @server.tool(
        name="rpg_apply_changes",
        title="Apply confirmed Story changes",
        description=(
            "Apply a generic previewed change operation after explicit user "
            "confirmation."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=True,
            idempotent=True,
        ),
    )
    def apply_changes(operation_id: str) -> dict[str, Any]:
        return runtime.apply_story_pack(
            operation_id,
            expected_operation_kind="changes",
        )

    @server.tool(
        name="rpg_export_story_snapshot",
        title="Export Story snapshot",
        description=(
            "Export a neutral Story design snapshot. Optionally save it under "
            "the configured DesignProject without changing runtime data."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=False,
            idempotent=True,
        ),
    )
    def export_story_snapshot(
        workspace_id: str,
        story_id: int,
        save_to_project: bool = False,
    ) -> dict[str, Any]:
        snapshot = runtime.export_story_snapshot(workspace_id, story_id)
        if save_to_project:
            if store is None:
                raise ValueError(
                    "save_to_project requires --mode all and a DesignProject"
                )
            snapshot = {
                **snapshot,
                "artifact": store.write_runtime_snapshot(snapshot),
            }
        return snapshot

    @server.tool(
        name="rpg_get_operation_result",
        title="Get Story Pack operation",
        description=(
            "Read the persistent preview/apply/local-sync operation truth."
        ),
        annotations=_annotations(read_only=True),
    )
    def get_operation_result(operation_id: str) -> dict[str, Any]:
        return runtime.operation_result(operation_id)


def _register_all_tools(
    server: FastMCP,
    store: DesignProjectStore,
    runtime: Any,
) -> None:
    @server.tool(
        name="story_design_compare_runtime",
        title="Compare Story design with runtime",
        description=(
            "Build an in-memory pack from the current head and compare it with "
            "runtime without writing a pack or preview ledger."
        ),
        annotations=_annotations(read_only=True),
    )
    def compare_runtime(
        included_sections: list[str] | None = None,
        target_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = store.get_current()
        document = StoryDesignDocument.model_validate(current["document"])
        pack = build_story_pack(
            document,
            source_revision=current["revision"],
            source_digest=current["headDigest"],
            included_sections=included_sections,
            target_overrides=target_overrides,
        )
        return runtime.compare_story_pack(
            pack.model_dump(by_alias=True, exclude_none=True)
        )

    @server.tool(
        name="story_design_preview_runtime_sync",
        title="Preview design-to-runtime sync",
        description=(
            "Build an immutable Story Pack artifact and persist a runtime sync "
            "preview. This does not apply Story business changes."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=False,
            idempotent=False,
        ),
    )
    def preview_runtime_sync(
        expected_head: str,
        included_sections: list[str] | None = None,
        target_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        built = store.build_pack(
            expected_head=expected_head,
            included_sections=included_sections,
            target_overrides=target_overrides,
        )
        preview = runtime.preview_story_pack(
            built["pack"],
            operation_kind="runtime_sync",
        )
        return {**preview, "storyPackArtifact": built["path"]}

    @server.tool(
        name="story_design_apply_runtime_sync",
        title="Apply confirmed design-to-runtime sync",
        description=(
            "Apply a previously previewed runtime sync after explicit user "
            "confirmation, then update portable integration/report files."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=True,
            idempotent=True,
        ),
    )
    def apply_runtime_sync(operation_id: str) -> dict[str, Any]:
        return runtime.apply_story_pack(
            operation_id,
            expected_operation_kind="runtime_sync",
            local_sync=store.write_runtime_integration,
        )

    @server.tool(
        name="story_design_reconcile_from_runtime",
        title="Reconcile design from runtime",
        description=(
            "Export runtime Story state and create a new design revision that "
            "replaces target/story/resources while preserving design history."
        ),
        annotations=_annotations(
            read_only=False,
            destructive=True,
            idempotent=False,
        ),
    )
    def reconcile_from_runtime(
        workspace_id: str,
        story_id: int,
        expected_head: str,
        reason: str,
    ) -> dict[str, Any]:
        snapshot = runtime.export_story_snapshot(workspace_id, story_id)
        artifact = store.write_runtime_snapshot(snapshot)
        document = snapshot["designDocument"]
        result = store.patch(
            expected_head=expected_head,
            reason=reason,
            operations=[
                {
                    "op": "replace",
                    "path": "/target",
                    "value": document["target"],
                },
                {
                    "op": "replace",
                    "path": "/story",
                    "value": document["story"],
                },
                {
                    "op": "replace",
                    "path": "/resources",
                    "value": document["resources"],
                },
                {
                    "op": "add",
                    "path": "/notes/-",
                    "value": (
                        f"Reconciled from runtime {workspace_id}/{story_id} "
                        f"at {snapshot['exportedAt']}."
                    ),
                },
            ],
        )
        return {**result, "snapshotArtifact": artifact}


def _load_pack(
    pack: Mapping[str, Any] | None,
    pack_path: str | None,
    project_root: Path | None,
) -> dict[str, Any]:
    if (pack is None) == (pack_path is None):
        raise ValueError("provide exactly one of pack or pack_path")
    if pack is not None:
        return dict(pack)
    if project_root is None:
        raise ValueError(
            "pack_path requires a configured --project-root; pass pack inline "
            "in runtime-only mode"
        )
    relative = Path(str(pack_path))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("pack_path must be a safe project-relative path")
    path = (project_root / relative).resolve()
    try:
        path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("pack_path escapes the DesignProject root") from exc
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Story Pack file must contain one JSON object")
    return value


__all__ = ["MCP_INSTRUCTIONS", "ServerBundle", "build_server"]
