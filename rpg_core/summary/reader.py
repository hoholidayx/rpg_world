"""Read-only access to rendered session summary markdown files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from loguru import logger

from rpg_core.summary.front_matter import parse_markdown_front_matter


SummaryKind = Literal["overall", "batch"]
_LEADING_H1_RE = re.compile(r"^\s*#(?!#)\s+([^\r\n]+?)\s*(?:\r?\n+|$)")
_EXCERPT_LIMIT = 240


@dataclass(frozen=True)
class SummaryDocument:
    kind: SummaryKind
    title: str
    excerpt: str
    markdown: str
    updated_at: str | None
    batch_id: int | None = None
    last_batch_id: int | None = None
    time: str = ""
    location: str = ""
    characters: tuple[str, ...] = ()
    source_turn_start: int | None = None
    source_turn_end: int | None = None
    source_message_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class SummaryIndex:
    overall: SummaryDocument | None
    batches: tuple[SummaryDocument, ...]


class SummaryReader:
    """Scan ``{session_root}/summaries`` without mutating the filesystem."""

    def __init__(self, session_root: str | Path) -> None:
        self._directory = Path(session_root) / "summaries"

    def read_index(self) -> SummaryIndex:
        if not self._directory.is_dir():
            return SummaryIndex(overall=None, batches=())

        overall = self._read_overall(self._directory / "overall.md")
        by_batch_id: dict[int, tuple[int, SummaryDocument, Path]] = {}
        for path in sorted(self._directory.glob("*.md")):
            if path.name == "overall.md" or not path.is_file():
                continue
            document = self._read_batch(path)
            if document is None or document.batch_id is None:
                continue
            try:
                modified_ns = path.stat().st_mtime_ns
            except OSError as exc:
                logger.warning("[SummaryReader] failed to stat {}: {}", path, exc)
                continue

            existing = by_batch_id.get(document.batch_id)
            if existing is not None:
                keep_new = (modified_ns, path.name) > (existing[0], existing[2].name)
                kept_path = path if keep_new else existing[2]
                logger.warning(
                    "[SummaryReader] duplicate batch_id={} in {} and {}; keeping {}",
                    document.batch_id,
                    existing[2].name,
                    path.name,
                    kept_path.name,
                )
                if not keep_new:
                    continue
            by_batch_id[document.batch_id] = (modified_ns, document, path)

        batches = tuple(
            item[1]
            for _, item in sorted(by_batch_id.items(), key=lambda pair: pair[0])
        )
        return SummaryIndex(overall=overall, batches=batches)

    def get(self, summary_key: str | int) -> SummaryDocument | None:
        index = self.read_index()
        if summary_key == "overall":
            return index.overall
        try:
            batch_id = int(summary_key)
        except (TypeError, ValueError):
            return None
        return next(
            (batch for batch in index.batches if batch.batch_id == batch_id),
            None,
        )

    def _read_overall(self, path: Path) -> SummaryDocument | None:
        if not path.is_file():
            return None
        try:
            front_matter, body = parse_markdown_front_matter(
                path.read_text(encoding="utf-8")
            )
            markdown = body.strip()
            title = "故事归纳"
            heading = _LEADING_H1_RE.match(markdown)
            if heading is not None:
                title = _normalized_text(heading.group(1)) or title
                markdown = markdown[heading.end() :].lstrip()
            return SummaryDocument(
                kind="overall",
                title=title,
                excerpt=_excerpt(markdown),
                markdown=markdown,
                last_batch_id=_optional_non_negative_int(
                    front_matter.get("last_batch_id")
                ),
                updated_at=_updated_at(path),
            )
        except Exception as exc:
            logger.warning("[SummaryReader] skipped malformed {}: {}", path.name, exc)
            return None

    def _read_batch(self, path: Path) -> SummaryDocument | None:
        try:
            front_matter, body = parse_markdown_front_matter(
                path.read_text(encoding="utf-8")
            )
            batch_id = _required_non_negative_int(front_matter.get("batch_id"))
            markdown = body.strip()
            title = _normalized_text(front_matter.get("title")) or f"Batch {batch_id:03d}"
            return SummaryDocument(
                kind="batch",
                batch_id=batch_id,
                title=title,
                excerpt=_excerpt(markdown),
                markdown=markdown,
                time=_normalized_text(front_matter.get("time")),
                location=_normalized_text(front_matter.get("location")),
                characters=_characters(front_matter.get("characters")),
                source_turn_start=_optional_positive_int(
                    front_matter.get("source_turn_start")
                ),
                source_turn_end=_optional_positive_int(
                    front_matter.get("source_turn_end")
                ),
                source_message_ids=_positive_ints(
                    front_matter.get("source_message_ids")
                ),
                updated_at=_updated_at(path),
            )
        except Exception as exc:
            logger.warning("[SummaryReader] skipped malformed {}: {}", path.name, exc)
            return None


def _required_non_negative_int(value: object) -> int:
    parsed = _optional_non_negative_int(value)
    if parsed is None:
        raise ValueError("batch_id must be a non-negative integer")
    return parsed


def _optional_non_negative_int(value: object) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _optional_positive_int(value: object) -> int | None:
    parsed = _optional_non_negative_int(value)
    return parsed if parsed is not None and parsed > 0 else None


def _positive_ints(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    result: list[int] = []
    for item in value:
        parsed = _optional_positive_int(item)
        if parsed is not None and parsed not in result:
            result.append(parsed)
    return tuple(result)


def _normalized_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _characters(value: object) -> tuple[str, ...]:
    values = value if isinstance(value, list) else [value]
    return tuple(text for item in values if (text := _normalized_text(item)))


def _excerpt(markdown: str) -> str:
    text = _normalized_text(markdown)
    if len(text) <= _EXCERPT_LIMIT:
        return text
    return f"{text[: _EXCERPT_LIMIT - 1].rstrip()}…"


def _updated_at(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return None
