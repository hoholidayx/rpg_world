"""StoryMemoryStore — persistent small story details for the Dynamic Layer.

Lifecycle:
  1. Agent records small story beats (e.g. "颜沁记住了沈听洲唱歌很好")
  2. These appear in the context between milestones and status tables
  3. During offline PM/summary distillation, they're refined into Persistent Memory
  4. Story memory is cleared to make room for new details
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StoryMemoryStore:
    """剧情记忆 —— 对应动态层中"剧情记忆"模块。

    文件位置: data/story_memory/{session_id}.json
    内容为剧情推进中产生的需要记住的小细节，
    总量可控，定期提炼到常驻记忆后清空。
    """

    def __init__(self, data_path: Path, session_id: str = "default") -> None:
        self._file = data_path / f"{session_id}.json"
        self._details: list[dict[str, Any]] = self._load()

    # ── public API ────────────────────────────────────────

    def get_all(self) -> list[dict[str, Any]]:
        """返回所有剧情记忆条目。"""
        return list(self._details)

    def add_detail(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        """追加一条剧情细节。"""
        self._details.append({
            "text": text,
            "metadata": metadata or {},
        })
        self._save()

    def set_details(self, details: list[dict[str, Any]]) -> None:
        """批量设置剧情记忆（替换全部）。"""
        self._details = list(details)
        self._save()

    def clear(self) -> None:
        """清空全部剧情记忆（提炼到常驻记忆后调用）。"""
        self._details.clear()
        self._save()

    # ── I/O ───────────────────────────────────────────────

    def _load(self) -> list[dict[str, Any]]:
        try:
            raw = self._file.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(self._details, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
