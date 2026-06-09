"""BatchSummaryStore — 管理 sessions/{session_id}/summaries/ 目录下的 markdown 摘要文件。

批次文件是记忆唯一真源，overall.md 是聚合概览（唯一注入 context 的摘要）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from loguru import logger


def _register_watcher(file_path: Path, callback: Callable[[], None]) -> None:
    """向 FileWatcher 注册单个文件的变更回调。"""
    from rpg_world.rpg_core.utils.watcher import get_watcher

    get_watcher().register(file_path.resolve(), callback)


_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


class BatchSummaryStore:
    """管理 sessions/{session_id}/summaries/ 目录下的 markdown 摘要文件。"""

    def __init__(self, session_id: str) -> None:
        from rpg_world.rpg_core.settings import settings

        self._dir = settings.session_dir(session_id) / "summaries"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index: list[dict] = []
        self._load_index()
        self._register_watcher()

    # ── 批次摘要 ───────────────────────────────────────────────────

    def save_batch_summary(
        self,
        batch_id: int,
        title: str,
        user_rounds: int,
        summary_text: str = "",
        time: str = "",
        location: str = "",
        characters: list[str] | None = None,
    ) -> Path:
        """写入批次摘要 md 文件。返回文件路径。"""
        slug = self._slugify_title(title)
        file_name = f"{batch_id:03d}-{slug}.md"
        file_path = self._dir / file_name

        from rpg_world.rpg_core.context.builder import render_jinja_template

        body = render_jinja_template(
            "summary/batch_summary.md.jinja",
            batch_id=batch_id,
            title=title,
            time=time,
            location=location,
            characters=characters or [],
            summary_text=summary_text,
        )

        file_path.write_text(body, encoding="utf-8")
        logger.debug("[BatchSummaryStore] saved batch #{}: {}", batch_id, file_name)
        self._load_index()
        return file_path

    def list_summaries(self) -> list[dict]:
        """返回按 batch_id 排序的批次元数据列表。"""
        return sorted(self._index, key=lambda d: d.get("batch_id", 0))

    def get_batch_content(self, batch_id: int) -> str | None:
        """返回指定批次的 markdown 正文（剥离 front matter）。"""
        for entry in self._index:
            if entry.get("batch_id") == batch_id:
                return entry.get("body", "")
        return None

    # ── 整体归纳 ───────────────────────────────────────────────────

    def get_overall_path(self) -> Path:
        """返回 overall.md 的固定路径。"""
        return self._dir / "overall.md"

    def load_overall(self) -> tuple[str, int]:
        """加载已有 overall.md 的正文和 last_batch_id。
        返回 (body, last_batch_id)，文件不存在时返回 ("", -1)。"""
        path = self.get_overall_path()
        if not path.exists():
            return "", -1
        try:
            text = path.read_text(encoding="utf-8")
            _, body = self._parse_front_matter(text)
            fm = self._parse_front_matter_dict(text)
            last_id = int(fm.get("last_batch_id", -1))
            return body.strip(), last_id
        except Exception as exc:
            logger.warning("[BatchSummaryStore] failed to load overall.md: {}", exc)
            return "", -1

    def save_overall(
        self,
        content: str,
        title: str = "",
        key_events: list[str] | None = None,
        last_batch_id: int = 0,
    ) -> Path:
        """覆盖写入 overall.md（含 front matter）。返回文件路径。"""
        from rpg_world.rpg_core.context.builder import render_jinja_template

        body = render_jinja_template(
            "summary/overall.md.jinja",
            type="overall",
            last_batch_id=last_batch_id,
            title=title,
            summary_text=content,
            key_events=key_events or [],
        )

        path = self.get_overall_path()
        path.write_text(body, encoding="utf-8")
        logger.debug(
            "[BatchSummaryStore] saved overall.md (last_batch_id={})", last_batch_id
        )
        return path

    # ── 通用 ──────────────────────────────────────────────────────

    def get_all_content(self) -> list[str]:
        """返回所有批次摘要正文的有序列表。"""
        return [e.get("body", "") for e in sorted(self._index, key=lambda d: d.get("batch_id", 0))]

    def get_new_content(self, after_batch_id: int = -1) -> list[str]:
        """返回 last_batch_id 之后的批次摘要正文列表。
        用于整体归纳时只传入新增批次。"""
        return [
            e.get("body", "")
            for e in sorted(self._index, key=lambda d: d.get("batch_id", 0))
            if e.get("batch_id", 0) > after_batch_id
        ]

    def reload(self) -> None:
        """从磁盘重建索引（FileWatcher 回调）。"""
        self._load_index()

    # ── 内部方法 ──────────────────────────────────────────────────

    def _slugify_title(self, title: str) -> str:
        """将标题转为文件系统安全的 slug。保留中文字符。"""
        slug = re.sub(r"[^\w\u4e00-\u9fff\-]", "-", title.strip())
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        return slug[:40] if len(slug) > 40 else slug

    def _next_batch_id(self) -> int:
        """返回下一个可用 batch_id（最大已有值 + 1，或 0）。"""
        if not self._index:
            return 0
        return max(e.get("batch_id", 0) for e in self._index) + 1

    def _parse_front_matter(self, text: str) -> tuple[dict, str]:
        """拆分 YAML front matter 和 markdown 正文。返回 (fm_dict, body)。"""
        m = _FRONT_MATTER_RE.match(text)
        if not m:
            return {}, text
        fm_text = m.group(1)
        body = text[m.end() :]
        fm_dict: dict[str, object] = {}
        for line in fm_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                fm_dict[key.strip()] = val.strip().strip('"').strip("'")
        return fm_dict, body

    def _parse_front_matter_dict(self, text: str) -> dict[str, object]:
        """仅解析 front matter 为 dict。"""
        fm, _ = self._parse_front_matter(text)
        return fm

    def _register_watcher(self) -> None:
        """向 FileWatcher 注册 summaries 目录。"""
        try:
            from rpg_world.rpg_core.utils.watcher import get_watcher

            get_watcher().register(self._dir.resolve(), self.reload)
        except Exception as exc:
            logger.debug("[BatchSummaryStore] watcher registration skipped: {}", exc)

    def _load_index(self) -> None:
        """扫描 summaries/ 目录，重建批次索引。"""
        self._index = []
        if not self._dir.is_dir():
            return
        for path in sorted(self._dir.iterdir()):
            if path.suffix != ".md" or path.name == "overall.md":
                continue
            try:
                text = path.read_text(encoding="utf-8")
                fm, body = self._parse_front_matter(text)
                batch_id = int(fm.get("batch_id", -1))
                if batch_id < 0:
                    continue
                self._index.append(
                    {
                        "batch_id": batch_id,
                        "title": fm.get("title", ""),
                        "time": fm.get("time", ""),
                        "location": fm.get("location", ""),
                        "body": body.strip(),
                        "file_path": path,
                    }
                )
            except Exception as exc:
                logger.debug("[BatchSummaryStore] failed to index {}: {}", path.name, exc)
