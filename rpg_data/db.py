"""SQLite connection helpers for the RPG World data module."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from rpg_data.settings import get_database_path

if TYPE_CHECKING:
    from peewee import Database, SqliteDatabase

_BUSY_TIMEOUT_MS = 5000

__all__ = [
    "bind_peewee_database",
    "connect",
    "make_peewee_database",
    "transaction",
]


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a configured SQLite connection and apply runtime pragmas."""

    path = Path(db_path).expanduser() if db_path is not None else get_database_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    return conn


def make_peewee_database(db_path: str | Path | None = None) -> "SqliteDatabase":
    """Create a Peewee SQLite database for repository-backed access."""

    from rpg_data.repositories.records import make_database

    return make_database(db_path)


def bind_peewee_database(database: "Database") -> "Database":
    """Bind all repository record models to ``database``."""

    from rpg_data.repositories.records import bind_database

    return bind_database(database)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a SQLite transaction, committing on success and rolling back on error."""

    try:
        conn.execute("BEGIN")
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
