"""StoryMemoryStore — rpg_data-backed story details for the Dynamic Layer."""

from __future__ import annotations

import json
from collections.abc import Iterable


class StoryMemoryStore:
    """剧情记忆 —— 对应动态层中"剧情记忆"模块。"""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id

    # ── public API ────────────────────────────────────────

    def reload(self) -> None:
        """Kept for store interface compatibility; rpg_data reads are live."""

    def get_all(self) -> list[dict[str, object]]:
        """返回所有剧情记忆条目。"""
        return [
            row.to_context_dict()
            for row in self._service().list(self._session_id)
        ]

    def add_detail(
        self,
        text: str,
        metadata: dict[str, object] | None = None,
        *,
        turn_id: int,
        dream_processed: bool = False,
    ) -> None:
        """追加一条剧情细节。"""
        self._service().add_detail(
            self._session_id,
            text,
            turn_id=turn_id,
            dream_processed=dream_processed,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )

    def set_details(self, details: Iterable[dict[str, object]]) -> None:
        """批量设置剧情记忆（替换全部）。"""
        self._service().set_details(self._session_id, list(details))

    def clear(self) -> None:
        """清空全部剧情记忆（提炼到常驻记忆后调用）。"""
        self._service().clear(self._session_id)

    def _service(self):
        from rpg_data.services import get_data_service_gateway

        return get_data_service_gateway().story_memory
