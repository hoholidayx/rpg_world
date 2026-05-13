"""SummaryStore — persist conversation round-chunk summaries as JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SummaryStore:
    """摘要持久化存储。

    文件位置: data/summary/rpg_summaries.json
    数据格式:
    {
      "summaries": [
        {"round_start": 0, "round_end": 100, "text": "..."},
        {"round_start": 100, "round_end": 200, "text": "..."}
      ]
    }
    """

    def __init__(self, data_path: Path) -> None:
        self._file = data_path / "rpg_summaries.json"
        self._summaries: list[dict[str, Any]] = self._load()

    # ── public API ────────────────────────────────────────

    def get_all_summaries(self) -> list[dict[str, Any]]:
        """返回所有摘要列表，按 round_start 升序排列。

        构建摘要层时调用此方法批量获取全部已归档摘要，
        由 Builder 按窗口阈值筛选需要的范围。
        """
        return sorted(self._summaries, key=lambda s: s.get("round_start", 0))

    def get_summary(self, round_start: int, round_end: int) -> str | None:
        """按精确轮次区间获取单条摘要。"""
        for s in self._summaries:
            if s.get("round_start") == round_start and s.get("round_end") == round_end:
                return s.get("text")
        return None

    def set_summary(self, round_start: int, round_end: int, text: str) -> None:
        """写入一条摘要。若区间已存在则覆盖。"""
        # Remove existing entry for the same range
        self._summaries = [
            s for s in self._summaries
            if not (s.get("round_start") == round_start and s.get("round_end") == round_end)
        ]
        self._summaries.append({"round_start": round_start, "round_end": round_end, "text": text})
        self._save()

    # ── I/O ───────────────────────────────────────────────

    def _load(self) -> list[dict[str, Any]]:
        try:
            raw = self._file.read_text(encoding="utf-8")
            data: dict = json.loads(raw)
            return data.get("summaries", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps({"summaries": self._summaries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
