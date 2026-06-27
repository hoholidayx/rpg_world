"""VectorIndexManager — watches file sources and updates the vector store.

FileWatcher 回调签名是 ``Callable[[], None]``（无参数），所以无法感知具体哪个
文件发生了变更。本模块在 source 级回调后扫描文件清单，并通过 SQLite manifest
只重建新增、变更或删除的文件。

所有操作同步执行，不依赖事件循环／asyncio。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rp_memory.chunker import Chunker, FileTextExtractor
from llm_service.base_provider import (
    EmbeddingProviderError,
    LLMProvider as EmbeddingProvider,
)
from rp_memory.storage.types import ChunkRecord, IndexedFileState
from rp_memory.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class WatchSource:
    """一个待监听的文件或目录。"""

    path: Path
    source_id: str
    file_filter: Callable[[Path], bool] | None = None


class VectorIndexManager:
    """多源向量索引管理器（同步版）。

    职责：
      - 将 watch source 注册到 FileWatcher
      - 文件变更时增量同步对应 source
      - 手动全量重建（同步，调用线程阻塞直到完成）

    所有嵌入调用直接走 ``embed_sync()``，无事件循环／线程切换。
    """

    def __init__(
        self,
        store: VectorStore,
        embedding: EmbeddingProvider | None,
        sources: list[WatchSource],
        chunker: Chunker | None = None,
    ) -> None:
        self._store = store
        self._embedding = embedding
        self._sources = sources
        self._chunker = chunker or Chunker()

    # ── lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """将每个 watch source 注册到全局 FileWatcher。"""
        logger.info("[VectorIndex] start — registering watch sources count=%s", len(self._sources))
        for src in self._sources:
            self._register(src)
        logger.info("[VectorIndex] start done")

    def reindex_all(self) -> None:
        """强制全量索引：遍历所有 source，同步阻塞直到嵌入+写入完成。

        调用线程会等待全部文件处理完毕。
        """
        logger.info("[VectorIndex] reindex_all start — sources=%s", len(self._sources))
        for src in self._sources:
            self.sync_source(src.source_id, force=True)
        logger.info("[VectorIndex] reindex_all done")

    def sync_all(self, *, force: bool = False) -> None:
        """同步所有 source，默认只处理新增、变更和删除文件。"""
        logger.info("[VectorIndex] sync_all start — sources=%s force=%s", len(self._sources), force)
        for src in self._sources:
            self._sync_source(src, force=force)
        logger.info("[VectorIndex] sync_all done")

    def sync_source(self, source_id: str, *, force: bool = False) -> None:
        """同步一个 source，默认只处理新增、变更和删除文件。"""
        for src in self._sources:
            if src.source_id == source_id:
                self._sync_source(src, force=force)
                return
        logger.warning("[VectorIndex] source not found: %s", source_id)

    # ── FileWatcher callback ───────────────────────────────────────────

    def on_source_change(self, source_id: str) -> None:
        """FileWatcher 回调：增量同步指定 source。"""
        logger.info("[VectorIndex] source change detected — source_id=%s", source_id)
        self.sync_source(source_id)

    # ── internal ───────────────────────────────────────────────────────

    def _register(self, src: WatchSource) -> None:
        from rpg_core.utils.watcher import get_watcher

        target = src.path if src.path.is_dir() else src.path.parent
        if not target.exists():
            logger.warning("[VectorIndex] path does not exist, skipping: %s", target)
            return

        def callback() -> None:
            self.on_source_change(src.source_id)

        get_watcher().register(target.resolve(), callback)
        logger.info("[VectorIndex] registered source=%s path=%s", src.source_id, target)

    def _iter_files(self, src: WatchSource) -> list[Path]:
        if not src.path.exists():
            return []
        if src.path.is_file():
            file_path = src.path.resolve()
            return [file_path] if (src.file_filter is None or src.file_filter(file_path)) else []
        return [
            f.resolve() for f in sorted(src.path.rglob("*"))
            if f.is_file() and (src.file_filter is None or src.file_filter(f))
        ]

    def _sync_source(self, src: WatchSource, *, force: bool = False) -> None:
        files = self._iter_files(src)
        current_files = {str(fp): fp for fp in files}
        indexed = self._store.list_indexed_files(src.source_id)

        deleted = sorted(set(indexed) - set(current_files))
        for file_path in deleted:
            try:
                self._store.delete_file_index(file_path)
                logger.info("[VectorIndex] deleted stale file index=%s source=%s", file_path, src.source_id)
            except Exception as exc:
                logger.warning("[VectorIndex] failed to delete stale file index=%s error=%s", file_path, exc)

        indexed_count = skipped_count = error_count = 0
        logger.info(
            "[VectorIndex] sync source=%s path=%s files=%s deleted=%s force=%s",
            src.source_id, src.path, len(files), len(deleted), force,
        )
        for fp in files:
            try:
                stat = fp.stat()
                file_key = str(fp.resolve())
            except OSError as exc:
                error_count += 1
                logger.warning("[VectorIndex]   %s — stat error: %s", fp.name, exc)
                continue

            previous = indexed.get(file_key)
            if not force and previous is not None and self._same_stat(previous, stat):
                skipped_count += 1
                continue

            try:
                state = self._file_state(fp, src.source_id, stat=stat, file_key=file_key)
            except OSError as exc:
                error_count += 1
                logger.warning("[VectorIndex]   %s — hash error: %s", fp.name, exc)
                continue
            if not force and previous is not None and self._is_unchanged(previous, state):
                skipped_count += 1
                continue
            if self._index_file(fp, state):
                indexed_count += 1
            else:
                error_count += 1

        logger.info(
            "[VectorIndex] sync done source=%s indexed=%s skipped=%s deleted=%s errors=%s",
            src.source_id, indexed_count, skipped_count, len(deleted), error_count,
        )

    def _index_file(self, file_path: Path, file_state: IndexedFileState) -> bool:
        """对单个文件执行：提取文本 → 分块 → 嵌入 → 原子替换。"""
        source_id = file_state.source_id
        file_key = file_state.file

        # 1. 提取文本
        try:
            text, fm = FileTextExtractor.extract(file_path)
            if not text.strip():
                file_state.status = "empty"
                file_state.chunk_count = 0
                file_state.last_error = ""
                self._store.replace_file(file_key, [], None, file_state)
                logger.info("[VectorIndex] indexed empty file=%s source=%s", file_path.name, source_id)
                return True
        except Exception as exc:
            self._mark_error(file_state, f"read error: {exc}")
            logger.warning("[VectorIndex]   %s — read error: %s", file_path.name, exc)
            return False
        logger.debug("[VectorIndex]   %s — extracted %s chars", file_path.name, len(text))

        # 2. 分块
        try:
            chunks = self._chunker.chunk_file(
                text=text,
                file_path=file_key,
                front_matter=fm,
            )
        except Exception as exc:
            self._mark_error(file_state, f"chunking error: {exc}")
            logger.warning("[VectorIndex]   %s — chunking error: %s", file_path.name, exc)
            return False

        if not chunks:
            file_state.status = "empty"
            file_state.chunk_count = 0
            file_state.last_error = ""
            self._store.replace_file(file_key, [], None, file_state)
            return True
        logger.debug("[VectorIndex]   %s — %s chunks", file_path.name, len(chunks))

        # 3. 构造 ChunkRecord（稳定 ID = sha256(file + chunk_idx)）
        records: list[ChunkRecord] = []
        for chunk in chunks:
            chunk_idx = int(chunk.metadata.get("chunk_idx", 0))
            metadata = dict(chunk.metadata)
            metadata["source"] = source_id
            metadata["file"] = file_key
            metadata["chunk_idx"] = chunk_idx
            uid = hashlib.sha256(
                f"{file_key}:{chunk_idx}".encode()
            ).hexdigest()[:16]
            rid = int(uid, 16) % (2**63)
            records.append(ChunkRecord(id=rid, text=chunk.text, metadata=metadata))

        # 4. 嵌入（同步，不走线程切换）
        embeddings: list[list[float]] | None = None
        if self._embedding is not None:
            logger.info(
                "[VectorIndex] indexing file=%s mode=vector chars=%s chunks=%s",
                file_path.name, len(text), len(records),
            )
            try:
                embeddings = self._embedding.embed_sync([r.text for r in records])
                logger.debug(
                    "[VectorIndex]   %s — embedded %s vectors (dim=%s)",
                    file_path.name, len(embeddings), len(embeddings[0]) if embeddings else 0,
                )
            except (EmbeddingProviderError, Exception) as exc:
                self._mark_error(file_state, f"embed error: {exc}")
                logger.warning("[VectorIndex]   %s — embed error: %s", file_path.name, exc)
                return False
        else:
            logger.info(
                "[VectorIndex] indexing file=%s mode=text-index-only chars=%s chunks=%s",
                file_path.name, len(text), len(records),
            )

        # 5. 原子替换本文件旧 chunks、向量、FTS 与 manifest
        try:
            file_state.status = "indexed"
            file_state.chunk_count = len(records)
            file_state.last_error = ""
            self._store.replace_file(file_key, records, embeddings, file_state)
            logger.info(
                "[VectorIndex] indexed file=%s chunks=%s source=%s",
                file_path.name, len(records), source_id,
            )
            return True
        except Exception as exc:
            self._mark_error(file_state, f"upsert error: {exc}")
            logger.warning("[VectorIndex]   %s — upsert error: %s", file_path.name, exc)
            return False

    def _file_state(
        self,
        file_path: Path,
        source_id: str,
        *,
        stat: object | None = None,
        file_key: str | None = None,
    ) -> IndexedFileState:
        stat = file_path.stat() if stat is None else stat
        content_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        return IndexedFileState(
            file=file_key or str(file_path.resolve()),
            source_id=source_id,
            mtime_ns=int(stat.st_mtime_ns),
            size=int(stat.st_size),
            content_hash=content_hash,
        )

    def _mark_error(self, file_state: IndexedFileState, error: str) -> None:
        try:
            self._store.mark_file_error(file_state, error)
        except Exception as exc:
            logger.warning(
                "[VectorIndex] failed to record file error file=%s error=%s record_error=%s",
                file_state.file, error, exc,
            )

    @staticmethod
    def _same_stat(previous: IndexedFileState, current_stat: object) -> bool:
        if previous.status not in {"indexed", "empty"}:
            return False
        return (
            previous.mtime_ns == int(current_stat.st_mtime_ns)
            and previous.size == int(current_stat.st_size)
        )

    @staticmethod
    def _is_unchanged(previous: IndexedFileState, current: IndexedFileState) -> bool:
        if previous.status not in {"indexed", "empty"}:
            return False
        return (
            previous.mtime_ns == current.mtime_ns
            and previous.size == current.size
            and previous.content_hash == current.content_hash
        )
