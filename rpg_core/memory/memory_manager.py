"""MemoryManager — 统一记忆管理入口，封装所有记忆实现细节。

所有操作同步执行，不依赖事件循环。

初始化策略：
  1. ``create()`` — 加载模型 + 建 DB
  2. ``init()`` — 如果 DB 无数据则全量索引，已有数据则跳过（FileWatcher 负责增量更新）
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg_world.rpg_core.memory.recalled_memory import RecalledMemoryStore
    from rpg_world.rpg_core.memory.retriever import BaseRetriever
    from rpg_world.rpg_core.memory.vector_index_manager import VectorIndexManager
    from rpg_world.rpg_core.settings import MemorySettings

from loguru import logger

from dataclasses import dataclass, field


@dataclass
class RecallItem:
    """一条召回结果的结构化数据。"""

    text: str
    """匹配到的文本内容。"""

    score: float
    """相似度分数（0~1，越高越相关）。"""

    source: str = ""
    """来源标识（如 ``"summaries"``）。"""

    file_path: str = ""
    """来源文件路径。"""

    chunk_idx: int = 0
    """在文件内的分块索引。"""

    metadata: dict[str, object] = field(default_factory=dict)
    """扩展元信息。"""


def format_recall_item(idx: int, item: RecallItem) -> str:
    """格式化一条 RecallItem 为完整可读文本（无截断）。

    与 ``run.py`` 共享同一格式，确保 CLI / 日志输出一致。
    """
    lines: list[str] = []
    lines.append(f"  [{idx}] score={item.score:.4f}")
    lines.append(f"       source={item.source}  file={item.file_path}[{item.chunk_idx}]")
    non_text_keys = {"source", "file", "chunk_idx", "file_path"}
    extra = {k: v for k, v in item.metadata.items() if k not in non_text_keys}
    if extra:
        lines.append(f"       meta: {extra}")
    lines.append(f"       ---")
    for line in item.text.splitlines():
        lines.append(f"       {line}")
    return "\n".join(lines)


class MemoryManager:
    """记忆管理器 — 所有操作同步。"""

    # ── 工厂方法 ───────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        recalled_store: RecalledMemoryStore,
        session_dir: str,
        get_vector_db_path: str,
        mem_cfg: MemorySettings,
    ) -> MemoryManager | None:
        """构造 MemoryManager（同步：加载模型 + 建 DB）。"""
        if not mem_cfg.enabled:
            logger.info("[MemoryManager] disabled by config")
            return None

        embed_path = mem_cfg.embedding_model_path
        if not embed_path:
            logger.warning("[MemoryManager] embedding_model_path not configured — disabled")
            return None

        try:
            import llama_cpp  # noqa: F401
            import sqlite_vec  # noqa: F401
        except ImportError as exc:
            logger.warning("[MemoryManager] missing dependency ({})", exc)
            return None

        try:
            from rpg_world.rpg_core.memory.embedding_provider import LlamaCppEmbeddingProvider
            logger.info(
                "[MemoryManager] loading embedding model: {} (n_ctx={}, n_gpu_layers={})",
                embed_path, mem_cfg.n_ctx, mem_cfg.n_gpu_layers,
            )
            embedding = LlamaCppEmbeddingProvider(
                gguf_model_path=embed_path,
                n_ctx=mem_cfg.n_ctx,
                n_gpu_layers=mem_cfg.n_gpu_layers,
            )
            logger.info("[MemoryManager] model loaded — dim={}", embedding.dimension())

            from rpg_world.rpg_core.memory.vector_store import VectorStore
            store = VectorStore(db_path=get_vector_db_path, dimension=embedding.dimension())
            logger.info("[MemoryManager] vector store ready: {}", get_vector_db_path)

            from rpg_world.rpg_core.memory.chunker import Chunker
            chunker = Chunker(
                max_file_chars=mem_cfg.chunk_size,
                overlap=mem_cfg.chunk_overlap,
            )

            from rpg_world.rpg_core.memory.vector_index_manager import (
                VectorIndexManager, WatchSource,
            )
            from pathlib import Path
            sources = [
                WatchSource(
                    path=Path(session_dir) / "summaries",
                    source_id="summaries",
                    file_filter=lambda p: p.suffix in (".md", ".json"),
                ),
            ]
            logger.info("[MemoryManager] watch sources: {}", sources[0].path)

            index_mgr = VectorIndexManager(
                store=store, embedding=embedding, sources=sources, chunker=chunker,
            )

            from rpg_world.rpg_core.memory.retriever import DenseRetriever
            retriever = DenseRetriever(store=store, embedding=embedding)

            logger.info("[MemoryManager] components ready — top_k={}", mem_cfg.top_k)
            mm = cls(
                recalled_store=recalled_store,
                index_manager=index_mgr,
                retriever=retriever,
                top_k=mem_cfg.top_k,
            )
            mm._db_path = get_vector_db_path
            return mm

        except Exception as exc:
            logger.warning("[MemoryManager] init failed: {}", exc)
            return None

    # ── 实例初始化 ─────────────────────────────────────────────────────

    def __init__(
        self,
        recalled_store: RecalledMemoryStore,
        index_manager: VectorIndexManager | None = None,
        retriever: BaseRetriever | None = None,
        top_k: int = 5,
    ) -> None:
        self._recalled_store = recalled_store
        self._index_manager = index_manager
        self._retriever = retriever
        self._top_k = top_k
        self._inited = False
        self._db_path: str | None = None

    def init(self) -> None:
        """同步初始化：DB 无数据则全量索引，已有数据则跳过。"""
        logger.info("[MemoryManager] init() called — _inited={}", self._inited)
        if self._inited:
            return
        if self._index_manager is None:
            self._inited = True
            return

        # 跳过 DB 预检，直接全量索引（避免 vec_chunks 虚拟表查询可能导致的死锁）
        logger.info("[MemoryManager] DB empty — full reindex ...")
        self._index_manager.reindex_all()
        self._index_manager.start()
        self._inited = True
        logger.info("[MemoryManager] init done")

    def _get_db_path(self) -> Path | None:
        """返回 create() 时保存的 DB 路径，用于 init() 检查。"""
        if self._db_path:
            return Path(self._db_path)
        return None

    @property
    def recalled_items(self) -> list[str]:
        """当前缓存的召回结果文本列表（供上下文构建器读取）。"""
        return list(self._recalled_store.get_items())

    # ── 检索 ───────────────────────────────────────────────────────────

    def recall(self, query: str) -> list[RecallItem]:
        """检索与 *query* 相关的记忆（同步，无事件循环依赖）。

        返回结构化 ``RecallItem`` 列表（含文本、分数、来源信息）。
        同时将文本列表写入 ``RecalledMemoryStore``（供上下文构建器读取）。
        """
        if self._retriever is None:
            self._recalled_store.set_items([])
            return []

        raw = self._retriever.retrieve_sync(query, self._top_k)
        items: list[RecallItem] = []
        for text, score, meta in raw:
            items.append(RecallItem(
                text=text,
                score=score,
                source=str(meta.get("source", "")),
                file_path=str(meta.get("file", "")),
                chunk_idx=int(meta.get("chunk_idx", 0)),
                metadata=meta,
            ))

        self._recalled_store.set_items([i.text for i in items])
        logger.info(
            "[MemoryManager] recall({}) → {} items", query, len(items),
        )
        for i, it in enumerate(items):
            for line in format_recall_item(i, it).splitlines():
                logger.info("[MemoryManager] {}", line)
        return items
