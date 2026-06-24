"""SQLite repository for canonical memory chunks."""

from __future__ import annotations

import json as _json
import sqlite3
import time
from pathlib import Path

from rp_memory.storage.types import ChunkRecord, IndexedFileState


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

    def list_indexed_files(self, source_id: str) -> dict[str, IndexedFileState]:
        rows = self._conn.execute(
            """
            SELECT file, source_id, mtime_ns, size, content_hash, chunk_count,
                   indexed_at, status, last_error
            FROM indexed_files
            WHERE source_id = ?
            """,
            (source_id,),
        ).fetchall()
        result: dict[str, IndexedFileState] = {}
        for row in rows:
            state = IndexedFileState(
                file=str(row[0]),
                source_id=str(row[1]),
                mtime_ns=int(row[2]),
                size=int(row[3]),
                content_hash=str(row[4]),
                chunk_count=int(row[5]),
                indexed_at=float(row[6]),
                status=str(row[7]),
                last_error=str(row[8] or ""),
            )
            result[state.file] = state
        if not result:
            rows = self._conn.execute(
                """
                SELECT file, source, COUNT(*)
                FROM chunks
                WHERE source = ?
                GROUP BY file, source
                """,
                (source_id,),
            ).fetchall()
            for row in rows:
                file_path = str(row[0])
                result[file_path] = IndexedFileState(
                    file=file_path,
                    source_id=str(row[1]),
                    mtime_ns=0,
                    size=0,
                    content_hash="",
                    chunk_count=int(row[2]),
                    indexed_at=0.0,
                    status="unknown",
                )
        return result

    def upsert_indexed_file(self, state: IndexedFileState) -> None:
        indexed_at = time.time() if state.indexed_at is None else state.indexed_at
        self._conn.execute(
            """
            INSERT INTO indexed_files (
                file, source_id, mtime_ns, size, content_hash, chunk_count,
                indexed_at, status, last_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file) DO UPDATE SET
                source_id = excluded.source_id,
                mtime_ns = excluded.mtime_ns,
                size = excluded.size,
                content_hash = excluded.content_hash,
                chunk_count = excluded.chunk_count,
                indexed_at = excluded.indexed_at,
                status = excluded.status,
                last_error = excluded.last_error
            """,
            (
                state.file,
                state.source_id,
                state.mtime_ns,
                state.size,
                state.content_hash,
                state.chunk_count,
                indexed_at,
                state.status,
                state.last_error,
            ),
        )

    def delete_indexed_file(self, file_path: str) -> None:
        self._conn.execute("DELETE FROM indexed_files WHERE file = ?", (file_path,))

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
            CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file);
            CREATE TABLE IF NOT EXISTS indexed_files (
                file TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL DEFAULT 0,
                size INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT NOT NULL DEFAULT '',
                chunk_count INTEGER NOT NULL DEFAULT 0,
                indexed_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'indexed',
                last_error TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_indexed_files_source
                ON indexed_files(source_id);
            """
        )
        col_info = conn.execute("PRAGMA table_info(chunks)").fetchall()
        existing_cols = {r[1] for r in col_info}
        if "metadata" not in existing_cols:
            conn.execute("ALTER TABLE chunks ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        return conn
