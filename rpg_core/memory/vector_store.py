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

from rpg_world.rpg_core.memory.bigram_tokenizer import tokenize_bigram
from rpg_world.rpg_core.memory.candidate import MemoryCandidate


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

    def __init__(self, db_path: str | Path, dimension: int | None) -> None:
        self._path = str(db_path)
        self._dim = dimension
        self._conn = self._open()

    # ── public API ────────────────────────────────────────────

    def upsert(
        self,
        records: list[ChunkRecord],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """Insert or replace chunks.  Stale entries (same file+idx) are removed."""
        if not records:
            return
        if self._has_vector_index() and (embeddings is None or len(embeddings) != len(records)):
            raise VectorStoreError("embedding count does not match record count")
        cur = self._conn.cursor()
        try:
            for i, rec in enumerate(records):
                emb = embeddings[i] if embeddings is not None and i < len(embeddings) else None
                stale_rows = cur.execute(
                    "SELECT id FROM chunks WHERE file = ? AND chunk_idx = ?",
                    (rec.metadata.get("file", ""), rec.metadata.get("chunk_idx", 0)),
                ).fetchall()
                for row in stale_rows:
                    stale_id = int(row[0])
                    if self._has_vector_index():
                        cur.execute("DELETE FROM vec_chunks WHERE rowid = ?", (stale_id,))
                    cur.execute("DELETE FROM memory_fts WHERE rowid = ?", (stale_id,))
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
                if self._has_vector_index():
                    if emb is None:
                        raise VectorStoreError("missing embedding for vector insert")
                    cur.execute(
                        "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                        (cur.lastrowid, _serialize(emb)),
                    )
                self._upsert_fts_for_memory(cur, rec.id, rec.text)
                if (i + 1) % self.BATCH_SIZE == 0:
                    self._conn.commit()
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def delete_by_source(self, source: str) -> None:
        """Remove all chunks with the given *source* identifier."""
        rows = self._conn.execute(
            "SELECT id FROM chunks WHERE source = ?",
            (source,),
        ).fetchall()
        if self._has_vector_index():
            self._conn.execute(
                "DELETE FROM vec_chunks WHERE rowid IN "
                "(SELECT id FROM chunks WHERE source = ?)",
                (source,),
            )
        for row in rows:
            self.delete_fts_for_memory(int(row[0]), commit=False)
        self._conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
        self._conn.commit()

    def delete_by_file(self, file_path: str) -> None:
        """Remove all chunks belonging to a specific file path."""
        rows = self._conn.execute(
            "SELECT id FROM chunks WHERE file = ?",
            (file_path,),
        ).fetchall()
        if self._has_vector_index():
            self._conn.execute(
                "DELETE FROM vec_chunks WHERE rowid IN "
                "(SELECT id FROM chunks WHERE file = ?)",
                (file_path,),
            )
        for row in rows:
            self.delete_fts_for_memory(int(row[0]), commit=False)
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
        if not self._has_vector_index():
            raise VectorStoreError("vector search unavailable without embedding dimension")

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
            SELECT c.id, c.text, c.metadata, c.created_at, v.distance
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
            meta["created_at"] = r[3]
            result.append((
                ChunkRecord(id=r[0], text=r[1], metadata=meta),
                r[4],
            ))
        return result

    def keyword_search(self, query: str, limit: int = 50) -> list[MemoryCandidate]:
        """Search chunks through the bigram FTS5 index."""
        import json as _json

        grams = _fts_query(tokenize_bigram(query))
        if not grams:
            return []

        rows = self._conn.execute(
            """
            SELECT c.id, c.text, c.metadata, c.created_at, bm25(memory_fts) AS rank
            FROM memory_fts
            JOIN chunks c ON c.id = memory_fts.rowid
            WHERE memory_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (grams, limit),
        ).fetchall()

        result: list[MemoryCandidate] = []
        for row in rows:
            try:
                meta = _json.loads(row[2]) if isinstance(row[2], str) else {}
            except (ValueError, TypeError):
                meta = {}
            meta["created_at"] = row[3]
            bm25_score = float(row[4])
            result.append(
                MemoryCandidate(
                    memory_id=int(row[0]),
                    content=str(row[1]),
                    metadata=meta,
                    keyword_score=1.0 / (1.0 + max(bm25_score, 0.0)),
                    debug={"keyword_bm25": bm25_score},
                )
            )
        return result

    def substring_search(self, query: str, limit: int = 50) -> list[MemoryCandidate]:
        """Search chunks through plain string matching only.

        This is the final fallback stage when vector and FTS retrieval fail
        or return no useful candidates.
        """
        import json as _json

        normalized = " ".join((query or "").split())
        if not normalized:
            return []

        terms = [term for term in normalized.split(" ") if term]
        clauses: list[str] = []
        params: list[object] = []
        if len(terms) <= 1:
            clauses.append("c.text LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(normalized)}%")
        else:
            for term in terms:
                clauses.append("c.text LIKE ? ESCAPE '\\'")
                params.append(f"%{_escape_like(term)}%")

        rows = self._conn.execute(
            f"""
            SELECT c.id, c.text, c.metadata, c.created_at
            FROM chunks c
            WHERE {' AND '.join(clauses)}
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()

        result: list[MemoryCandidate] = []
        for row in rows:
            try:
                meta = _json.loads(row[2]) if isinstance(row[2], str) else {}
            except (ValueError, TypeError):
                meta = {}
            meta["created_at"] = row[3]
            normalized_text = str(row[1])
            match_score = _substring_match_score(normalized, normalized_text)
            result.append(
                MemoryCandidate(
                    memory_id=int(row[0]),
                    content=normalized_text,
                    metadata=meta,
                    keyword_score=match_score,
                    debug={"substring_query": normalized},
                )
            )
        return result

    def rebuild_fts_index(self) -> None:
        """Rebuild FTS rows from the canonical ``chunks`` table."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM memory_fts")
        for memory_id, text in cur.execute("SELECT id, text FROM chunks").fetchall():
            self._upsert_fts_for_memory(cur, int(memory_id), str(text))
        self._conn.commit()

    def upsert_fts_for_memory(self, memory_id: int, content: str) -> None:
        """Insert or replace one FTS row."""
        cur = self._conn.cursor()
        self._upsert_fts_for_memory(cur, memory_id, content)
        self._conn.commit()

    def delete_fts_for_memory(self, memory_id: int, commit: bool = True) -> None:
        """Delete one FTS row."""
        self._conn.execute("DELETE FROM memory_fts WHERE rowid = ?", (memory_id,))
        if commit:
            self._conn.commit()

    def clear(self) -> None:
        if self._has_vector_index():
            self._conn.execute("DELETE FROM vec_chunks")
        self._conn.execute("DELETE FROM memory_fts")
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
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(grams);
            """
        )
        # 兼容旧表：metadata 列若不存在则添加（新表已有，仅旧表迁移）
        col_info = conn.execute("PRAGMA table_info(chunks)").fetchall()
        existing_cols = {r[1] for r in col_info}
        if "metadata" not in existing_cols:
            conn.execute("ALTER TABLE chunks ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        if self._has_vector_index():
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

    def _upsert_fts_for_memory(
        self,
        cur: sqlite3.Cursor,
        memory_id: int,
        content: str,
    ) -> None:
        grams = " ".join(tokenize_bigram(content))
        cur.execute("DELETE FROM memory_fts WHERE rowid = ?", (memory_id,))
        if grams:
            cur.execute(
                "INSERT INTO memory_fts(rowid, grams) VALUES (?, ?)",
                (memory_id, grams),
            )

    def _has_vector_index(self) -> bool:
        return self._dim is not None and self._dim > 0


def _serialize(vec: list[float]) -> bytes:
    import struct

    return struct.pack(f"{len(vec)}f", *vec)


def _fts_query(tokens: list[str]) -> str:
    quoted: list[str] = []
    for token in tokens:
        escaped = token.replace('"', '""')
        quoted.append(f'"{escaped}"')
    return " OR ".join(quoted)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _substring_match_score(query: str, text: str) -> float:
    if not query or not text:
        return 0.0
    normalized_query = " ".join(query.split())
    if normalized_query and normalized_query in text:
        return 1.0
    terms = [term for term in normalized_query.split(" ") if term]
    if not terms:
        return 0.0
    matches = sum(1 for term in terms if term in text)
    return matches / len(terms)
