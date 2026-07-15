"""Loop-owned coordinator for watched memory sources and vector indexes."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rp_memory.chunker import Chunker, FileTextExtractor
from rp_memory.storage.types import ChunkRecord, IndexedFileState
from rp_memory.storage.vector_store import VectorStore

if TYPE_CHECKING:
    from llm_client.types import LLMProvider as EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass
class WatchSource:
    """A file or directory whose memory index must stay synchronized."""

    path: Path
    source_id: str
    file_filter: Callable[[Path], bool] | None = None


class VectorIndexManager:
    """Serialize one session's watcher, embedding, and SQLite index work."""

    def __init__(
        self,
        store: VectorStore,
        embedding: EmbeddingProvider | None,
        sources: list[WatchSource],
        chunker: Chunker | None = None,
        *,
        operation_lock: asyncio.Lock | None = None,
    ) -> None:
        self._store = store
        self._embedding = embedding
        self._sources = sources
        self._chunker = chunker or Chunker()
        self._operation_lock = operation_lock or asyncio.Lock()
        self._watch_callbacks: list[tuple[Path, Callable[[], None]]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[str | None] | None = None
        self._queued_sources: set[str] = set()
        self._worker: asyncio.Task[None] | None = None
        self._accepting = False
        self._closed = False

    @property
    def worker_task(self) -> asyncio.Task[None] | None:
        return self._worker

    def set_embedding(self, embedding: EmbeddingProvider | None) -> None:
        """Replace the remote embedding handle while holding the session lock."""
        self._embedding = embedding

    async def initialize(self) -> None:
        """Compensate offline changes, then attach watcher callbacks."""
        if self._closed:
            raise RuntimeError("vector index manager is closed")
        await self.sync_all(force=False)
        await self.start()

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("vector index manager is closed")
        if self._worker is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._accepting = True
        self._worker = asyncio.create_task(
            self._run_worker(),
            name="memory-index-coordinator",
        )
        logger.info(
            "[VectorIndex] start — registering watch sources count=%s",
            len(self._sources),
        )
        for source in self._sources:
            self._register(source)

    async def close(self) -> None:
        """Stop watcher delivery and drain the single index consumer."""
        if self._closed:
            return
        self._closed = True
        self._accepting = False
        self._unregister_all()
        worker = self._worker
        queue = self._queue
        if worker is not None and queue is not None:
            await queue.put(None)
            try:
                await worker
            finally:
                self._worker = None
                self._queue = None
                self._queued_sources.clear()

    async def reindex_all(self) -> None:
        await self.sync_all(force=True)

    async def sync_all(self, *, force: bool = False) -> None:
        async with self._operation_lock:
            logger.info(
                "[VectorIndex] sync_all start — sources=%s force=%s",
                len(self._sources),
                force,
            )
            for source in self._sources:
                await self._sync_source_locked(source, force=force)
            logger.info("[VectorIndex] sync_all done")

    async def sync_source(self, source_id: str, *, force: bool = False) -> None:
        source = self._source(source_id)
        if source is None:
            logger.warning("[VectorIndex] source not found: %s", source_id)
            return
        async with self._operation_lock:
            await self._sync_source_locked(source, force=force)

    def on_source_change(self, source_id: str) -> None:
        """Thread-safe watcher callback; never performs indexing itself."""
        loop = self._loop
        if not self._accepting or loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._enqueue_source, source_id)
        except RuntimeError:
            logger.debug("[VectorIndex] event loop closed; dropped source=%s", source_id)

    def _enqueue_source(self, source_id: str) -> None:
        if not self._accepting or self._queue is None:
            return
        if source_id in self._queued_sources:
            return
        self._queued_sources.add(source_id)
        self._queue.put_nowait(source_id)

    async def _run_worker(self) -> None:
        assert self._queue is not None
        while True:
            source_id = await self._queue.get()
            if source_id is None:
                return
            self._queued_sources.discard(source_id)
            try:
                await self.sync_source(source_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "[VectorIndex] watcher sync failed source=%s",
                    source_id,
                )

    def _register(self, source: WatchSource) -> None:
        from rpg_core.utils.watcher import get_watcher

        target = source.path if source.path.is_dir() else source.path.parent
        if not target.exists():
            logger.warning("[VectorIndex] path does not exist, skipping: %s", target)
            return

        def callback() -> None:
            self.on_source_change(source.source_id)

        resolved_target = target.resolve()
        get_watcher().register(resolved_target, callback)
        self._watch_callbacks.append((resolved_target, callback))
        logger.info(
            "[VectorIndex] registered source=%s path=%s",
            source.source_id,
            target,
        )

    def _unregister_all(self) -> None:
        from rpg_core.utils.watcher import get_watcher

        watcher = get_watcher()
        for target, callback in self._watch_callbacks:
            watcher.unregister(target, callback)
        self._watch_callbacks.clear()

    def _source(self, source_id: str) -> WatchSource | None:
        return next(
            (source for source in self._sources if source.source_id == source_id),
            None,
        )

    async def _sync_source_locked(
        self,
        source: WatchSource,
        *,
        force: bool,
    ) -> None:
        files = await asyncio.to_thread(self._iter_files, source)
        current_files = {str(path): path for path in files}
        indexed = await asyncio.to_thread(
            self._store.list_indexed_files,
            source.source_id,
        )

        deleted = sorted(set(indexed) - set(current_files))
        for file_path in deleted:
            try:
                await asyncio.to_thread(self._store.delete_file_index, file_path)
            except Exception:
                logger.exception(
                    "[VectorIndex] failed to delete stale file index=%s",
                    file_path,
                )

        indexed_count = skipped_count = error_count = 0
        logger.info(
            "[VectorIndex] sync source=%s path=%s files=%s deleted=%s force=%s",
            source.source_id,
            source.path,
            len(files),
            len(deleted),
            force,
        )
        for file_path in files:
            try:
                stat = await asyncio.to_thread(file_path.stat)
                file_key = str(file_path.resolve())
            except OSError as exc:
                error_count += 1
                logger.warning("[VectorIndex] %s — stat error: %s", file_path.name, exc)
                continue

            previous = indexed.get(file_key)
            if not force and previous is not None and self._same_stat(previous, stat):
                skipped_count += 1
                continue
            try:
                state = await asyncio.to_thread(
                    self._file_state,
                    file_path,
                    source.source_id,
                    stat,
                    file_key,
                )
            except OSError as exc:
                error_count += 1
                logger.warning("[VectorIndex] %s — hash error: %s", file_path.name, exc)
                continue
            if not force and previous is not None and self._is_unchanged(previous, state):
                skipped_count += 1
                continue
            if await self._index_file(file_path, state):
                indexed_count += 1
            else:
                error_count += 1

        logger.info(
            "[VectorIndex] sync done source=%s indexed=%s skipped=%s deleted=%s errors=%s",
            source.source_id,
            indexed_count,
            skipped_count,
            len(deleted),
            error_count,
        )

    async def _index_file(
        self,
        file_path: Path,
        file_state: IndexedFileState,
    ) -> bool:
        try:
            records = await asyncio.to_thread(
                self._extract_records,
                file_path,
                file_state,
            )
        except Exception as exc:
            await self._mark_error(file_state, f"read/chunk error: {exc}")
            logger.warning("[VectorIndex] %s — read/chunk error: %s", file_path.name, exc)
            return False

        embeddings: list[list[float]] | None = None
        if records and self._embedding is not None:
            try:
                embeddings = await self._embedding.embed(
                    [record.text for record in records]
                )
            except Exception as exc:
                await self._mark_error(file_state, f"embed error: {exc}")
                logger.warning("[VectorIndex] %s — embed error: %s", file_path.name, exc)
                return False

        file_state.status = "indexed" if records else "empty"
        file_state.chunk_count = len(records)
        file_state.last_error = ""
        try:
            await asyncio.to_thread(
                self._store.replace_file,
                file_state.file,
                records,
                embeddings,
                file_state,
            )
        except Exception as exc:
            await self._mark_error(file_state, f"upsert error: {exc}")
            logger.warning("[VectorIndex] %s — upsert error: %s", file_path.name, exc)
            return False
        logger.info(
            "[VectorIndex] indexed file=%s chunks=%s source=%s mode=%s",
            file_path.name,
            len(records),
            file_state.source_id,
            "vector" if self._embedding is not None else "text-index-only",
        )
        return True

    def _extract_records(
        self,
        file_path: Path,
        file_state: IndexedFileState,
    ) -> list[ChunkRecord]:
        text, front_matter = FileTextExtractor.extract(file_path)
        if not text.strip():
            return []
        chunks = self._chunker.chunk_file(
            text=text,
            file_path=file_state.file,
            front_matter=front_matter,
        )
        records: list[ChunkRecord] = []
        for chunk in chunks:
            chunk_idx = int(chunk.metadata.get("chunk_idx", 0))
            metadata = dict(chunk.metadata)
            metadata.update(
                {
                    "source": file_state.source_id,
                    "file": file_state.file,
                    "chunk_idx": chunk_idx,
                }
            )
            uid = hashlib.sha256(
                f"{file_state.file}:{chunk_idx}".encode()
            ).hexdigest()[:16]
            records.append(
                ChunkRecord(
                    id=int(uid, 16) % (2**63),
                    text=chunk.text,
                    metadata=metadata,
                )
            )
        return records

    def _iter_files(self, source: WatchSource) -> list[Path]:
        if not source.path.exists():
            return []
        if source.path.is_file():
            path = source.path.resolve()
            return [path] if source.file_filter is None or source.file_filter(path) else []
        return [
            path.resolve()
            for path in sorted(source.path.rglob("*"))
            if path.is_file()
            and (source.file_filter is None or source.file_filter(path))
        ]

    @staticmethod
    def _file_state(
        file_path: Path,
        source_id: str,
        stat: object,
        file_key: str,
    ) -> IndexedFileState:
        return IndexedFileState(
            file=file_key,
            source_id=source_id,
            mtime_ns=int(stat.st_mtime_ns),
            size=int(stat.st_size),
            content_hash=hashlib.sha256(file_path.read_bytes()).hexdigest(),
        )

    async def _mark_error(self, file_state: IndexedFileState, error: str) -> None:
        try:
            await asyncio.to_thread(self._store.mark_file_error, file_state, error)
        except Exception:
            logger.exception(
                "[VectorIndex] failed to record file error file=%s",
                file_state.file,
            )

    @staticmethod
    def _same_stat(previous: IndexedFileState, current_stat: object) -> bool:
        return previous.status in {"indexed", "empty"} and (
            previous.mtime_ns == int(current_stat.st_mtime_ns)
            and previous.size == int(current_stat.st_size)
        )

    @staticmethod
    def _is_unchanged(
        previous: IndexedFileState,
        current: IndexedFileState,
    ) -> bool:
        return previous.status in {"indexed", "empty"} and (
            previous.mtime_ns == current.mtime_ns
            and previous.size == current.size
            and previous.content_hash == current.content_hash
        )
