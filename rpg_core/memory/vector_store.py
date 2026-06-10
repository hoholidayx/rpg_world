"""SQLite + sqlite-vec vector store for memory chunks.

Provides upsert, delete-by-source, similarity search, and lifecycle
management.  The store owns a single SQLite connection in WAL mode and
commits in batches during bulk operations.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ChunkRecord:
    """A single chunk stored in the vector database."""

    id: int
    text: str
    metadata: dict[str, Any]


class VectorStoreError(Exception):
    """Unrecoverable vector store error."""


class VectorStore:
    """SQLite + sqlite-vec backed vector store.

    Schema::

        chunks(id PK, text, source, file, chunk_idx, created_at)
        vec_chunks(rowid → chunks.id, embedding FLOAT32[])
    """

    BATCH_SIZE = 100

    def __init__(self, db_path: str | Path, dimension: int) -> None:
        self._path = str(db_path)
        self._dim = dimension
        self._conn = self._open()

    # ── public API ────────────────────────────────────────────

    def upsert(
        self,
        records: list[ChunkRecord],
        embeddings: list[list[float]],
    ) -> None:
        """Insert or replace chunks.  Stale entries (same file+idx) are removed."""
        if not records:
            return
        cur = self._conn.cursor()
        try:
            for i, (rec, emb) in enumerate(zip(records, embeddings)):
                cur.execute(
                    "DELETE FROM chunks WHERE file = ? AND chunk_idx = ?",
                    (rec.metadata.get("file", ""), rec.metadata.get("chunk_idx", 0)),
                )
                import json as _json
                cur.execute(
                    "INSERT INTO chunks (id, text, source, file, chunk_idx, created_at, metadata) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        rec.id,
                        rec.text,
                        str(rec.metadata.get("source", "")),
                        str(rec.metadata.get("file", "")),
                        int(rec.metadata.get("chunk_idx", 0)),
                        time.time(),
                        _json.dumps(rec.metadata, ensure_ascii=False),
                    ),
                )
                cur.execute(
                    "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                    (cur.lastrowid, _serialize(emb)),
                )
                if (i + 1) % self.BATCH_SIZE == 0:
                    self._conn.commit()
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def delete_by_source(self, source: str) -> None:
        """Remove all chunks with the given *source* identifier."""
        self._conn.execute(
            "DELETE FROM vec_chunks WHERE rowid IN "
            "(SELECT id FROM chunks WHERE source = ?)",
            (source,),
        )
        self._conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
        self._conn.commit()

    def delete_by_file(self, file_path: str) -> None:
        """Remove all chunks belonging to a specific file path."""
        self._conn.execute(
            "DELETE FROM vec_chunks WHERE rowid IN "
            "(SELECT id FROM chunks WHERE file = ?)",
            (file_path,),
        )
        self._conn.execute("DELETE FROM chunks WHERE file = ?", (file_path,))
        self._conn.commit()

    def search(
        self,
        query: list[float],
        top_k: int = 5,
        filters: dict[str, object] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        """Search for the *top_k* most similar vectors.

        *filters* 是一个 ``{json_field: value}`` 字典，用于在向量检索后
        对 ``chunks.metadata`` JSON 列做条件过滤。支持两种匹配模式：

          - **精确匹配**：值不以 ``%`` 开头 → ``json_extract(...) = ?``
          - **LIKE 匹配**：值以 ``%`` 开头（如 ``"%骑士Bob%"``）→ ``LIKE ?``

        Usage::

            # LIKE 模糊匹配（值含 %）
            store.search(query_vec, filters={"title": "%骑士Bob%"})

            # 精确匹配
            store.search(query_vec, filters={"batch_id": "0"})

        字段名不硬编码 — 由调用方按 metadata 中的实际键名传入。
        """
        import json as _json

        vec = _serialize(query)
        where_clauses: list[str] = []
        params: list[object] = [vec, top_k]

        if filters:
            for field, val in filters.items():
                if isinstance(val, str) and "%" in val:
                    where_clauses.append(
                        f"json_extract(c.metadata, '$.{field}') LIKE ?"
                    )
                    params.append(val)
                else:
                    where_clauses.append(
                        f"json_extract(c.metadata, '$.{field}') = ?"
                    )
                    params.append(val)

        where_sql = ""
        if where_clauses:
            where_sql = " AND ".join(where_clauses)
            where_sql = "WHERE " + where_sql

        rows = self._conn.execute(
            f"""
            SELECT c.id, c.text, c.metadata, v.distance
            FROM (
                SELECT rowid, distance FROM vec_chunks
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
            ) v
            JOIN chunks c ON c.id = v.rowid
            {where_sql}
            """,
            tuple(params),
        ).fetchall()

        result: list[tuple[ChunkRecord, float]] = []
        for r in rows:
            try:
                meta = _json.loads(r[2]) if isinstance(r[2], str) else {}
            except (ValueError, TypeError):
                meta = {}
            result.append((
                ChunkRecord(id=r[0], text=r[1], metadata=meta),
                r[3],
            ))
        return result

    def clear(self) -> None:
        self._conn.execute("DELETE FROM vec_chunks")
        self._conn.execute("DELETE FROM chunks")
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    # ── internal ──────────────────────────────────────────────

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
        # 兼容旧表：metadata 列若不存在则添加（新表已有，仅旧表迁移）
        col_info = conn.execute("PRAGMA table_info(chunks)").fetchall()
        existing_cols = {r[1] for r in col_info}
        if "metadata" not in existing_cols:
            conn.execute("ALTER TABLE chunks ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        try:
            import sqlite_vec

            conn.enable_load_extension(True)
            conn.load_extension(sqlite_vec.loadable_path())
        except ImportError as exc:
            raise VectorStoreError(
                "sqlite-vec is required: pip install sqlite-vec"
            ) from exc
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to load sqlite-vec: {exc}"
            ) from exc
        conn.executescript(
            "DROP TABLE IF EXISTS vec_chunks;"
        )
        conn.executescript(
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
            f"USING vec0(embedding float[{self._dim}] distance_metric=cosine);"
        )
        return conn


def _serialize(vec: list[float]) -> bytes:
    import struct

    return struct.pack(f"{len(vec)}f", *vec)
