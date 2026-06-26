"""Migration runner for the RPG World SQLite database."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from rpg_data.db import transaction

_MIGRATIONS_DIR = Path(__file__).resolve().parent


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply pending SQLite migrations to ``conn``."""

    _ensure_schema_migrations(conn)
    applied_versions = _get_applied_versions(conn)

    for migration_path in _iter_migration_files():
        version = _migration_version(migration_path)
        if version in applied_versions:
            continue

        sql = migration_path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        with transaction(conn):
            _execute_sql_script(conn, sql)
            conn.execute(
                """
                INSERT INTO rpg_schema_migrations (version, name, checksum)
                VALUES (?, ?, ?)
                """,
                (version, migration_path.name, checksum),
            )
        applied_versions.add(version)


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rpg_schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _get_applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM rpg_schema_migrations").fetchall()
    return {row["version"] for row in rows}


def _iter_migration_files() -> list[Path]:
    return sorted(_MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def _migration_version(path: Path) -> str:
    return path.stem.split("_", 1)[0]


def _execute_sql_script(conn: sqlite3.Connection, sql: str) -> None:
    statement_lines: list[str] = []

    for line in sql.splitlines():
        statement_lines.append(line)
        statement = "\n".join(statement_lines).strip()
        if not statement or not sqlite3.complete_statement(statement):
            continue
        conn.execute(statement)
        statement_lines.clear()

    trailing_statement = "\n".join(statement_lines).strip()
    if trailing_statement:
        raise sqlite3.OperationalError("incomplete SQL migration statement")
