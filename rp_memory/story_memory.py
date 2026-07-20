"""StoryMemoryStore — rpg_data-backed story details for the Dynamic Layer."""

from __future__ import annotations

from collections.abc import Iterable

from rp_memory.story_memory_service import StoryMemoryApplicationService


class StoryMemoryStore:
    """剧情记忆 —— 对应动态层中"剧情记忆"模块。"""

    def __init__(
        self,
        session_id: str,
        service: StoryMemoryApplicationService,
    ) -> None:
        self._session_id = session_id
        self._application = service

    # ── public API ────────────────────────────────────────

    def reload(self) -> None:
        """Kept for store interface compatibility; rpg_data reads are live."""

    def get_all(self) -> list[dict[str, object]]:
        """返回所有剧情记忆条目。"""
        return [
            item.to_context_dict()
            for item in self._service().get_context_items(self._session_id)
        ]

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
