"""Data manager backend provider for Play API."""

from __future__ import annotations

import sqlite3

from rpg_data import db
from rpg_data.migrations.runner import run_migrations


class DataManagerBackend:
    """Read Play-facing metadata from the rpg_data database."""

    async def list_workspaces(self) -> list[dict[str, object]]:
        conn = db.connect()
        try:
            run_migrations(conn)
            rows = conn.execute(
                """
                SELECT id, name, description
                FROM workspaces
                WHERE enabled = 1
                ORDER BY
                    name,
                    id
                """
            ).fetchall()
            return [_workspace_summary(row) for row in rows]
        finally:
            conn.close()


def _workspace_summary(row: sqlite3.Row) -> dict[str, object]:
    description = str(row["description"] or "")
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "description": description or None,
    }
