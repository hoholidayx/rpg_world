from __future__ import annotations

import asyncio
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from llm_client.types import DocumentScore, DocumentScoreProvider, LLMProvider, LLMResponse, ProviderChunk
from llm_service import main as service_main
from llm_service.llama_provider import LlamaCompletionProvider
from llm_service.models import LlamaModelCache, build_qwen_rerank_prompt, model_cache_key
from llm_service.runtime import DirectLlamaRuntime, LlamaRuntimeCapacityError


def test_model_cache_reuses_same_key_and_splits_different_keys(tmp_path, monkeypatch):
    model_a = tmp_path / "a.gguf"
    model_b = tmp_path / "b.gguf"
    model_a.write_text("fake", encoding="utf-8")
    model_b.write_text("fake", encoding="utf-8")
    created: list[str] = []

    class FakeLlama:
        def __init__(self, model_path: str, **_kwargs) -> None:
            created.append(model_path)

        def embed(self, texts):  # noqa: ANN001
            return [[float(len(text))] for text in texts]

    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeLlama))
    cache = LlamaModelCache()
    model = {"model_path": str(model_a), "n_ctx": 16, "n_gpu_layers": 0, "n_threads": 1}

    assert cache.embedding_dimension(model) == 1
    assert cache.embed(model, ["x"]) == [[1.0]]
    cache.embed({"model_path": str(model_b), "n_ctx": 16, "n_gpu_layers": 0, "n_threads": 1}, ["xx"])

    assert created == [str(model_a), str(model_b)]
    assert cache.load_counts[model_cache_key("embed", model)] == 1


def test_model_cache_rerank_uses_yes_no_logits_in_order(tmp_path, monkeypatch):
    model_path = tmp_path / "rerank.gguf"
    model_path.write_text("fake", encoding="utf-8")

    class FakeLlama:
        def __init__(self, **_kwargs) -> None:
            self.eval_count = 0
            self.scores: list[list[float]] = []

        def tokenize(self, raw, add_bos=False, special=False):  # noqa: ANN001
            text = raw.decode("utf-8")
            if text == "yes":
                return [1]
            if text == "no":
                return [2]
            return ([7] if add_bos else []) + [3] * max(1, len(text))

        def reset(self):
            pass

        def eval(self, tokens):  # noqa: ANN001
            self.eval_count += 1
            yes_logit, no_logit = ((3.0, 1.0) if self.eval_count == 1 else (0.0, 4.0))
            self.scores = [[0.0] * 8 for _ in tokens]
            self.scores[-1][1] = yes_logit
            self.scores[-1][2] = no_logit

    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeLlama))
    cache = LlamaModelCache()
    model = {"model_path": str(model_path), "n_ctx": 128, "n_gpu_layers": 0}
    result = cache.rerank(
        model,
        "wolf query",
        ["wolf document", "tavern document"],
        instruction="match memories",
        max_length=128,
    )

    assert result[0]["score"] == pytest.approx(0.880797, rel=1e-5)
    assert result[1]["score"] == pytest.approx(0.017986, rel=1e-4)


def test_direct_runtime_serializes_same_model_and_bounds_distinct_models():
    active = 0
    max_active = 0
    lock = threading.Lock()

    class FakeCache:
        def complete(self, model, prompt, **_kwargs):  # noqa: ANN001
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return prompt

    runtime = DirectLlamaRuntime(max_parallel_models=2, cache=FakeCache())  # type: ignore[arg-type]
    model_a = {"model_path": "a.gguf", "n_ctx": 16, "n_gpu_layers": 0}
    threads = [
        threading.Thread(
            target=lambda: runtime.complete(model_a, "x", max_tokens=1, temperature=0.0)
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert max_active == 1

    runtime.complete(
        {"model_path": "b.gguf", "n_ctx": 16, "n_gpu_layers": 0},
        "b",
        max_tokens=1,
        temperature=0.0,
    )
    with pytest.raises(LlamaRuntimeCapacityError):
        runtime.complete(
            {"model_path": "c.gguf", "n_ctx": 16, "n_gpu_layers": 0},
            "c",
            max_tokens=1,
            temperature=0.0,
        )
    runtime.close()


@pytest.mark.asyncio
async def test_direct_runtime_cancels_queued_same_model_request_before_execution():
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    class FakeCache:
        def complete(self, model, prompt, **_kwargs):  # noqa: ANN001
            calls.append(prompt)
            if prompt == "first":
                started.set()
                release.wait(timeout=1.0)
            return prompt

    runtime = DirectLlamaRuntime(max_parallel_models=1, cache=FakeCache())  # type: ignore[arg-type]
    model = {"model_path": "same.gguf", "n_ctx": 16, "n_gpu_layers": 0}
    first = asyncio.create_task(
        runtime.complete_async(model, "first", max_tokens=1, temperature=0.0)
    )
    assert await asyncio.to_thread(started.wait, 1.0)

    queued = asyncio.create_task(
        runtime.complete_async(model, "cancelled", max_tokens=1, temperature=0.0)
    )
    await asyncio.sleep(0)
    queued.cancel()
    with pytest.raises(asyncio.CancelledError):
        await queued

    release.set()
    assert await first == "first"
    await asyncio.sleep(0.01)
    assert calls == ["first"]
    runtime.close()


def test_build_qwen_rerank_prompt_uses_official_sections():
    prompt = build_qwen_rerank_prompt(
        instruction="match memories",
        query="wolf query",
        document="wolf document",
    )
    assert "<Instruct>: match memories" in prompt
    assert "<Query>: wolf query" in prompt
    assert "<Document>: wolf document" in prompt


@pytest.mark.asyncio
async def test_llama_completion_provider_builds_tool_call():
    class FakeModel:
        async def complete_async(self, *_args, **_kwargs):
            return '{"tool":"scene_time","arguments":{"time":"night"}}'

    provider = LlamaCompletionProvider(
        model_path="fake.gguf",
        model=FakeModel(),  # type: ignore[arg-type]
    )
    response = await provider.chat(
        [{"role": "user", "content": "advance"}],
        tools=[{"type": "function", "function": {"name": "scene_time"}}],
    )
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0]["function"]["name"] == "scene_time"


class _FakeProvider(LLMProvider, DocumentScoreProvider):
    def get_default_model(self) -> str:
        return "fake-model"

    async def chat(self, messages, tools=None):  # noqa: ANN001
        return LLMResponse("reply", None, "stop", model="fake-model", request_id="req-1")

    async def chat_stream(self, messages, tools=None):  # noqa: ANN001
        yield ProviderChunk(content="re", model="fake-model")
        yield ProviderChunk(content="ply", finish_reason="stop", model="fake-model")

    async def embed(self, texts):  # noqa: ANN001
        return [[float(len(text))] for text in texts]

    def embed_sync(self, texts):  # noqa: ANN001
        return [[float(len(text))] for text in texts]

    def dimension(self) -> int:
        return 1

    async def score_documents(self, query, documents):  # noqa: ANN001
        return [DocumentScore(score=0.75, reason="match") for _ in documents]


def test_http_contract_auth_chat_stream_embedding_and_rerank(monkeypatch):
    monkeypatch.setenv("RPG_WORLD_LLM_SERVICE_TOKEN", "test-token")
    provider = _FakeProvider()

    class FakeManager:
        def get_provider(self, _biz_key, *, provider_key=None):  # noqa: ANN001, ANN201
            return provider

    monkeypatch.setattr(
        service_main.LLMManager,
        "get",
        classmethod(lambda cls: FakeManager()),
    )
    headers = {"Authorization": "Bearer test-token"}
    with TestClient(service_main.app) as client:
        assert client.post(
            "/llm/v1/chat",
            json={"bizKey": "agent.main", "messages": [{"role": "user", "content": "hi"}]},
        ).status_code == 401

        chat = client.post(
            "/llm/v1/chat",
            headers=headers,
            json={"bizKey": "agent.main", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert chat.status_code == 200
        assert chat.json()["content"] == "reply"

        stream = client.post(
            "/llm/v1/chat/stream",
            headers=headers,
            json={"bizKey": "agent.main", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert "event: chunk" in stream.text
        assert "event: done" in stream.text

        embedded = client.post(
            "/llm/v1/embeddings",
            headers=headers,
            json={"bizKey": "memory.embed", "texts": ["abc"]},
        )
        assert embedded.json() == {"vectors": [[3.0]]}
        dimension = client.get(
            "/llm/v1/embeddings/dimension",
            headers=headers,
            params={"bizKey": "memory.embed"},
        )
        assert dimension.json() == {"dimension": 1}

        reranked = client.post(
            "/llm/v1/rerank",
            headers=headers,
            json={"bizKey": "memory.rerank", "query": "q", "documents": ["d"]},
        )
        assert reranked.json()["scores"][0]["score"] == 0.75
