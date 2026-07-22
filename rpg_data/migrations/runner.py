"""Migration runner for the RPG World SQLite database."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from rpg_data.db import transaction

_MIGRATIONS_DIR = Path(__file__).resolve().parent
logger = logging.getLogger("rpg_data.migrations")


class MigrationHistoryError(RuntimeError):
    """The database migration ledger does not match this hard-cut schema."""


@dataclass(frozen=True)
class MigrationSpec:
    version: str
    name: str
    path: Path
    sql: str
    checksum: str


@dataclass(frozen=True)
class AppliedMigration:
    version: str
    name: str
    checksum: str


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply pending SQLite migrations to ``conn``."""

    logger.info("migration check started")
    _ensure_schema_migrations(conn)
    migrations = _load_migrations()
    applied_migrations = _get_applied_migrations(conn)
    _validate_migration_history(migrations, applied_migrations)
    applied_count = 0

    for migration in migrations:
        if migration.version in applied_migrations:
            logger.debug(
                "migration already applied version=%s name=%s",
                migration.version,
                migration.name,
            )
            continue

        logger.info(
            "applying migration version=%s name=%s checksum=%s",
            migration.version,
            migration.name,
            migration.checksum,
        )
        with transaction(conn):
            _execute_sql_script(conn, migration.sql)
            conn.execute(
                """
                INSERT INTO rpg_schema_migrations (version, name, checksum)
                VALUES (?, ?, ?)
                """,
                (migration.version, migration.name, migration.checksum),
            )
        applied_migrations[migration.version] = AppliedMigration(
            migration.version,
            migration.name,
            migration.checksum,
        )
        applied_count += 1
        logger.info(
            "migration applied version=%s name=%s",
            migration.version,
            migration.name,
        )

    logger.info(
        "migration check finished applied_count=%s total_versions=%s",
        applied_count,
        len(applied_migrations),
    )


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


def _get_applied_migrations(
    conn: sqlite3.Connection,
) -> dict[str, AppliedMigration]:
    rows = conn.execute(
        "SELECT version, name, checksum FROM rpg_schema_migrations"
    ).fetchall()
    return {
        str(row["version"]): AppliedMigration(
            version=str(row["version"]),
            name=str(row["name"]),
            checksum=str(row["checksum"]),
        )
        for row in rows
    }


def _load_migrations() -> tuple[MigrationSpec, ...]:
    migrations: list[MigrationSpec] = []
    versions: set[str] = set()
    for path in _iter_migration_files():
        version = _migration_version(path)
        if version in versions:
            raise MigrationHistoryError(
                f"duplicate migration version in package: {version}"
            )
        versions.add(version)
        sql = path.read_text(encoding="utf-8")
        migrations.append(MigrationSpec(
            version=version,
            name=path.name,
            path=path,
            sql=sql,
            checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        ))
    return tuple(migrations)


def _validate_migration_history(
    migrations: tuple[MigrationSpec, ...],
    applied: dict[str, AppliedMigration],
) -> None:
    expected = {migration.version: migration for migration in migrations}
    unsupported = sorted(set(applied).difference(expected))
    if unsupported:
        raise MigrationHistoryError(
            "database uses unsupported pre-hard-cut migration versions: "
            + ", ".join(unsupported)
        )

    for version, ledger in applied.items():
        migration = expected[version]
        if ledger.name != migration.name:
            raise MigrationHistoryError(
                "migration name mismatch "
                f"version={version} database={ledger.name!r} package={migration.name!r}"
            )
        if ledger.checksum != migration.checksum:
            raise MigrationHistoryError(
                "migration checksum mismatch "
                f"version={version} name={migration.name}"
            )


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
