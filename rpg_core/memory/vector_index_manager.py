"""VectorIndexManager — watches file sources and updates the vector store on change.

FileWatcher 回调签名是 ``Callable[[], None]``（无参数），所以无法感知具体哪个
文件发生了变更。本模块的策略是：当某个 source 触发变更，对该 source 下所有文件
**整体重新索引**（与 BaseManager 的 reload 模式一致）。

所有操作同步执行，不依赖事件循环／asyncio。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rpg_world.rpg_core.memory.chunker import Chunker, FileTextExtractor
from rpg_world.rpg_core.memory.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderError,
)
from rpg_world.rpg_core.memory.vector_store import ChunkRecord, VectorStore

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
      - 文件变更时重新索引对应 source 的全部文件
      - 初始全量索引（同步，调用线程阻塞直到完成）

    所有嵌入调用直接走 ``embed_sync()``，无事件循环／线程切换。
    """

    def __init__(
        self,
        store: VectorStore,
        embedding: EmbeddingProvider,
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
        logger.info("[VectorIndex] registering %d watch sources ...", len(self._sources))
        for src in self._sources:
            self._register(src)
        logger.info("[VectorIndex] FileWatcher registration done")

    def reindex_all(self) -> None:
        """全量索引：遍历所有 source，同步阻塞直到嵌入+写入完成。

        调用线程会等待全部文件处理完毕。
        """
        logger.info("[VectorIndex] reindex_all start — %d sources", len(self._sources))
        total_files = 0
        for src in self._sources:
            files = self._iter_files(src)
            logger.info(
                "[VectorIndex]   source=%s path=%s files=%d",
                src.source_id, src.path, len(files),
            )
            for fp in files:
                self._index_file(fp, src.source_id)
                total_files += 1
        logger.info("[VectorIndex] reindex_all done — %d files indexed", total_files)

    # ── FileWatcher callback ───────────────────────────────────────────

    def on_source_change(self, source_id: str) -> None:
        """FileWatcher 回调：重新索引指定 source 的全部文件。"""
        logger.info("[VectorIndex] source change detected: %s", source_id)
        for src in self._sources:
            if src.source_id == source_id:
                for fp in self._iter_files(src):
                    self._index_file(fp, source_id)
                break

    # ── internal ───────────────────────────────────────────────────────

    def _register(self, src: WatchSource) -> None:
        from rpg_world.rpg_core.utils.watcher import get_watcher

        target = src.path if src.path.is_dir() else src.path.parent
        if not target.exists():
            logger.warning("[VectorIndex] path does not exist, skipping: %s", target)
            return

        def callback() -> None:
            self.on_source_change(src.source_id)

        get_watcher().register(target.resolve(), callback)
        logger.debug("[VectorIndex]   registered source=%s path=%s", src.source_id, target)

    def _iter_files(self, src: WatchSource) -> list[Path]:
        if not src.path.exists():
            return []
        if src.path.is_file():
            return [src.path] if (src.file_filter is None or src.file_filter(src.path)) else []
        return [
            f for f in sorted(src.path.rglob("*"))
            if f.is_file() and (src.file_filter is None or src.file_filter(f))
        ]

    def _index_file(self, file_path: Path, source_id: str) -> None:
        """对单个文件执行：提取文本 → 分块 → 嵌入 → upsert（同步）。"""
        # 1. 提取文本
        try:
            text, fm = FileTextExtractor.extract(file_path)
            if not text.strip():
                logger.debug("[VectorIndex]   %s — empty, skipped", file_path.name)
                return
        except OSError as exc:
            logger.warning("[VectorIndex]   %s — read error: %s", file_path.name, exc)
            return
        logger.debug("[VectorIndex]   %s — extracted %d chars", file_path.name, len(text))

        # 2. 分块
        try:
            chunks = self._chunker.chunk_file(
                text=text,
                file_path=str(file_path),
                front_matter=fm,
            )
        except Exception as exc:
            logger.warning("[VectorIndex]   %s — chunking error: %s", file_path.name, exc)
            return

        if not chunks:
            return
        logger.debug("[VectorIndex]   %s — %d chunks", file_path.name, len(chunks))

        # 3. 构造 ChunkRecord（稳定 ID = sha256(file + chunk_idx)）
        records: list[ChunkRecord] = []
        for chunk in chunks:
            uid = hashlib.sha256(
                f"{file_path}:{chunk.metadata.get('chunk_idx', 0)}".encode()
            ).hexdigest()[:16]
            rid = int(uid, 16) % (2**63)
            records.append(ChunkRecord(id=rid, text=chunk.text, metadata=chunk.metadata))

        # 4. 嵌入（同步，不走线程切换）
        logger.info("[VectorIndex]   embedding %s (%d chars → %d chunks)...", file_path.name, len(text), len(records))
        try:
            embeddings = self._embedding.embed_sync([r.text for r in records])
            logger.debug(
                "[VectorIndex]   %s — embedded %d vectors (dim=%d)",
                file_path.name, len(embeddings), len(embeddings[0]) if embeddings else 0,
            )
        except (EmbeddingProviderError, Exception) as exc:
            logger.warning("[VectorIndex]   %s — embed error: %s", file_path.name, exc)
            return

        # 5. upsert（先删除本文件旧 chunks，再插入新的）
        try:
            self._store.delete_by_file(str(file_path))
            self._store.upsert(records, embeddings)
            logger.info(
                "[VectorIndex]   ✓ %s — %d chunks indexed (source=%s)",
                file_path.name, len(records), source_id,
            )
        except Exception as exc:
            logger.warning("[VectorIndex]   %s — upsert error: %s", file_path.name, exc)
