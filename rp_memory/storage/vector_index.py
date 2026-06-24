"""Vector similarity index for memory chunks."""

from __future__ import annotations

import json as _json
import math

from loguru import logger

from rp_memory.storage.repository import MemoryRepository
from rp_memory.storage.types import ChunkRecord, VectorStoreError


class VectorIndex:
    """Vector search backend over the shared repository."""

    def __init__(self, repository: MemoryRepository, dimension: int | None) -> None:
        self._repository = repository
        self._dim = dimension
        self._enabled = self._dim is not None and self._dim > 0
        self._backend = "none"
        if self._enabled:
            self._open_vector_table()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def backend(self) -> str:
        return self._backend

    def insert(self, rowid: int, embedding: list[float]) -> None:
        if not self._enabled:
            raise VectorStoreError("vector index unavailable without embedding dimension")
        if self._backend == "sqlite_vec":
            self._repository.conn.execute(
                "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                (rowid, _serialize(embedding)),
            )
        elif self._backend == "python":
            self._repository.conn.execute(
                "INSERT INTO vec_embeddings (rowid, embedding) VALUES (?, ?)",
                (rowid, _serialize(embedding)),
            )
        else:
            raise VectorStoreError("vector backend not initialized")

    def delete_rows(self, rowids: list[int]) -> None:
        if not self._enabled or not rowids:
            return
        placeholders = ",".join("?" for _ in rowids)
        table = "vec_chunks" if self._backend == "sqlite_vec" else "vec_embeddings"
        self._repository.conn.execute(
            f"DELETE FROM {table} WHERE rowid IN ({placeholders})",
            tuple(rowids),
        )

    def search(
        self,
        query: list[float],
        top_k: int = 5,
        filters: dict[str, object] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        if not self._enabled:
            raise VectorStoreError("vector search unavailable without embedding dimension")

        if self._backend == "python":
            return self._search_python(query, top_k=top_k, filters=filters)

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

        rows = self._repository.conn.execute(
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
            result.append(
                (
                    ChunkRecord(id=r[0], text=r[1], metadata=meta),
                    r[4],
                )
            )
        return result

    def clear(self) -> None:
        if self._enabled:
            table = "vec_chunks" if self._backend == "sqlite_vec" else "vec_embeddings"
            self._repository.conn.execute(f"DELETE FROM {table}")

    def _open_vector_table(self) -> None:
        import sqlite_vec

        try:
            sqlite_vec.load(self._repository.conn)
            logger.info("[VectorIndex] sqlite_vec extension loaded")
        except Exception as exc:
            logger.warning("[VectorIndex] sqlite_vec.load() failed: {} (type={})", exc, type(exc).__name__)
            self._backend = "python"
            self._repository.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS vec_embeddings (
                    rowid INTEGER PRIMARY KEY,
                    embedding BLOB NOT NULL
                );
                """
            )
            logger.info("[VectorIndex] fallback to python backend (vec_embeddings table created)")
            logger.info("[VectorIndex] backend ready: {}", self._backend)
            return

        try:
            self._backend = "sqlite_vec"
            self._repository.conn.executescript(
                "DROP TABLE IF EXISTS vec_embeddings;"
            )
            self._repository.conn.executescript(
                "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
                f"USING vec0(embedding float[{self._dim}] distance_metric=cosine);"
            )
            logger.info("[VectorIndex] vec_chunks virtual table created (backend=sqlite_vec)")
            logger.info("[VectorIndex] backend ready: {}", self._backend)
        except Exception as exc:
            logger.error("[VectorIndex] vec_chunks creation failed: {} (type={})", exc, type(exc).__name__)
            self._backend = "python"
            self._repository.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS vec_embeddings (
                    rowid INTEGER PRIMARY KEY,
                    embedding BLOB NOT NULL
                );
                """
            )
            logger.info("[VectorIndex] fallback to python backend after vec_chunks failure")
            logger.info("[VectorIndex] backend ready: {}", self._backend)

    def _search_python(
        self,
        query: list[float],
        top_k: int = 5,
        filters: dict[str, object] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        rows = self._repository.conn.execute(
            """
            SELECT c.id, c.text, c.metadata, c.created_at, v.embedding
            FROM vec_embeddings v
            JOIN chunks c ON c.id = v.rowid
            """,
        ).fetchall()
        result: list[tuple[ChunkRecord, float]] = []
        for row in rows:
            try:
                meta = _json.loads(row[2]) if isinstance(row[2], str) else {}
            except (ValueError, TypeError):
                meta = {}
            meta["created_at"] = row[3]
            if not _passes_filters(meta, filters):
                continue
            stored = _deserialize(row[4])
            distance = _cosine_distance(query, stored)
            result.append((ChunkRecord(id=row[0], text=row[1], metadata=meta), distance))
        result.sort(key=lambda item: item[1])
        return result[:top_k]


def _serialize(vec: list[float]) -> bytes:
    import struct

    return struct.pack(f"{len(vec)}f", *vec)


def _deserialize(blob: bytes) -> list[float]:
    import struct

    if not blob:
        return []
    count = len(blob) // 4
    if count <= 0:
        return []
    return list(struct.unpack(f"{count}f", blob))


def _cosine_distance(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 1.0
    length = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(length))
    norm_a = math.sqrt(sum(v * v for v in a[:length]))
    norm_b = math.sqrt(sum(v * v for v in b[:length]))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    similarity = dot / (norm_a * norm_b)
    return max(0.0, 1.0 - similarity)


def _passes_filters(meta: dict[str, object], filters: dict[str, object] | None) -> bool:
    if not filters:
        return True
    for field, val in filters.items():
        actual = meta.get(field)
        if isinstance(val, str) and "%" in val:
            needle = val.strip("%")
            if needle not in str(actual):
                return False
        elif actual != val:
            return False
    return True
