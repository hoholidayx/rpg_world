"""Raw markdown grep fallback for memory retrieval.

This is the final retrieval stage when vector and bigram keyword search
produce no useful candidates or fail independently.
It scans the raw markdown files under the watched memory source paths
instead of depending on the SQLite database.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from rpg_world.rpg_core.memory.candidate import MemoryCandidate


@dataclass
class RawMarkdownGrepSearch:
    """Final fallback searcher based on raw markdown file scanning."""

    source_paths: list[Path]
    limit: int = 50

    def search(self, query: str, limit: int | None = None) -> list[MemoryCandidate]:
        """Return candidates matched by scanning raw markdown files.

        The search is intentionally tolerant: all failures are swallowed and
        converted to an empty result so that this stage never breaks the
        hybrid pipeline.
        """
        try:
            logger.info(
                "[RawMarkdownGrepSearch] search start — query={!r} roots={} limit={}",
                query,
                len(self.source_paths),
                limit or self.limit,
            )
            return self._search(query, limit=limit or self.limit)
        except Exception as exc:
            logger.warning("[RawMarkdownGrepSearch] fallback search failed: {}", exc)
            return []

    def _search(self, query: str, limit: int) -> list[MemoryCandidate]:
        normalized = " ".join((query or "").split())
        if not normalized:
            return []

        terms = [term for term in normalized.split(" ") if term]
        candidates: list[MemoryCandidate] = []
        for file_path in self._iter_md_files():
            try:
                raw_text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            match_score = _score_text(normalized, raw_text)
            if match_score <= 0.0:
                continue

            metadata = {
                "source": file_path.parent.name or file_path.stem,
                "file": str(file_path),
                "chunk_idx": 0,
                "created_at": float(file_path.stat().st_mtime),
                "grep_terms": terms,
            }
            candidates.append(
                MemoryCandidate(
                    memory_id=_stable_memory_id(file_path),
                    content=raw_text,
                    metadata=metadata,
                    keyword_score=match_score,
                    exact_score=1.0 if normalized in raw_text else 0.0,
                    fuzzy_score=match_score,
                    hybrid_score=match_score,
                    debug={"grep_source": str(file_path)},
                )
            )

        candidates.sort(
            key=lambda item: (
                item.exact_score,
                item.keyword_score,
                float(item.metadata.get("created_at") or 0.0),
            ),
            reverse=True,
        )
        logger.info("[RawMarkdownGrepSearch] search done — matched={}", len(candidates))
        return candidates[:limit]

    def _iter_md_files(self) -> list[Path]:
        files: list[Path] = []
        seen: set[Path] = set()
        for root in self.source_paths:
            if not root.exists():
                continue
            if root.is_file():
                if root.suffix.lower() == ".md":
                    resolved = root.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        files.append(resolved)
                continue
            for file_path in sorted(root.rglob("*.md")):
                if not file_path.is_file():
                    continue
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(resolved)
        return files


def _stable_memory_id(file_path: Path) -> int:
    uid = hashlib.sha256(f"{file_path}:0".encode()).hexdigest()[:16]
    return int(uid, 16) % (2**63)


def _score_text(query: str, text: str) -> float:
    if not query or not text:
        return 0.0
    if query in text:
        return 1.0

    compact_text = _compact(text)
    compact_query = _compact(query)
    if compact_query and compact_query in compact_text:
        return 1.0

    terms = [term for term in query.split(" ") if term]
    if not terms:
        return 0.0
    matched = sum(1 for term in terms if term in text or term in compact_text)
    return matched / len(terms)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
