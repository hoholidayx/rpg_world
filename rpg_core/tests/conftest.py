"""Shared fixtures and fakes for rpg_core tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from rpg_world.rpg_core.context.rpg_context import Message, Role
from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.planning.plan import QueryPlan
from rpg_world.rpg_core.session.turns import iter_turn_groups
from rpg_world.rpg_core.settings import settings


class FakeTokenCounter:
    """Deterministic token counter for tests."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4) if text else 0

    def count_messages(self, messages: list[Message]) -> int:
        return sum(self.count(m.content) for m in messages)


@dataclass
class FakeTemplateModule:
    name: str
    template: str
    position: str = "before"
    enabled: bool = True


class FakeLLMProvider:
    """Minimal LLM provider stand-in."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages: list[dict[str, object]], tools=None):  # noqa: ANN001
        self.calls.append({"messages": messages, "tools": tools})
        return {"content": "mock reply", "tool_calls": []}


class FakeEmbedding:
    def __init__(self, vectors: list[list[float]] | None = None) -> None:
        self.vectors = vectors or [[0.1, 0.2, 0.3]]
        self.calls: list[list[str]] = []

    def embed_sync(self, queries: list[str]) -> list[list[float]]:
        self.calls.append(list(queries))
        return self.vectors

    async def embed(self, queries: list[str]) -> list[list[float]]:
        self.calls.append(list(queries))
        return self.vectors

    def dimension(self) -> int:
        return len(self.vectors[0]) if self.vectors else 0


class FakeStore:
    def __init__(self) -> None:
        self.vector_rows: list[tuple[MemoryCandidate, float]] = []
        self.bigram_rows: dict[str, list[MemoryCandidate]] = {}
        self.search_calls: list[tuple[list[float], int]] = []
        self.bigram_calls: list[tuple[str, int]] = []

    def search(self, query: list[float], top_k: int = 5, filters=None):  # noqa: ANN001
        self.search_calls.append((list(query), top_k))
        return self.vector_rows[:top_k]

    def bigram_search(self, query: str, limit: int = 50):
        self.bigram_calls.append((query, limit))
        return self.bigram_rows.get(query, [])[:limit]


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

    def retrieve_sync(self, query: str, top_k: int = 5):
        self.sync_calls.append((query, top_k))
        return self.raw[:top_k]

    def retrieve_plan_sync(self, plan, top_k: int = 5):  # noqa: ANN001
        self.plan_calls.append((plan.normalized_query, top_k))
        return self.raw[:top_k]

    def hybrid_search(self, plan, top_k: int = 20):  # noqa: ANN001
        self.hybrid_calls.append((plan.normalized_query, top_k))
        return [
            MemoryCandidate(memory_id=i + 1, content=text, metadata=meta, hybrid_score=score)
            for i, (text, score, meta) in enumerate(self.raw[:top_k])
        ]


class FakeBatchStore:
    def __init__(self) -> None:
        self.batch_summaries: list[dict[str, object]] = []
        self.overall = ("", 0)
        self.new_content = ["batch-1"]

    def save_batch_summary(self, **kwargs):
        self.batch_summaries.append(kwargs)
        return Path(f"batch_{kwargs['batch_id']}.md")

    def load_overall(self):
        return self.overall

    def get_new_content(self, last_batch_id: int):
        return list(self.new_content)

    def save_overall(self, **kwargs):
        self.overall = (kwargs.get("content", ""), kwargs.get("last_batch_id", 0))
        return Path("overall.md")

    def _next_batch_id(self):
        return 2


class FakeMemorySubAgent:
    def __init__(self) -> None:
        self.batch_calls: list[dict[str, object]] = []
        self.overall_calls: list[dict[str, object]] = []

    def _split_into_batches(self, conv, batch_size):  # noqa: ANN001
        groups = iter_turn_groups(list(conv))
        return [(1, list(conv), len(groups))] if conv else []

    async def _pipeline_batch_summary(self, conv, batch_id, user_rounds):  # noqa: ANN001
        self.batch_calls.append({"conv": conv, "batch_id": batch_id, "user_rounds": user_rounds})
        return {
            "title": f"batch-{batch_id}",
            "summary_text": "summary text",
            "time": "time",
            "location": "location",
            "characters": ["A"],
        }

    async def _pipeline_overall_summary(self, new_batches, existing_overall):  # noqa: ANN001
        self.overall_calls.append({"new_batches": list(new_batches), "existing_overall": existing_overall})
        return {
            "title": "overall",
            "summary_text": "overall text",
            "key_events": ["e1"],
        }


class FakeStatusManager:
    def __init__(self, tables: dict[str, dict[str, dict[str, object]]] | None = None) -> None:
        self.tables = tables or {}

    def list_types(self):
        return list(self.tables.keys())

    def list_tables(self, type_name: str):
        return list(self.tables.get(type_name, {}).keys())

    def get_table(self, type_name: str, table_name: str):
        return self.tables[type_name][table_name]

    def create_type(self, name: str):
        self.tables.setdefault(name, {})

    def create_table(self, type_name: str, table_name: str, headers, rows):  # noqa: ANN001
        self.tables.setdefault(type_name, {})
        self.tables[type_name][table_name] = {"name": table_name, "headers": headers, "rows": rows}
        return self.tables[type_name][table_name]

    def save_table(self, type_name: str, table_name: str, headers, rows):  # noqa: ANN001
        return self.create_table(type_name, table_name, headers, rows)


@pytest.fixture
def fake_token_counter() -> FakeTokenCounter:
    return FakeTokenCounter()


@pytest.fixture
def fake_template_modules() -> list[FakeTemplateModule]:
    return [
        FakeTemplateModule(name="prefix", template="modules/user_reply_prefix.jinja", position="before"),
        FakeTemplateModule(name="suffix", template="modules/user_reply_suffix.jinja", position="after"),
    ]


@pytest.fixture
def fake_recalled_store():
    class _Store:
        def __init__(self) -> None:
            self.items: list[str] = []

        def get_items(self):
            return list(self.items)

        def set_items(self, items):
            self.items = list(items)

    return _Store()


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    """Redirect session/workspace paths into a temporary directory."""
    root = tmp_path / "rpg"

    def workspace_root(workspace: str) -> Path:
        ws = workspace or "data/default"
        return (root / ws).resolve()

    def session_root(workspace: str, session_id: str) -> Path:
        return workspace_root(workspace) / "sessions" / session_id

    monkeypatch.setattr(settings, "session_dir", session_root)
    monkeypatch.setattr(settings, "sessions_base_dir", lambda workspace: workspace_root(workspace) / "sessions")
    monkeypatch.setattr(settings, "get_history_path", lambda workspace, session_id: session_root(workspace, session_id) / "history.jsonl")
    monkeypatch.setattr(settings, "get_cold_history_path", lambda workspace, session_id: session_root(workspace, session_id) / "history_cold.jsonl")
    monkeypatch.setattr(settings, "get_session_meta_path", lambda workspace, session_id: session_root(workspace, session_id) / "session.json")
    monkeypatch.setattr(settings, "get_summary_path", lambda workspace, session_id: session_root(workspace, session_id) / "rpg_summaries.json")
    monkeypatch.setattr(settings, "get_story_memory_path", lambda workspace, session_id: session_root(workspace, session_id) / "story_memory.json")
    monkeypatch.setattr(settings, "get_persistent_memory_path", lambda workspace, session_id: session_root(workspace, session_id) / "persistent_memory.md")
    monkeypatch.setattr(settings, "get_status_dir", lambda workspace, session_id: session_root(workspace, session_id) / "status")
    monkeypatch.setattr(settings, "get_vector_db_path", lambda workspace, session_id: str(session_root(workspace, session_id) / "memory_vectors.db"))
    monkeypatch.setattr(settings, "character_path", lambda workspace: str(workspace_root(workspace) / "character"))
    monkeypatch.setattr(settings, "lorebook_path", lambda workspace: str(workspace_root(workspace) / "lorebook"))
    return root


@pytest.fixture
def fake_memory_cfg():
    return SimpleNamespace(
        enabled=True,
        embedding_provider=SimpleNamespace(provider="llama", openai={}, llama={}),
        query_planner_provider=SimpleNamespace(provider="llama", openai={}, llama={}),
        rerank_provider=SimpleNamespace(provider="llama", openai={}, llama={}),
        embedding_model_path="",
        n_ctx=32768,
        n_gpu_layers=0,
        top_k=3,
        hybrid_enabled=True,
        vector_k=10,
        bigram_k=10,
        rerank_enabled=False,
        rerank_model_path="",
        rerank_max_candidates=5,
        rerank_n_ctx=4096,
        rerank_temperature=0.0,
        query_planner_enabled=False,
        query_planner_model_path="",
        query_planner_n_ctx=2048,
        query_planner_n_gpu_layers=0,
        query_planner_temperature=0.0,
        query_planner_max_tokens=128,
        chunk_size=2000,
        chunk_overlap=64,
    )


@pytest.fixture
def query_plan():
    return QueryPlan(
        original_query="查找线索",
        normalized_query="查找线索",
        bigram_queries=("查找线索",),
        expanded_queries=("查找线索",),
        raw_md_terms=("查找", "线索"),
    )
