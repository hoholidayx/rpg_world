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
    StatusTableTemplateRecord,
    WorkspaceRecord,
    bind_database,
)
from rpg_data.services.status import StatusTableService
from rpg_data.settings import resolve_workspace_relative_path, resolve_workspace_root

__all__ = ["bootstrap_runtime_data"]

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
    template_file_count = _ensure_template_files(workspace_roots)
    session_copy_count = _ensure_session_copies(database)
    session_file_count = _ensure_session_files(workspace_roots)
    logger.info(
        "runtime bootstrap finished workspace_count=%s template_files_created=%s "
        "sessions_initialized=%s session_files_restored=%s",
        workspace_count,
        template_file_count,
        session_copy_count,
        session_file_count,
    )


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
