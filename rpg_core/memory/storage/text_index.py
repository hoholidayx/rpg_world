"""FTS and substring text index for memory chunks."""

from __future__ import annotations

import json as _json

from rpg_world.rpg_core.memory.bigram_tokenizer import tokenize_bigram
from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.storage.repository import MemoryRepository


class TextIndex:
    """SQLite FTS5 + substring fallback index."""

    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository
        self._repository.conn.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(grams);
            """
        )

    def upsert(self, memory_id: int, content: str) -> None:
        self._upsert(memory_id, content)

    def delete_rows(self, rowids: list[int]) -> None:
        if not rowids:
            return
        placeholders = ",".join("?" for _ in rowids)
        self._repository.conn.execute(
            f"DELETE FROM memory_fts WHERE rowid IN ({placeholders})",
            tuple(rowids),
        )

    def bigram_search(self, query: str, limit: int = 50) -> list[MemoryCandidate]:
        grams = _fts_query(tokenize_bigram(query))
        if not grams:
            return []

        rows = self._repository.conn.execute(
            """
            SELECT c.id, c.text, c.metadata, c.created_at, bm25(memory_fts) AS rank
            FROM memory_fts
            JOIN chunks c ON c.id = memory_fts.rowid
            WHERE memory_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (grams, limit),
        ).fetchall()

        result: list[MemoryCandidate] = []
        for row in rows:
            try:
                meta = _json.loads(row[2]) if isinstance(row[2], str) else {}
            except (ValueError, TypeError):
                meta = {}
            meta["created_at"] = row[3]
            bm25_score = float(row[4])
            result.append(
                MemoryCandidate(
                    memory_id=int(row[0]),
                    content=str(row[1]),
                    metadata=meta,
                    bigram_score=1.0 / (1.0 + max(bm25_score, 0.0)),
                    debug={"bigram_bm25": bm25_score},
                )
            )
        return result

    def substring_search(self, query: str, limit: int = 50) -> list[MemoryCandidate]:
        normalized = " ".join((query or "").split())
        if not normalized:
            return []

        terms = [term for term in normalized.split(" ") if term]
        clauses: list[str] = []
        params: list[object] = []
        if len(terms) <= 1:
            clauses.append("c.text LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(normalized)}%")
        else:
            for term in terms:
                clauses.append("c.text LIKE ? ESCAPE '\\'")
                params.append(f"%{_escape_like(term)}%")

        rows = self._repository.conn.execute(
            f"""
            SELECT c.id, c.text, c.metadata, c.created_at
            FROM chunks c
            WHERE {' AND '.join(clauses)}
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()

        result: list[MemoryCandidate] = []
        for row in rows:
            try:
                meta = _json.loads(row[2]) if isinstance(row[2], str) else {}
            except (ValueError, TypeError):
                meta = {}
            meta["created_at"] = row[3]
            normalized_text = str(row[1])
            match_score = _substring_match_score(normalized, normalized_text)
            result.append(
                MemoryCandidate(
                    memory_id=int(row[0]),
                    content=normalized_text,
                    metadata=meta,
                    bigram_score=match_score,
                    debug={"substring_query": normalized},
                )
            )
        return result

    def rebuild(self) -> None:
        self._repository.conn.execute("DELETE FROM memory_fts")
        for memory_id, text in self._repository.iter_chunks():
            self._upsert(memory_id, text)
        self._repository.conn.commit()

    def clear(self) -> None:
        self._repository.conn.execute("DELETE FROM memory_fts")

    def _upsert(self, memory_id: int, content: str) -> None:
        grams = " ".join(tokenize_bigram(content))
        self._repository.conn.execute("DELETE FROM memory_fts WHERE rowid = ?", (memory_id,))
        if grams:
            self._repository.conn.execute(
                "INSERT INTO memory_fts(rowid, grams) VALUES (?, ?)",
                (memory_id, grams),
            )


def _fts_query(tokens: list[str]) -> str:
    quoted: list[str] = []
    for token in tokens:
        escaped = token.replace('"', '""')
        quoted.append(f'"{escaped}"')
    return " OR ".join(quoted)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _substring_match_score(query: str, text: str) -> float:
    if not query or not text:
        return 0.0
    normalized_query = " ".join(query.split())
    if normalized_query and normalized_query in text:
        return 1.0
    terms = [term for term in normalized_query.split(" ") if term]
    if not terms:
        return 0.0
    matches = sum(1 for term in terms if term in text)
    return matches / len(terms)
