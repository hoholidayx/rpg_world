"""Settings helpers for the RPG World data module."""

from __future__ import annotations

import os
from pathlib import Path

DATABASE_PATH_ENV = "RPG_WORLD_DB_PATH"
WORKSPACE_ROOT_BASE_ENV = "RPG_WORLD_WORKSPACE_ROOT_BASE"
BOOTSTRAP_DELETE_ORPHAN_DIRS_ENV = "RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATABASE_PATH = _PROJECT_ROOT / "data" / "rpg_world.sqlite3"

__all__ = [
    "DATABASE_PATH_ENV",
    "BOOTSTRAP_DELETE_ORPHAN_DIRS_ENV",
    "WORKSPACE_ROOT_BASE_ENV",
    "get_bootstrap_delete_orphan_dirs",
    "get_database_path",
    "get_workspace_root_base",
    "resolve_database_path",
    "resolve_workspace_relative_path",
    "resolve_workspace_root",
]


def get_bootstrap_delete_orphan_dirs() -> bool:
    """Return whether bootstrap should remove catalog-orphan runtime dirs."""

    value = os.getenv(BOOTSTRAP_DELETE_ORPHAN_DIRS_ENV)
    if value is None or str(value).strip() == "":
        return False
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return False


def get_database_path() -> Path:
    """Return the configured SQLite database path."""

    return resolve_database_path()


def resolve_database_path(db_path: str | Path | None = None) -> Path:
    """Resolve a configured database path without touching callers' cwd.

    The special SQLite path ``":memory:"`` is preserved. Relative filesystem
    paths stay relative, matching the previous database behavior; only ``~`` is
    expanded here.
    """

    configured = db_path if db_path is not None else os.getenv(DATABASE_PATH_ENV)
    if configured is None or str(configured) == "":
        return _DEFAULT_DATABASE_PATH
    if str(configured) == ":memory:":
        return Path(":memory:")
    return Path(configured).expanduser()


def get_workspace_root_base() -> Path:
    """Return the base directory for relative workspace ``root_path`` values."""

    configured = os.getenv(WORKSPACE_ROOT_BASE_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return _PROJECT_ROOT


def resolve_workspace_root(root_path: str | Path) -> Path:
    """Resolve a workspace root path from the catalog.

    Absolute ``root_path`` values are used directly. Relative values are
    resolved against ``RPG_WORLD_WORKSPACE_ROOT_BASE`` when set, otherwise
    against the repository root used by the default database layout.
    """

    path = Path(root_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (get_workspace_root_base() / path).resolve()


def resolve_workspace_relative_path(
    workspace_root: str | Path,
    relative_path: str | Path,
) -> Path:
    """Resolve a catalog relative path inside a workspace root.

    Catalog runtime directories are stored as workspace-relative paths. This
    helper is the single boundary that turns those locators into real paths and
    rejects traversal or absolute paths that escape the workspace.
    """

    relative = Path(relative_path)
    if relative.is_absolute():
        raise ValueError(f"Workspace relative path must not be absolute: {relative_path}")

    root = resolve_workspace_root(workspace_root)
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Workspace relative path escapes workspace root: {relative_path}") from exc
    return target
