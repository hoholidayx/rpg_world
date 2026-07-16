from __future__ import annotations

import asyncio
import sys
import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from llm_client.auth import (
    DEFAULT_LLM_SERVICE_TOKEN,
    DEFAULT_LLM_SERVICE_TOKEN_ENV,
)
from llm_client.types import DocumentScore, DocumentScoreProvider, LLMProvider, LLMResponse, ProviderChunk
from llm_service import main as service_main
from llm_service.llama_provider import LlamaCompletionProvider
from llm_service.errors import LLMInputModalityUnsupportedError
from llm_service.models import LlamaModelCache, build_qwen_rerank_prompt, model_cache_key
from llm_service.runtime import (
    DirectLlamaRuntime,
    LlamaRuntimeCapacityError,
    LlamaRuntimeTimeoutError,
)


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


async def test_direct_runtime_times_out_queued_request_before_execution():
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    class FakeCache:
        def complete(self, model, prompt, **_kwargs):  # noqa: ANN001
            del model
            calls.append(prompt)
            if prompt == "first":
                started.set()
                release.wait(timeout=1.0)
            return prompt

    runtime = DirectLlamaRuntime(max_parallel_models=1, cache=FakeCache())  # type: ignore[arg-type]
    model = {"model_path": "same.gguf", "n_ctx": 16, "n_gpu_layers": 0}
    first = asyncio.create_task(
        runtime.complete_async(
            model,
            "first",
            max_tokens=1,
            temperature=0.0,
            request_timeout_ms=1000,
        )
    )
    assert await asyncio.to_thread(started.wait, 1.0)

    with pytest.raises(LlamaRuntimeTimeoutError):
        await runtime.complete_async(
            model,
            "timed-out",
            max_tokens=1,
            temperature=0.0,
            request_timeout_ms=20,
        )

    release.set()
    assert await first == "first"
    await asyncio.sleep(0.02)
    assert calls == ["first"]
    runtime.close()


async def test_active_completion_observes_cooperative_timeout():
    started = threading.Event()
    cancellation_seen = threading.Event()

    class FakeCache:
        def complete(self, model, prompt, *, cancelled, **_kwargs):  # noqa: ANN001
            del model, prompt
            started.set()
            while not cancelled():
                time.sleep(0.002)
            cancellation_seen.set()
            return "stopped"

    runtime = DirectLlamaRuntime(max_parallel_models=1, cache=FakeCache())  # type: ignore[arg-type]
    model = {"model_path": "active.gguf", "n_ctx": 16, "n_gpu_layers": 0}

    with pytest.raises(LlamaRuntimeTimeoutError):
        await runtime.complete_async(
            model,
            "slow",
            max_tokens=1,
            temperature=0.0,
            request_timeout_ms=20,
        )

    assert started.is_set()
    assert await asyncio.to_thread(cancellation_seen.wait, 1.0)
    runtime.close()


async def test_native_embedding_timeout_returns_while_actor_drains() -> None:
    first_started = threading.Event()
    second_started = threading.Event()
    release_first = threading.Event()

    class FakeCache:
        def embed(self, _model, texts):  # noqa: ANN001
            if texts == ["first"]:
                first_started.set()
                release_first.wait(timeout=1.0)
            else:
                second_started.set()
            return [[float(len(text))] for text in texts]

    runtime = DirectLlamaRuntime(max_parallel_models=1, cache=FakeCache())  # type: ignore[arg-type]
    model = {"model_path": "embed.gguf", "n_ctx": 16, "n_gpu_layers": 0}
    first = asyncio.create_task(
        runtime.embed_async(model, ["first"], request_timeout_ms=20)
    )
    assert await asyncio.to_thread(first_started.wait, 1.0)

    with pytest.raises(LlamaRuntimeTimeoutError):
        await first

    second = asyncio.create_task(
        runtime.embed_async(model, ["second"], request_timeout_ms=1000)
    )
    await asyncio.sleep(0.03)
    assert second_started.is_set() is False

    release_first.set()
    assert await second == [[6.0]]
    assert second_started.is_set() is True
    runtime.close()


async def test_rerank_timeout_stops_at_document_boundary(tmp_path, monkeypatch):
    model_path = tmp_path / "rerank-timeout.gguf"
    model_path.write_text("fake", encoding="utf-8")
    eval_finished = threading.Event()
    instances: list[object] = []

    class FakeLlama:
        def __init__(self, **_kwargs) -> None:
            self.eval_count = 0
            self.scores: list[list[float]] = []
            instances.append(self)

        def tokenize(self, raw, add_bos=False, special=False):  # noqa: ANN001
            del special
            text = raw.decode("utf-8")
            if text == "yes":
                return [1]
            if text == "no":
                return [2]
            return ([7] if add_bos else []) + [3]

        def reset(self) -> None:
            pass

        def eval(self, tokens):  # noqa: ANN001
            self.eval_count += 1
            time.sleep(0.05)
            self.scores = [[0.0] * 8 for _ in tokens]
            self.scores[-1][1] = 2.0
            self.scores[-1][2] = 0.0
            eval_finished.set()

    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeLlama))
    runtime = DirectLlamaRuntime(max_parallel_models=1, cache=LlamaModelCache())
    model = {"model_path": str(model_path), "n_ctx": 128, "n_gpu_layers": 0}

    with pytest.raises(LlamaRuntimeTimeoutError):
        await runtime.rerank_async(
            model,
            "query",
            ["first", "second"],
            instruction="match",
            max_length=64,
            request_timeout_ms=10,
        )

    assert await asyncio.to_thread(eval_finished.wait, 1.0)
    await asyncio.sleep(0.01)
    assert instances[0].eval_count == 1
    runtime.close()


async def test_llama_stream_timeout_cancels_active_callback():
    cancellation_seen = threading.Event()

    class FakeStreamModel:
        def start_complete_stream(self, *args, on_chunk, cancelled, **kwargs):  # noqa: ANN002, ANN003
            del args, on_chunk, kwargs
            future: Future[None] = Future()

            def run() -> None:
                cancelled.wait(timeout=1.0)
                cancellation_seen.set()
                if not future.cancelled():
                    future.set_result(None)

            threading.Thread(target=run, daemon=True).start()
            return future

    provider = LlamaCompletionProvider(
        model_path="fake.gguf",
        request_timeout_ms=20,
        model=FakeStreamModel(),  # type: ignore[arg-type]
    )

    with pytest.raises(LlamaRuntimeTimeoutError):
        async for _chunk in provider.chat_stream(
            [{"role": "user", "content": "slow"}],
        ):
            pass

    assert await asyncio.to_thread(cancellation_seen.wait, 1.0)


async def test_llama_stream_consumer_cancel_stops_active_callback():
    cancellation_seen = threading.Event()

    class FakeStreamModel:
        def start_complete_stream(self, *args, on_chunk, cancelled, **kwargs):  # noqa: ANN002, ANN003
            del args, kwargs
            future: Future[None] = Future()

            def run() -> None:
                on_chunk("first")
                cancelled.wait(timeout=1.0)
                cancellation_seen.set()
                if not future.cancelled():
                    future.set_result(None)

            threading.Thread(target=run, daemon=True).start()
            return future

    provider = LlamaCompletionProvider(
        model_path="fake.gguf",
        request_timeout_ms=1000,
        model=FakeStreamModel(),  # type: ignore[arg-type]
    )
    stream = provider.chat_stream([{"role": "user", "content": "stream"}])

    chunk = await anext(stream)
    await stream.aclose()

    assert chunk.content == "first"
    assert await asyncio.to_thread(cancellation_seen.wait, 1.0)


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


@pytest.mark.asyncio
async def test_llama_completion_rejects_image_before_model_call():
    class FakeModel:
        async def complete_async(self, *_args, **_kwargs):
            raise AssertionError("model must not receive image input")

    provider = LlamaCompletionProvider(
        model_path="fake.gguf",
        model=FakeModel(),  # type: ignore[arg-type]
    )
    with pytest.raises(LLMInputModalityUnsupportedError):
        await provider.chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
                        },
                    ],
                }
            ]
        )


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

    async def dimension(self) -> int:
        return 1

    async def score_documents(self, query, documents):  # noqa: ANN001
        return [DocumentScore(score=0.75, reason="match") for _ in documents]


def test_http_service_starts_with_shared_default_token_and_warns(monkeypatch):
    monkeypatch.delenv(DEFAULT_LLM_SERVICE_TOKEN_ENV, raising=False)
    warning_calls: list[tuple[object, ...]] = []
    real_logger = service_main.logger
    monkeypatch.setattr(
        service_main,
        "logger",
        SimpleNamespace(
            warning=lambda *args: warning_calls.append(args),
            exception=real_logger.exception,
        ),
    )

    headers = {"Authorization": f"Bearer {DEFAULT_LLM_SERVICE_TOKEN}"}
    with TestClient(service_main.app) as client:
        assert client.get("/llm/v1/health").status_code == 200
        assert client.get("/llm/v1/catalog/agent.main").status_code == 401
        assert client.get(
            "/llm/v1/catalog/agent.main",
            headers=headers,
        ).status_code == 200

    assert len(warning_calls) == 1
    assert DEFAULT_LLM_SERVICE_TOKEN_ENV in warning_calls[0]


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

        unsupported = client.post(
            "/llm/v1/chat",
            headers=headers,
            json={
                "bizKey": "agent.main",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "describe"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,iVBORw0KGgo="
                                },
                            },
                        ],
                    }
                ],
            },
        )
        assert unsupported.status_code == 422
        assert unsupported.json()["detail"]["errorCode"] == "LLM_INPUT_MODALITY_UNSUPPORTED"

        remote_url = client.post(
            "/llm/v1/chat",
            headers=headers,
            json={
                "bizKey": "agent.main",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": "https://example.test/image.png"},
                            }
                        ],
                    }
                ],
            },
        )
        assert remote_url.status_code == 422
        assert remote_url.json()["detail"]["errorCode"] == "LLM_REQUEST_INVALID"

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


def test_http_speech_profile_and_binary_contract(monkeypatch):
    monkeypatch.setenv("RPG_WORLD_LLM_SERVICE_TOKEN", "test-token")

    class FakeSpeechProvider:
        profile = SimpleNamespace(
            provider_key="openai-tts",
            model="tts-model",
            voice="alloy",
            response_format="mp3",
            speed=1.0,
            cache_revision="v1",
            config_fingerprint="e" * 64,
        )

        async def synthesize(self, text: str) -> bytes:
            assert text == "hello"
            return b"ID3audio"

    class FakeManager:
        def get_speech_provider(self, _biz_key, *, provider_key=None):  # noqa: ANN001, ANN201
            del provider_key
            return FakeSpeechProvider()

    monkeypatch.setattr(
        service_main.LLMManager,
        "get",
        classmethod(lambda cls: FakeManager()),
    )
    headers = {"Authorization": "Bearer test-token"}
    with TestClient(service_main.app) as client:
        profile = client.get("/llm/v1/speech/profile/tts.reply", headers=headers)
        audio = client.post(
            "/llm/v1/speech",
            headers=headers,
            json={"bizKey": "tts.reply", "text": "hello"},
        )

    assert profile.status_code == 200
    assert profile.json()["voice"] == "alloy"
    assert audio.status_code == 200
    assert audio.content == b"ID3audio"
    assert audio.headers["x-speech-config-fingerprint"] == "e" * 64
