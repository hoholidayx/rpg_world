"""Settings helpers for the RPG World data module."""

from __future__ import annotations

import os
from pathlib import Path

DATABASE_PATH_ENV = "RPG_WORLD_DB_PATH"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATABASE_PATH = _PROJECT_ROOT / "data" / "rpg_world.sqlite3"


def get_database_path() -> Path:
    """Return the configured SQLite database path."""

    configured = os.getenv(DATABASE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    return _DEFAULT_DATABASE_PATH
