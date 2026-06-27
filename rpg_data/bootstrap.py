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
    workspace_roots = _ensure_workspace_roots()
    _ensure_template_files(workspace_roots)
    _ensure_session_copies(database)
    _ensure_session_files(workspace_roots)


def _ensure_workspace_roots() -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for workspace in WorkspaceRecord.select():
        workspace_id = str(workspace.id)
        root = resolve_workspace_root(str(workspace.root_path))
        root.mkdir(parents=True, exist_ok=True)
        (root / _TEMPLATE_STATUS_DIR).mkdir(parents=True, exist_ok=True)
        (root / _STORIES_DIR).mkdir(parents=True, exist_ok=True)
        roots[workspace_id] = root
    return roots


def _ensure_template_files(workspace_roots: dict[str, Path]) -> None:
    for template in StatusTableTemplateRecord.select():
        workspace_root = _workspace_root(workspace_roots, str(template.workspace_id))
        path = resolve_workspace_relative_path(workspace_root, str(template.relative_path))
        if path.is_file():
            continue
        headers, rows = _csv_seed_from_metadata(str(template.metadata_json or "{}"))
        _write_csv(path, headers, rows)


def _ensure_session_copies(database: Database) -> None:
    status_service = StatusTableService(database)
    for session in SessionRecord.select():
        session_id = str(session.id)
        if SessionStatusTableRecord.select().where(
            SessionStatusTableRecord.session == session_id
        ).exists():
            continue
        try:
            status_service.clear_unindexed_session_files(session_id)
            status_service.initialize_session_tables(session_id)
        except Exception:
            logger.exception("failed to initialize status tables for session %s", session_id)


def _ensure_session_files(workspace_roots: dict[str, Path]) -> None:
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
            continue

        headers, rows = _csv_seed_from_metadata(str(table.metadata_json or "{}"))
        _write_csv(path, headers, rows)


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
