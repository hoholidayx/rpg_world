"""Vector storage facade for memory chunks.

This module keeps the vector-oriented store API and delegates canonical
chunk persistence and text indexing to sibling storage components.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from rpg_world.rpg_core.memory.storage.repository import MemoryRepository
from rpg_world.rpg_core.memory.storage.text_index import TextIndex
from rpg_world.rpg_core.memory.storage.types import ChunkRecord, VectorStoreError
from rpg_world.rpg_core.memory.storage.vector_index import VectorIndex


class VectorStore:
    """Vector-first storage wrapper.

    The repository and text index are managed as collaborators, but the public
    API is intentionally vector-oriented.
    """

    BATCH_SIZE = 100

    def __init__(
        self,
        db_path: str | Path,
        dimension: int | None,
        *,
        keyword_tokenizer: str = "jieba",
        jieba_dict: str = "",
    ) -> None:
        self._path = str(db_path)
        self._dim = dimension
        self._repo = MemoryRepository(db_path)
        self._text_index = TextIndex(
            self._repo,
            keyword_tokenizer=keyword_tokenizer,
            jieba_dict=jieba_dict,
        )
        self._vector_index: VectorIndex | None = None
        if dimension is not None:
            try:
                self._vector_index = VectorIndex(self._repo, dimension)
            except VectorStoreError as exc:
                logger.warning("[VectorStore] vector index init failed, retry text-index-only: {}", exc)
                self._vector_index = None
                self._dim = None
        backend = self._vector_index.backend if self._vector_index is not None else "none"
        logger.info(
            "[VectorStore] ready: {} (vector_mode={} backend={})",
            self._path,
            self._vector_index is not None and self._vector_index.enabled,
            backend,
        )

    def upsert(
        self,
        records: list[ChunkRecord],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        if not records:
            return
        if self._has_vector_index() and (embeddings is None or len(embeddings) != len(records)):
            raise VectorStoreError("embedding count does not match record count")

        conn = self._repo.conn
        try:
            for i, rec in enumerate(records):
                emb = embeddings[i] if embeddings is not None and i < len(embeddings) else None
                stale_ids = self._repo.delete_chunk_by_file_and_idx(
                    file_path=str(rec.metadata.get("file", "")),
                    chunk_idx=int(rec.metadata.get("chunk_idx", 0)),
                )
                self._delete_secondary_rows(stale_ids)

                rowid = self._repo.upsert_chunk(rec)
                if self._vector_index is not None:
                    if emb is None:
                        raise VectorStoreError("missing embedding for vector insert")
                    self._vector_index.insert(rowid, emb)
                self._text_index.upsert(rowid, rec.text)

                if (i + 1) % self.BATCH_SIZE == 0:
                    conn.commit()
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def delete_by_source(self, source: str) -> None:
        conn = self._repo.conn
        try:
            stale_ids = self._repo.delete_chunk_by_source(source)
            self._delete_secondary_rows(stale_ids)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def delete_by_file(self, file_path: str) -> None:
        conn = self._repo.conn
        try:
            stale_ids = self._repo.delete_chunk_by_file(file_path)
            self._delete_secondary_rows(stale_ids)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def search(
        self,
        query: list[float],
        top_k: int = 5,
        filters: dict[str, object] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        if self._vector_index is None:
            raise VectorStoreError("vector search unavailable without embedding dimension")
        return self._vector_index.search(query, top_k=top_k, filters=filters)

    def keyword_search(self, query: str, limit: int = 50):
        return self._text_index.keyword_search(query, limit=limit)

    def substring_search(self, query: str, limit: int = 50):
        return self._text_index.substring_search(query, limit=limit)

    def rebuild_fts_index(self) -> None:
        self._text_index.rebuild()

    def upsert_fts_for_memory(self, memory_id: int, content: str) -> None:
        self._text_index.upsert(memory_id, content)
        self._repo.conn.commit()

    def delete_fts_for_memory(self, memory_id: int, commit: bool = True) -> None:
        self._text_index.delete_rows([memory_id])
        if commit:
            self._repo.conn.commit()

    def clear(self) -> None:
        if self._vector_index is not None:
            self._vector_index.clear()
        self._text_index.clear()
        self._repo.clear_chunks()
        self._repo.conn.commit()

    def close(self) -> None:
        self._repo.close()

    def _delete_secondary_rows(self, rowids: list[int]) -> None:
        if self._vector_index is not None:
            self._vector_index.delete_rows(rowids)
        self._text_index.delete_rows(rowids)

    def _has_vector_index(self) -> bool:
        return self._vector_index is not None and self._vector_index.enabled
