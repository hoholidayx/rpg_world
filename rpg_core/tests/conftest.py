"""Shared fixtures and fakes for rpg_core tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


import pytest

from rpg_core.context.rpg_context import Message, Role
from rp_memory.candidate import MemoryCandidate
from rp_memory.planning.plan import QueryPlan
from rpg_core.session.manager import SessionManager
from llm_service.manager import LLMManager


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


@pytest.fixture(autouse=True)
def reset_llm_manager():
    LLMManager.reset()
    yield
    LLMManager.reset()


class FakeMemorySubAgent:
    def __init__(self) -> None:
        self.batch_calls: list[dict[str, object]] = []
        self.overall_calls: list[dict[str, object]] = []

    def _split_into_batches(self, conv, batch_size):  # noqa: ANN001
        groups = SessionManager.iter_turn_groups(list(conv))
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
    def __init__(self, scene_table: dict[str, object] | None = None) -> None:
        self.scene_table = scene_table
        self.calls: list[tuple[str, int, str, str | None]] = []

    def get_active_scene_table(self):
        return self.scene_table

    def get_active_scene_table_ref(self):
        if self.scene_table is None:
            return None
        return (
            int(self.scene_table["id"]),
            (str(self.scene_table["type_name"]), str(self.scene_table["name"])),
        )

    def get_scene_attrs(self):
        if self.scene_table is None:
            return None
        attrs: dict[str, str] = {}
        for row in self.scene_table.get("rows", []):
            if len(row) >= 2:
                attrs[str(row[0])] = str(row[1])
        return attrs

    def set_key_value(self, table_id: int, key: str, value: str):
        self.calls.append(("set", table_id, key, value))
        if self.scene_table is None:
            raise FileNotFoundError("scene table missing")
        rows = self.scene_table.setdefault("rows", [])
        for row in rows:
            if row and row[0] == key:
                if len(row) < 2:
                    row.append(value)
                else:
                    row[1] = value
                return self.scene_table
        rows.append([key, value])
        return self.scene_table

    def runtime_set_key_value(self, table_id: int, key: str, value: str):
        return self.set_key_value(table_id, key, value)

    def delete_key_value(self, table_id: int, key: str):
        self.calls.append(("delete", table_id, key, None))
        if self.scene_table is None:
            raise FileNotFoundError("scene table missing")
        rows = self.scene_table.setdefault("rows", [])
        for idx, row in enumerate(rows):
            if row and row[0] == key:
                del rows[idx]
                return self.scene_table
        raise FileNotFoundError(key)

    def runtime_delete_key_value(self, table_id: int, key: str):
        return self.delete_key_value(table_id, key)


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
def rpg_data_gateway(tmp_path, monkeypatch):
    from rpg_data.services import get_data_service_gateway, reset_data_service_gateways

    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_data.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    gateway = get_data_service_gateway()
    yield gateway
    reset_data_service_gateways()


@pytest.fixture
def make_data_session(rpg_data_gateway):
    from rpg_data.repositories.session_repo import SessionRepository
    from rpg_data.repositories.story_repo import StoryRepository
    from rpg_data.repositories.workspace_repo import WorkspaceRepository

    def _make(
        session_id: str = "s1",
        *,
        workspace_id: str = "test_workspace",
        story_title: str = "Test Story",
    ) -> str:
        database = rpg_data_gateway.database
        workspaces = WorkspaceRepository(database)
        stories = StoryRepository(database)
        sessions = SessionRepository(database)

        with database.atomic():
            if workspaces.get(workspace_id) is None:
                workspaces.create(workspace_id, workspace_id, f"data/{workspace_id}")
            story = next(
                (candidate for candidate in stories.list(workspace_id) if candidate.title == story_title),
                None,
            )
            if story is None:
                story = stories.create(workspace_id, story_title)
            if sessions.get(session_id) is None:
                sessions.create(
                    workspace_id,
                    story.id,
                    session_id=session_id,
                    title=session_id,
                )
        return session_id

    return _make


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
        keyword_tokenizer="jieba",
        keyword_k=10,
        hybrid_vector_weight=0.47,
        hybrid_keyword_weight=0.18,
        hybrid_raw_md_weight=0.05,
        hybrid_exact_weight=0.10,
        hybrid_expanded_weight=0.10,
        hybrid_recency_weight=0.05,
        hybrid_granularity_weight=0.05,
        raw_md_mode="fallback_only",
        raw_md_min_results=0,
        rerank_candidate_k=8,
        rerank_enabled=False,
        rerank_score_weight=0.70,
        rerank_model_path="",
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
        keyword_queries=("查找线索",),
        expanded_queries=("查找线索",),
        raw_md_terms=("查找", "线索"),
    )
