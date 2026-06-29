"""Runtime bootstrap helpers for catalog-backed workspace files."""

from __future__ import annotations

import csv
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from peewee import Database

from rpg_data.repositories.records import (
    SessionRecord,
    SessionStatusTableRecord,
    StoryRecord,
    StatusTableTemplateRecord,
    WorkspaceRecord,
    bind_database,
)
from rpg_data.services.status import StatusTableService
from rpg_data.settings import (
    get_bootstrap_delete_orphan_dirs,
    resolve_workspace_relative_path,
    resolve_workspace_root,
)

__all__ = ["bootstrap_runtime_data", "scan_orphan_runtime_data"]

logger = logging.getLogger("rpg_data.bootstrap")

_BOOTSTRAP_CSV_KEY = "_bootstrap_csv"
_TEMPLATE_STATUS_DIR = "template_status"
_STORIES_DIR = "stories"


def bootstrap_runtime_data(database: Database) -> None:
    """Align SQL file indexes with workspace directories and CSV files.

    SQL remains the complete index. Bootstrap does not discover status tables
    from directories and does not create business records; it only materializes
    files referenced by indexed rows. Missing CSV content is restored from the
    row's ``metadata_json._bootstrap_csv`` seed when present, otherwise an empty
    CSV shell is created.
    """

    bind_database(database)
    logger.info("runtime bootstrap started")
    workspace_roots, workspace_count = _ensure_workspace_roots()
    orphan_dirs_removed = _cleanup_orphan_runtime_dirs(workspace_roots)
    orphan_status_files_removed = _cleanup_unindexed_status_files(workspace_roots)
    template_file_count = _ensure_template_files(workspace_roots)
    session_copy_count = _ensure_session_copies(database)
    session_file_count = _ensure_session_files(workspace_roots)
    logger.info(
        "runtime bootstrap finished workspace_count=%s template_files_created=%s "
        "sessions_initialized=%s session_files_restored=%s orphan_dirs_removed=%s "
        "orphan_status_files_removed=%s",
        workspace_count,
        template_file_count,
        session_copy_count,
        session_file_count,
        orphan_dirs_removed,
        orphan_status_files_removed,
    )


def scan_orphan_runtime_data(database: Database) -> dict[str, list[dict[str, str]]]:
    """Return runtime directories/status CSV files not indexed by SQL.

    This is a read-only companion for operational tooling. It intentionally
    reuses the same index rules as bootstrap cleanup, but never deletes files.
    """

    bind_database(database)
    workspace_roots = _workspace_roots_from_index()
    return {
        "orphan_directories": _scan_orphan_runtime_dirs(workspace_roots),
        "unindexed_status_files": _scan_unindexed_status_files(workspace_roots),
    }


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
        for path in sorted(template_root.rglob("*.csv")):
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
        for path in sorted(status_root.rglob("*.csv")):
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
        for path in sorted(template_root.rglob("*.csv")):
            if path.resolve() in allowed:
                continue
            if _remove_orphan_status_file(path, root, kind="template", workspace_id=workspace_id):
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
        for path in sorted(status_root.rglob("*.csv")):
            if path.resolve() in allowed:
                continue
            if _remove_orphan_status_file(
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


def _remove_orphan_status_file(
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
            "failed to remove unindexed status csv kind=%s workspace_id=%s "
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
        "removed unindexed status csv kind=%s workspace_id=%s story_id=%s "
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


def _ensure_template_files(workspace_roots: dict[str, Path]) -> int:
    created_count = 0
    for template in StatusTableTemplateRecord.select():
        workspace_root = _workspace_root(workspace_roots, str(template.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, str(template.relative_path))
        if path.is_file():
            continue
        headers, rows = _csv_seed_from_metadata(str(template.metadata_json or "{}"))
        _write_csv(path, headers, rows)
        created_count += 1
        logger.info(
            "template status csv materialized template_id=%s workspace_id=%s "
            "relative_path=%s headers=%s rows=%s",
            template.id,
            template.workspace_id,
            template.relative_path,
            headers,
            rows,
        )
    return created_count


def _ensure_session_copies(database: Database) -> int:
    status_service = StatusTableService(database)
    initialized_count = 0
    for session in SessionRecord.select():
        session_id = str(session.id)
        if SessionStatusTableRecord.select().where(
            SessionStatusTableRecord.session == session_id
        ).exists():
            continue
        try:
            status_service.clear_unindexed_session_files(session_id)
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


def _ensure_session_files(workspace_roots: dict[str, Path]) -> int:
    restored_count = 0
    for table in SessionStatusTableRecord.select():
        workspace_root = _workspace_root(workspace_roots, str(table.session.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, str(table.relative_path))
        if path.is_file():
            continue

        source_path: Path | None = None
        if table.source_table_id is not None:
            source = StatusTableTemplateRecord.get_or_none(
                StatusTableTemplateRecord.id == int(table.source_table_id)
            )
            if source is not None:
                source_path = resolve_workspace_relative_path(
                    workspace_root,
                    str(source.relative_path),
                )
        if source_path is not None and source_path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, path)
            headers, rows = _read_csv(source_path)
            restored_count += 1
            logger.info(
                "session status csv restored from template table_id=%s session_id=%s "
                "relative_path=%s headers=%s rows=%s",
                table.id,
                table.session_id,
                table.relative_path,
                headers,
                rows,
            )
            continue

        headers, rows = _csv_seed_from_metadata(str(table.metadata_json or "{}"))
        _write_csv(path, headers, rows)
        restored_count += 1
        logger.info(
            "session status csv restored from metadata table_id=%s session_id=%s "
            "relative_path=%s headers=%s rows=%s",
            table.id,
            table.session_id,
            table.relative_path,
            headers,
            rows,
        )
    return restored_count


def _workspace_root(workspace_roots: dict[str, Path], workspace_id: str) -> Path:
    root = workspace_roots.get(workspace_id)
    if root is None:
        workspace = WorkspaceRecord.get_by_id(workspace_id)
        root = resolve_workspace_root(str(workspace.root_path))
        root.mkdir(parents=True, exist_ok=True)
        workspace_roots[workspace_id] = root
    return root


def _csv_seed_from_metadata(metadata_json: str) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    try:
        metadata = json.loads(metadata_json)
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    raw_seed = metadata.get(_BOOTSTRAP_CSV_KEY, {})
    if not isinstance(raw_seed, dict):
        raw_seed = {}

    headers = _string_tuple(raw_seed.get("headers", ()))
    rows = tuple(_string_tuple(row) for row in _iter_rows(raw_seed.get("rows", ())))
    return headers, rows


def _iter_rows(value: Any) -> tuple[Any, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value)


def _write_csv(path: Path, headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(rows)


def _read_csv(path: Path) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        raw_rows = list(csv.reader(fh))
    if not raw_rows:
        return (), ()
    headers = tuple(str(cell) for cell in raw_rows[0])
    rows = tuple(tuple(str(cell) for cell in row) for row in raw_rows[1:])
    return headers, rows
