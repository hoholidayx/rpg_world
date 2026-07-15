"""Shared fixtures and fakes for rp_memory tests."""

from __future__ import annotations

import pytest

from rp_memory.candidate import MemoryCandidate
from rpg_core.context.rpg_context import Message
from llm_client.manager import LLMClientManager


class FakeTokenCounter:
    """Deterministic token counter for tests."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4) if text else 0

    def count_messages(self, messages: list[Message]) -> int:
        return sum(self.count(m.content) for m in messages)


class FakeEmbedding:
    def __init__(self, vectors: list[list[float]] | None = None) -> None:
        self.vectors = vectors or [[0.1, 0.2, 0.3]]
        self.calls: list[list[str]] = []

    async def embed(self, queries: list[str]) -> list[list[float]]:
        self.calls.append(list(queries))
        return self.vectors

    async def dimension(self) -> int:
        return len(self.vectors[0]) if self.vectors else 0


class FakeStore:
    def __init__(self) -> None:
        self.vector_rows: list[tuple[MemoryCandidate, float]] = []
        self.keyword_rows: dict[str, list[MemoryCandidate]] = {}
        self.search_calls: list[tuple[list[float], int]] = []
        self.keyword_calls: list[tuple[str, int]] = []

    def search(self, query: list[float], top_k: int = 5, filters=None):  # noqa: ANN001
        self.search_calls.append((list(query), top_k))
        return self.vector_rows[:top_k]

    def keyword_search(self, query: str, limit: int = 50):
        self.keyword_calls.append((query, limit))
        return self.keyword_rows.get(query, [])[:limit]


class FakeFallbackSearch:
    def __init__(self, results: list[MemoryCandidate] | None = None) -> None:
        self.results = results or []
        self.calls: list[str] = []

    def search(self, query: str, limit: int = 50):
        self.calls.append(query)
        return self.results[:limit]

    def search_plan(self, plan, limit: int = 50):  # noqa: ANN001
        self.calls.append(plan.normalized_query)
        return self.results[:limit]


class FakeRetriever:
    def __init__(self, raw: list[tuple[str, float, dict[str, object]]] | None = None) -> None:
        self.raw = raw or []
        self.sync_calls: list[tuple[str, int]] = []
        self.plan_calls: list[tuple[str, int]] = []
        self.hybrid_calls: list[tuple[str, int]] = []

    async def retrieve(self, query: str, top_k: int = 5):
        self.sync_calls.append((query, top_k))
        return self.raw[:top_k]

    async def retrieve_plan(self, plan, top_k: int = 5):  # noqa: ANN001
        self.plan_calls.append((plan.normalized_query, top_k))
        return self.raw[:top_k]

    async def hybrid_search(self, plan, top_k: int = 20):  # noqa: ANN001
        self.hybrid_calls.append((plan.normalized_query, top_k))
        return [
            MemoryCandidate(memory_id=i + 1, content=text, metadata=meta, hybrid_score=score)
            for i, (text, score, meta) in enumerate(self.raw[:top_k])
        ]


@pytest.fixture(autouse=True)
async def reset_llm_manager():
    await LLMClientManager.areset()
    yield
    await LLMClientManager.areset()


@pytest.fixture
def fake_token_counter() -> FakeTokenCounter:
    return FakeTokenCounter()


@pytest.fixture
def fake_recalled_store():
    class _Store:
        def __init__(self) -> None:
            self.items: list[str] = []

        def get_items(self):
            return list(self.items)

        def set_items(self, items):
            self.items = list(items)

        def clear(self):
            self.items.clear()

    return _Store()
