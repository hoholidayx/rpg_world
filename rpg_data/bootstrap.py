"""Runtime bootstrap helpers for catalog-backed workspace files."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from peewee import Database

from rpg_data.repositories.records import (
    SessionRecord,
    SessionStatusTableRecord,
    StoryRecord,
    StatusTableTemplateRecord,
    WorkspaceRecord,
    bind_database,
)
from rpg_data.settings import (
    get_bootstrap_delete_orphan_dirs,
    resolve_workspace_relative_path,
    resolve_workspace_root,
)

__all__ = [
    "bootstrap_runtime_data",
    "delete_unindexed_runtime_item",
    "delete_unindexed_runtime_items",
    "scan_orphan_runtime_data",
    "scan_unindexed_runtime_data",
]

logger = logging.getLogger("rpg_data.bootstrap")

_TEMPLATE_STATUS_DIR = "template_status"
_STORIES_DIR = "stories"
_STATUS_FILE_PATTERN = "*.status.json"


def bootstrap_runtime_data(database: Database) -> None:
    """Align SQL file indexes with workspace directories and status JSON files.

    SQL remains the complete index. Bootstrap does not discover status tables
    from directories, does not create business records, and does not rebuild
    missing status table content from SQL metadata.
    """

    bind_database(database)
    logger.info("runtime bootstrap started")
    workspace_roots, workspace_count = _ensure_workspace_roots()
    orphan_dirs_removed = _cleanup_orphan_runtime_dirs(workspace_roots)
    unindexed_status_files_removed = _cleanup_unindexed_status_files(workspace_roots)
    missing_template_file_count = _check_template_files(workspace_roots)
    session_copy_count = _ensure_session_copies(database)
    missing_session_file_count = _check_session_files(workspace_roots)
    logger.info(
        "runtime bootstrap finished workspace_count=%s missing_template_files=%s "
        "sessions_initialized=%s missing_session_files=%s orphan_dirs_removed=%s "
        "unindexed_status_files_removed=%s",
        workspace_count,
        missing_template_file_count,
        session_copy_count,
        missing_session_file_count,
        orphan_dirs_removed,
        unindexed_status_files_removed,
    )


def scan_orphan_runtime_data(database: Database) -> dict[str, list[dict[str, str]]]:
    """Return runtime directories/status JSON files not indexed by SQL.

    This is a read-only companion for operational tooling. It intentionally
    reuses the same index rules as bootstrap cleanup, but never deletes files.
    """

    bind_database(database)
    workspace_roots = _workspace_roots_from_index()
    return {
        "orphan_directories": _scan_orphan_runtime_dirs(workspace_roots),
        "unindexed_status_files": _scan_unindexed_status_files(workspace_roots),
    }


def scan_unindexed_runtime_data(database: Database, workspace_id: str) -> dict[str, list[dict[str, str]]] | None:
    """Return workspace-scoped runtime items that are not indexed by SQL."""

    bind_database(database)
    workspace_roots = _workspace_roots_from_index()
    if workspace_id not in workspace_roots:
        return None
    scan = scan_orphan_runtime_data(database)
    items = [
        _unindexed_item("runtime_directory", item)
        for item in scan["orphan_directories"]
        if item.get("workspace_id") == workspace_id and item.get("kind") != "workspace"
    ]
    items.extend(
        _unindexed_item("status_json", item)
        for item in scan["unindexed_status_files"]
        if item.get("workspace_id") == workspace_id
    )
    return {"items": items}


def delete_unindexed_runtime_item(database: Database, item: dict[str, str]) -> bool | None:
    """Delete a scanned workspace-scoped unindexed runtime item.

    Returns ``None`` when the workspace is missing, ``False`` when the item no
    longer matches the current scan, and ``True`` when deletion succeeds.
    """

    bind_database(database)
    workspace_id = str(item.get("workspace_id", ""))
    workspace_roots = _workspace_roots_from_index()
    if workspace_id not in workspace_roots:
        return None
    scan = scan_unindexed_runtime_data(database, workspace_id)
    if scan is None:
        return None
    match = _find_unindexed_item(scan["items"], item)
    if match is None:
        return False

    return _delete_unindexed_runtime_match(workspace_roots, workspace_id, match)


def delete_unindexed_runtime_items(database: Database, items: list[dict[str, str]]) -> bool | None:
    """Delete scanned workspace-scoped unindexed runtime items as one operation."""

    bind_database(database)
    targets = _dedupe_unindexed_items(items)
    if not targets:
        return False
    workspace_id = str(targets[0].get("workspace_id", ""))
    if any(str(item.get("workspace_id", "")) != workspace_id for item in targets):
        return False

    workspace_roots = _workspace_roots_from_index()
    if workspace_id not in workspace_roots:
        return None
    scan = scan_unindexed_runtime_data(database, workspace_id)
    if scan is None:
        return None
    matches: list[dict[str, str]] = []
    for target in targets:
        match = _find_unindexed_item(scan["items"], target)
        if match is None:
            return False
        matches.append(match)

    for match in matches:
        if not _delete_unindexed_runtime_match(workspace_roots, workspace_id, match):
            return False
    return True


def _delete_unindexed_runtime_match(
    workspace_roots: dict[str, Path],
    workspace_id: str,
    match: dict[str, str],
) -> bool:
    path = Path(str(match["path"]))
    if match["category"] == "runtime_directory":
        return _remove_orphan_dir(
            path,
            kind=str(match["kind"]),
            workspace_id=workspace_id,
            story_id=str(match.get("story_id", "")),
            session_id=str(match.get("session_id", "")),
        )

    root = _workspace_root(workspace_roots, workspace_id)
    removed = _remove_unindexed_status_file(
        path,
        root,
        kind=str(match["kind"]),
        workspace_id=workspace_id,
        story_id=str(match.get("story_id", "")),
        session_id=str(match.get("session_id", "")),
    )
    if removed:
        stop = root / _TEMPLATE_STATUS_DIR
        if match["kind"] == "session":
            stop = root / _STORIES_DIR / str(match.get("story_id", "")) / str(match.get("session_id", "")) / "status"
        _remove_empty_parents(path.parent, stop)
    return removed


def _dedupe_unindexed_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    locator_keys = ("category", "kind", "workspace_id", "story_id", "session_id", "relative_path", "path")
    for item in items:
        normalized = tuple(str(item.get(key, "")) for key in locator_keys)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
    return deduped


def _unindexed_item(category: str, item: dict[str, str]) -> dict[str, str]:
    return {
        "category": category,
        "kind": str(item.get("kind", "")),
        "workspace_id": str(item.get("workspace_id", "")),
        "story_id": str(item.get("story_id", "")),
        "session_id": str(item.get("session_id", "")),
        "relative_path": str(item.get("relative_path", "")),
        "path": str(item.get("path", "")),
    }


def _find_unindexed_item(items: list[dict[str, str]], target: dict[str, str]) -> dict[str, str] | None:
    locator_keys = ("category", "kind", "workspace_id", "story_id", "session_id", "relative_path", "path")
    normalized = {key: str(target.get(key, "")) for key in locator_keys}
    for item in items:
        if all(str(item.get(key, "")) == normalized[key] for key in locator_keys):
            return item
    return None


def _workspace_roots_from_index() -> dict[str, Path]:
    return {
        str(workspace.id): resolve_workspace_root(str(workspace.root_path))
        for workspace in WorkspaceRecord.select()
    }


def _scan_orphan_runtime_dirs(workspace_roots: dict[str, Path]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    workspace_root_set = {root.resolve() for root in workspace_roots.values()}
    candidate_parents = {root.parent for root in workspace_root_set}
    for parent in sorted(candidate_parents):
        if not parent.is_dir():
            continue
        for child in sorted(parent.iterdir()):
            if not child.is_dir():
                continue
            child_root = child.resolve()
            if child_root not in workspace_root_set and _looks_like_workspace_root(child_root):
                results.append({
                    "kind": "workspace",
                    "workspace_id": "",
                    "story_id": "",
                    "session_id": "",
                    "path": str(child_root),
                    "relative_path": "",
                })

    indexed_story_ids: dict[str, set[str]] = {}
    for story in StoryRecord.select(StoryRecord.id, StoryRecord.workspace):
        indexed_story_ids.setdefault(str(story.workspace_id), set()).add(str(story.id))
    for workspace_id, root in sorted(workspace_roots.items()):
        stories_dir = root / _STORIES_DIR
        if not stories_dir.is_dir():
            continue
        allowed = indexed_story_ids.get(workspace_id, set())
        for child in sorted(stories_dir.iterdir()):
            if child.is_dir() and child.name not in allowed:
                results.append({
                    "kind": "story",
                    "workspace_id": workspace_id,
                    "story_id": child.name,
                    "session_id": "",
                    "path": str(child.resolve()),
                    "relative_path": _relative_to_root(child, root),
                })

    indexed_sessions: dict[tuple[str, str], set[str]] = {}
    for session in SessionRecord.select(SessionRecord.id, SessionRecord.workspace, SessionRecord.story):
        key = (str(session.workspace_id), str(session.story_id))
        indexed_sessions.setdefault(key, set()).add(str(session.id))
    for workspace_id, root in sorted(workspace_roots.items()):
        stories_dir = root / _STORIES_DIR
        if not stories_dir.is_dir():
            continue
        for story_dir in sorted(stories_dir.iterdir()):
            if not story_dir.is_dir():
                continue
            allowed = indexed_sessions.get((workspace_id, story_dir.name), set())
            for session_dir in sorted(story_dir.iterdir()):
                if session_dir.is_dir() and session_dir.name not in allowed:
                    results.append({
                        "kind": "session",
                        "workspace_id": workspace_id,
                        "story_id": story_dir.name,
                        "session_id": session_dir.name,
                        "path": str(session_dir.resolve()),
                        "relative_path": _relative_to_root(session_dir, root),
                    })
    return results


def _scan_unindexed_status_files(workspace_roots: dict[str, Path]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    indexed_template_paths: dict[str, set[Path]] = {}
    for table in StatusTableTemplateRecord.select(StatusTableTemplateRecord.workspace, StatusTableTemplateRecord.relative_path):
        workspace_id = str(table.workspace_id)
        workspace_root = _workspace_root(workspace_roots, workspace_id)
        indexed_template_paths.setdefault(workspace_id, set()).add(
            resolve_workspace_relative_path(workspace_root, str(table.relative_path)).resolve()
        )
    for workspace_id, root in sorted(workspace_roots.items()):
        template_root = root / _TEMPLATE_STATUS_DIR
        if not template_root.is_dir():
            continue
        allowed = indexed_template_paths.get(workspace_id, set())
        for path in sorted(template_root.rglob(_STATUS_FILE_PATTERN)):
            if path.resolve() not in allowed:
                results.append({
                    "kind": "template",
                    "workspace_id": workspace_id,
                    "story_id": "",
                    "session_id": "",
                    "path": str(path.resolve()),
                    "relative_path": _relative_to_root(path, root),
                })

    indexed_session_paths: dict[str, set[Path]] = {}
    for table in SessionStatusTableRecord.select(SessionStatusTableRecord.session, SessionStatusTableRecord.relative_path):
        session_id = str(table.session_id)
        workspace_root = _workspace_root(workspace_roots, str(table.session.workspace_id))
        indexed_session_paths.setdefault(session_id, set()).add(
            resolve_workspace_relative_path(workspace_root, str(table.relative_path)).resolve()
        )
    for session in SessionRecord.select(SessionRecord.id, SessionRecord.workspace, SessionRecord.story):
        workspace_id = str(session.workspace_id)
        story_id = str(session.story_id)
        session_id = str(session.id)
        root = _workspace_root(workspace_roots, workspace_id)
        status_root = root / _STORIES_DIR / story_id / session_id / "status"
        if not status_root.is_dir():
            continue
        allowed = indexed_session_paths.get(session_id, set())
        for path in sorted(status_root.rglob(_STATUS_FILE_PATTERN)):
            if path.resolve() not in allowed:
                results.append({
                    "kind": "session",
                    "workspace_id": workspace_id,
                    "story_id": story_id,
                    "session_id": session_id,
                    "path": str(path.resolve()),
                    "relative_path": _relative_to_root(path, root),
                })
    return results


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def _ensure_workspace_roots() -> tuple[dict[str, Path], int]:
    roots: dict[str, Path] = {}
    for workspace in WorkspaceRecord.select():
        workspace_id = str(workspace.id)
        root = resolve_workspace_root(str(workspace.root_path))
        root.mkdir(parents=True, exist_ok=True)
        (root / _TEMPLATE_STATUS_DIR).mkdir(parents=True, exist_ok=True)
        (root / _STORIES_DIR).mkdir(parents=True, exist_ok=True)
        roots[workspace_id] = root
        logger.debug("workspace root materialized workspace_id=%s root=%s", workspace_id, root)
    return roots, len(roots)


def _cleanup_orphan_runtime_dirs(workspace_roots: dict[str, Path]) -> int:
    if not get_bootstrap_delete_orphan_dirs():
        logger.info("runtime bootstrap orphan directory cleanup disabled")
        return 0

    workspace_root_set = {root.resolve() for root in workspace_roots.values()}
    removed_count = 0
    removed_count += _cleanup_orphan_workspace_dirs(workspace_root_set)
    removed_count += _cleanup_orphan_story_dirs(workspace_roots)
    removed_count += _cleanup_orphan_session_dirs(workspace_roots)
    logger.info("runtime bootstrap orphan directory cleanup finished removed_count=%s", removed_count)
    return removed_count


def _cleanup_orphan_workspace_dirs(workspace_root_set: set[Path]) -> int:
    removed_count = 0
    candidate_parents = {root.parent for root in workspace_root_set}
    for parent in sorted(candidate_parents):
        if not parent.is_dir():
            continue
        for child in sorted(parent.iterdir()):
            if not child.is_dir():
                continue
            child_root = child.resolve()
            if child_root in workspace_root_set:
                continue
            if not _looks_like_workspace_root(child_root):
                logger.debug("workspace orphan scan skipped non-workspace dir path=%s", child_root)
                continue
            if _remove_orphan_dir(child_root, kind="workspace"):
                removed_count += 1
    return removed_count


def _cleanup_orphan_story_dirs(workspace_roots: dict[str, Path]) -> int:
    indexed_story_ids: dict[str, set[str]] = {}
    for story in StoryRecord.select(StoryRecord.id, StoryRecord.workspace):
        indexed_story_ids.setdefault(str(story.workspace_id), set()).add(str(story.id))

    removed_count = 0
    for workspace_id, root in sorted(workspace_roots.items()):
        stories_dir = root / _STORIES_DIR
        if not stories_dir.is_dir():
            continue
        allowed = indexed_story_ids.get(workspace_id, set())
        for child in sorted(stories_dir.iterdir()):
            if not child.is_dir():
                continue
            if child.name in allowed:
                continue
            if _remove_orphan_dir(child, kind="story", workspace_id=workspace_id, story_id=child.name):
                removed_count += 1
    return removed_count


def _cleanup_orphan_session_dirs(workspace_roots: dict[str, Path]) -> int:
    indexed_sessions: dict[tuple[str, str], set[str]] = {}
    for session in SessionRecord.select(SessionRecord.id, SessionRecord.workspace, SessionRecord.story):
        key = (str(session.workspace_id), str(session.story_id))
        indexed_sessions.setdefault(key, set()).add(str(session.id))

    removed_count = 0
    for workspace_id, root in sorted(workspace_roots.items()):
        stories_dir = root / _STORIES_DIR
        if not stories_dir.is_dir():
            continue
        for story_dir in sorted(stories_dir.iterdir()):
            if not story_dir.is_dir():
                continue
            allowed = indexed_sessions.get((workspace_id, story_dir.name), set())
            for session_dir in sorted(story_dir.iterdir()):
                if not session_dir.is_dir():
                    continue
                if session_dir.name in allowed:
                    continue
                if _remove_orphan_dir(
                    session_dir,
                    kind="session",
                    workspace_id=workspace_id,
                    story_id=story_dir.name,
                    session_id=session_dir.name,
                ):
                    removed_count += 1
    return removed_count


def _looks_like_workspace_root(path: Path) -> bool:
    return (path / _STORIES_DIR).is_dir() or (path / _TEMPLATE_STATUS_DIR).is_dir()


def _remove_orphan_dir(
    path: Path,
    *,
    kind: str,
    workspace_id: str = "",
    story_id: str = "",
    session_id: str = "",
) -> bool:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception(
            "failed to remove orphan runtime directory kind=%s workspace_id=%s "
            "story_id=%s session_id=%s path=%s",
            kind,
            workspace_id or "<unknown>",
            story_id or "<unknown>",
            session_id or "<unknown>",
            path,
        )
        return False
    logger.warning(
        "removed orphan runtime directory kind=%s workspace_id=%s story_id=%s "
        "session_id=%s path=%s",
        kind,
        workspace_id or "<unknown>",
        story_id or "<unknown>",
        session_id or "<unknown>",
        path,
    )
    return True


def _cleanup_unindexed_status_files(workspace_roots: dict[str, Path]) -> int:
    if not get_bootstrap_delete_orphan_dirs():
        logger.info("runtime bootstrap unindexed status file cleanup disabled")
        return 0

    removed_count = 0
    removed_count += _cleanup_unindexed_template_status_files(workspace_roots)
    removed_count += _cleanup_unindexed_session_status_files(workspace_roots)
    logger.info("runtime bootstrap unindexed status file cleanup finished removed_count=%s", removed_count)
    return removed_count


def _cleanup_unindexed_template_status_files(workspace_roots: dict[str, Path]) -> int:
    indexed_paths: dict[str, set[Path]] = {}
    for table in StatusTableTemplateRecord.select(
        StatusTableTemplateRecord.workspace,
        StatusTableTemplateRecord.relative_path,
    ):
        workspace_id = str(table.workspace_id)
        workspace_root = _workspace_root(workspace_roots, workspace_id)
        indexed_paths.setdefault(workspace_id, set()).add(
            resolve_workspace_relative_path(workspace_root, str(table.relative_path)).resolve()
        )

    removed_count = 0
    for workspace_id, root in sorted(workspace_roots.items()):
        template_root = root / _TEMPLATE_STATUS_DIR
        if not template_root.is_dir():
            continue
        allowed = indexed_paths.get(workspace_id, set())
        for path in sorted(template_root.rglob(_STATUS_FILE_PATTERN)):
            if path.resolve() in allowed:
                continue
            if _remove_unindexed_status_file(path, root, kind="template", workspace_id=workspace_id):
                removed_count += 1
                _remove_empty_parents(path.parent, template_root)
    return removed_count


def _cleanup_unindexed_session_status_files(workspace_roots: dict[str, Path]) -> int:
    indexed_paths: dict[str, set[Path]] = {}
    for table in SessionStatusTableRecord.select(
        SessionStatusTableRecord.session,
        SessionStatusTableRecord.relative_path,
    ):
        session_id = str(table.session_id)
        session = table.session
        workspace_root = _workspace_root(workspace_roots, str(session.workspace_id))
        indexed_paths.setdefault(session_id, set()).add(
            resolve_workspace_relative_path(workspace_root, str(table.relative_path)).resolve()
        )

    removed_count = 0
    for session in SessionRecord.select(SessionRecord.id, SessionRecord.workspace, SessionRecord.story):
        workspace_id = str(session.workspace_id)
        story_id = str(session.story_id)
        session_id = str(session.id)
        root = _workspace_root(workspace_roots, workspace_id)
        status_root = root / _STORIES_DIR / story_id / session_id / "status"
        if not status_root.is_dir():
            continue
        allowed = indexed_paths.get(session_id, set())
        for path in sorted(status_root.rglob(_STATUS_FILE_PATTERN)):
            if path.resolve() in allowed:
                continue
            if _remove_unindexed_status_file(
                path,
                root,
                kind="session",
                workspace_id=workspace_id,
                story_id=story_id,
                session_id=session_id,
            ):
                removed_count += 1
                _remove_empty_parents(path.parent, status_root)
    return removed_count


def _remove_unindexed_status_file(
    path: Path,
    workspace_root: Path,
    *,
    kind: str,
    workspace_id: str,
    story_id: str = "",
    session_id: str = "",
) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception(
            "failed to remove unindexed status json kind=%s workspace_id=%s "
            "story_id=%s session_id=%s path=%s",
            kind,
            workspace_id,
            story_id or "<unknown>",
            session_id or "<unknown>",
            path,
        )
        return False
    relative_path = path.resolve().relative_to(workspace_root.resolve()).as_posix()
    logger.warning(
        "removed unindexed status json kind=%s workspace_id=%s story_id=%s "
        "session_id=%s relative_path=%s path=%s",
        kind,
        workspace_id,
        story_id or "<unknown>",
        session_id or "<unknown>",
        relative_path,
        path,
    )
    return True


def _remove_empty_parents(start: Path, stop: Path) -> None:
    stop_resolved = stop.resolve()
    current = start.resolve()
    while current != stop_resolved:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _check_template_files(workspace_roots: dict[str, Path]) -> int:
    missing_count = 0
    for template in StatusTableTemplateRecord.select():
        workspace_root = _workspace_root(workspace_roots, str(template.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, str(template.relative_path))
        if path.is_file():
            continue
        missing_count += 1
        logger.warning(
            "template status json missing template_id=%s workspace_id=%s "
            "relative_path=%s",
            template.id,
            template.workspace_id,
            template.relative_path,
        )
    return missing_count


def _ensure_session_copies(database: Database) -> int:
    from rpg_data.services.status import StatusTableService

    status_service = StatusTableService(database)
    initialized_count = 0
    for session in SessionRecord.select():
        session_id = str(session.id)
        if SessionStatusTableRecord.select().where(
            SessionStatusTableRecord.session == session_id
        ).exists():
            continue
        try:
            tables = status_service.initialize_session_tables(session_id)
            initialized_count += 1
            logger.info(
                "session status tables materialized session_id=%s table_count=%s",
                session_id,
                len(tables),
            )
        except Exception:
            logger.exception("failed to initialize status tables for session %s", session_id)
    return initialized_count


def _check_session_files(workspace_roots: dict[str, Path]) -> int:
    missing_count = 0
    for table in SessionStatusTableRecord.select():
        workspace_root = _workspace_root(workspace_roots, str(table.session.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, str(table.relative_path))
        if path.is_file():
            continue
        missing_count += 1
        logger.warning(
            "session status json missing table_id=%s session_id=%s relative_path=%s",
            table.id,
            table.session_id,
            table.relative_path,
        )
    return missing_count


def _workspace_root(workspace_roots: dict[str, Path], workspace_id: str) -> Path:
    root = workspace_roots.get(workspace_id)
    if root is None:
        workspace = WorkspaceRecord.get_by_id(workspace_id)
        root = resolve_workspace_root(str(workspace.root_path))
        root.mkdir(parents=True, exist_ok=True)
        workspace_roots[workspace_id] = root
    return root
