"""Story Memory Context store backed by the application service."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from rpg_memory.story.application import (
    StoryMemoryApplicationService,
    StoryMemoryContextItem,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoryMemoryItem:
    """One evidence-valid Story Memory projected for online Context."""

    memory_id: int
    turn_id: int
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    source_turn_start: int
    source_turn_end: int


class StoryMemoryStore:
    """剧情记忆 —— 对应动态层中"剧情记忆"模块。"""

    def __init__(
        self,
        session_id: str,
        service: StoryMemoryApplicationService,
        close_worker_connection: Callable[[], None] | None = None,
    ) -> None:
        self._session_id = session_id
        self._application = service
        self._close_worker_connection = close_worker_connection
        self._last_snapshot: tuple[StoryMemoryItem, ...] = ()
        self._refresh_lock = asyncio.Lock()

    # ── public API ────────────────────────────────────────

    def reload(self) -> None:
        """Kept for store interface compatibility; rpg_data reads are live."""

    def get_all(self) -> list[dict[str, object]]:
        """返回所有剧情记忆条目。"""
        return [
            item.to_context_dict()
            for item in self._service().get_context_items(self._session_id)
        ]

    async def load_snapshot(self) -> tuple[StoryMemoryItem, ...]:
        """Load one immutable evidence-valid projection off the Agent loop."""

        async with self._refresh_lock:
            try:
                items = tuple(await asyncio.to_thread(self._load_items))
            except Exception:
                logger.warning(
                    "story memory projection refresh failed; using stale snapshot",
                    exc_info=True,
                )
                return self._last_snapshot
            self._last_snapshot = items
            return items

    def _load_items(self) -> list[StoryMemoryItem]:
        try:
            return [
                self._project_item(item)
                for item in self._service().get_context_items(self._session_id)
            ]
        finally:
            if self._close_worker_connection is not None:
                # Peewee connections are thread-local. Close only the worker's
                # handle; the shared gateway/database remains initialized.
                self._close_worker_connection()

    @staticmethod
    def _project_item(item: StoryMemoryContextItem) -> StoryMemoryItem:
        return StoryMemoryItem(
            memory_id=item.id,
            turn_id=item.turn_id,
            text=item.text,
            memory_kind=item.memory_kind.value,
            epistemic_status=item.epistemic_status.value,
            salience=item.salience,
            source_turn_start=item.source_turn_start,
            source_turn_end=item.source_turn_end,
        )

    def add_detail(
        self,
        text: str | dict[str, object],
        metadata: dict[str, object] | None = None,
        *,
        turn_id: int,
        dream_processed: bool = False,
    ) -> None:
        """追加一条剧情细节。"""
        detail = dict(text) if isinstance(text, dict) else {"text": text}
        detail_metadata = detail.pop("metadata", metadata or {})
        allowed = {
            "memory_kind",
            "epistemic_status",
            "salience",
            "source_turn_start",
            "source_turn_end",
            "dedupe_key",
            "metadata_schema_version",
            "evidence_message_ids",
        }
        core = {key: value for key, value in detail.items() if key in allowed}
        payload: dict[str, object] = {
            **core,
            "text": str(detail.pop("text", "") or ""),
            "turn_id": turn_id,
            "dream_processed": dream_processed,
            "metadata": detail_metadata or {},
        }
        self._service().add_candidate(self._session_id, payload)

    def add_details_and_mark_processed(
        self,
        details: Iterable[dict[str, object]],
        *,
        turn_id: int,
        source_turn_start: int,
        source_turn_end: int,
        message_ids: Iterable[int],
    ) -> int:
        payloads: list[dict[str, object]] = []
        for detail in details:
            payload = dict(detail)
            payload.setdefault("turn_id", turn_id)
            payload.setdefault("source_turn_start", source_turn_start)
            payload.setdefault("source_turn_end", source_turn_end)
            payloads.append(payload)
        rows = self._service().add_details_and_mark_processed(
            self._session_id,
            payloads,
            message_ids=message_ids,
        )
        return len(rows)

    def set_details(self, details: Iterable[dict[str, object]]) -> None:
        """批量设置剧情记忆（替换全部）。"""
        self._service().set_details(self._session_id, list(details))

    def clear(self) -> None:
        """清空全部剧情记忆（提炼到常驻记忆后调用）。"""
        self._service().clear(self._session_id)

    def _service(self) -> StoryMemoryApplicationService:
        return self._application
