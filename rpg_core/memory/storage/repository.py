"""SQLite repository for canonical memory chunks."""

from __future__ import annotations

import json as _json
import sqlite3
import time
from pathlib import Path

from rpg_world.rpg_core.memory.storage.types import ChunkRecord


class MemoryRepository:
    """Owns the SQLite connection and the canonical `chunks` table."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        self._conn = self._open()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    @property
    def path(self) -> str:
        return self._path

    def upsert_chunk(self, record: ChunkRecord, created_at: float | None = None) -> int:
        created_at = time.time() if created_at is None else created_at
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO chunks (id, text, source, file, chunk_idx, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.text,
                str(record.metadata.get("source", "")),
                str(record.metadata.get("file", "")),
                int(record.metadata.get("chunk_idx", 0)),
                created_at,
                _json.dumps(record.metadata, ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid)

    def delete_chunk_by_source(self, source: str) -> list[int]:
        rows = self._conn.execute(
            "SELECT id FROM chunks WHERE source = ?",
            (source,),
        ).fetchall()
        self._conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
        return [int(row[0]) for row in rows]

    def delete_chunk_by_file(self, file_path: str) -> list[int]:
        rows = self._conn.execute(
            "SELECT id FROM chunks WHERE file = ?",
            (file_path,),
        ).fetchall()
        self._conn.execute("DELETE FROM chunks WHERE file = ?", (file_path,))
        return [int(row[0]) for row in rows]

    def delete_chunk_by_file_and_idx(self, file_path: str, chunk_idx: int) -> list[int]:
        rows = self._conn.execute(
            "SELECT id FROM chunks WHERE file = ? AND chunk_idx = ?",
            (file_path, chunk_idx),
        ).fetchall()
        self._conn.execute(
            "DELETE FROM chunks WHERE file = ? AND chunk_idx = ?",
            (file_path, chunk_idx),
        )
        return [int(row[0]) for row in rows]

    def iter_chunks(self) -> list[tuple[int, str]]:
        return [
            (int(memory_id), str(text))
            for memory_id, text in self._conn.execute("SELECT id, text FROM chunks").fetchall()
        ]

    def clear_chunks(self) -> None:
        self._conn.execute("DELETE FROM chunks")

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def _open(self) -> sqlite3.Connection:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                source TEXT NOT NULL,
                file TEXT NOT NULL,
                chunk_idx INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source);
            """
        )
        col_info = conn.execute("PRAGMA table_info(chunks)").fetchall()
        existing_cols = {r[1] for r in col_info}
        if "metadata" not in existing_cols:
            conn.execute("ALTER TABLE chunks ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        return conn
