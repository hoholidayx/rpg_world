from __future__ import annotations

import queue
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from rpg_world.rpg_core.llama_service.client import (
    LlamaClient,
    LlamaClientRemoteError,
    LlamaClientTimeout,
    configure_llama_client_from_memory_settings,
    get_llama_client,
    set_llama_client,
)
from rpg_world.rpg_core.llama_service.models import LlamaModelCache, model_cache_key
from rpg_world.rpg_core.llama_service.protocol import error_response, ok_response
from rpg_world.rpg_core.llama_service.server import LlamaServiceServer
from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.planning.planner import FallbackQueryPlanner, LlamaQueryPlanner
from rpg_world.rpg_core.memory.rerank.llama_reranker import LlamaRerankConfig, LlamaReranker
from rpg_world.rpg_core.agent.sub_agents import llama_provider as llama_provider_module
from rpg_world.rpg_core.agent.sub_agents.llama_provider import LlamaCompletionProvider


class _FakeProcess:
    def __init__(self, target) -> None:  # noqa: ANN001
        self._target = target
        self._thread: threading.Thread | None = None
        self.exitcode: int | None = None
        self.pid = 12345

    def start(self) -> None:
        def run() -> None:
            try:
                self._target()
                self.exitcode = 0
            except Exception:
                self.exitcode = 1

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def terminate(self) -> None:
        self.exitcode = -15


def _fake_process_factory(handler):  # noqa: ANN001
    def factory(request_queue, response_queue, _max_parallel_models):  # noqa: ANN001
        def run() -> None:
            while True:
                request = request_queue.get()
                response = handler(request)
                if response is not None:
                    response_queue.put(response)
                if request.get("op") == "shutdown":
                    return

        return _FakeProcess(run)

    return factory


def test_llama_client_matches_response_and_shutdown():
    client = LlamaClient(
        request_timeout_ms=1000,
        process_factory=_fake_process_factory(
            lambda request: ok_response(request["request_id"], {"op": request["op"]})
        ),
    )

    assert client.request("embedding_dimension") == {"op": "embedding_dimension"}
    client.shutdown()


def test_llama_client_timeout_and_remote_error():
    timeout_client = LlamaClient(
        request_timeout_ms=50,
        process_factory=_fake_process_factory(lambda _request: None),
    )
    with pytest.raises(LlamaClientTimeout):
        timeout_client.request("embedding_dimension")
    timeout_client.shutdown()

    error_client = LlamaClient(
        request_timeout_ms=1000,
        process_factory=_fake_process_factory(
            lambda request: error_response(request["request_id"], "boom")
        ),
    )
    with pytest.raises(LlamaClientRemoteError):
        error_client.request("embedding_dimension")
    error_client.shutdown()


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


def test_server_serializes_same_model_and_parallelizes_different_models():
    request_queue: queue.Queue = queue.Queue()
    response_queue: queue.Queue = queue.Queue()
    active = 0
    max_active = 0
    calls: list[str] = []
    lock = threading.Lock()

    class FakeCache:
        def complete(self, model, prompt, **_kwargs):  # noqa: ANN001
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
                calls.append(f"start:{prompt}")
            time.sleep(0.05)
            with lock:
                calls.append(f"end:{prompt}")
                active -= 1
            return {"choices": [{"text": prompt}]}

    server = LlamaServiceServer(
        request_queue,
        response_queue,
        max_parallel_models=3,
        cache=FakeCache(),  # type: ignore[arg-type]
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    same_model = {"model_path": "same.gguf", "n_ctx": 16, "n_gpu_layers": 0}
    request_queue.put(
        {
            "request_id": "1",
            "op": "complete",
            "model": same_model,
            "params": {"prompt": "a", "max_tokens": 1, "temperature": 0.0},
        }
    )
    request_queue.put(
        {
            "request_id": "2",
            "op": "complete",
            "model": same_model,
            "params": {"prompt": "b", "max_tokens": 1, "temperature": 0.0},
        }
    )
    assert response_queue.get(timeout=1)["ok"]
    assert response_queue.get(timeout=1)["ok"]
    assert calls[:4] == ["start:a", "end:a", "start:b", "end:b"]

    calls.clear()
    request_queue.put(
        {
            "request_id": "3",
            "op": "complete",
            "model": {"model_path": "a.gguf", "n_ctx": 16, "n_gpu_layers": 0},
            "params": {"prompt": "c", "max_tokens": 1, "temperature": 0.0},
        }
    )
    request_queue.put(
        {
            "request_id": "4",
            "op": "complete",
            "model": {"model_path": "b.gguf", "n_ctx": 16, "n_gpu_layers": 0},
            "params": {"prompt": "d", "max_tokens": 1, "temperature": 0.0},
        }
    )
    assert response_queue.get(timeout=1)["ok"]
    assert response_queue.get(timeout=1)["ok"]
    assert max_active >= 2

    request_queue.put({"request_id": "shutdown", "op": "shutdown"})
    assert response_queue.get(timeout=1)["ok"]
    thread.join(timeout=1)


def test_planner_and_reranker_fallback_when_client_fails(tmp_path):
    model = tmp_path / "planner.gguf"
    model.write_text("fake", encoding="utf-8")

    class FailingClient:
        def complete(self, *_args, **_kwargs):  # noqa: ANN002
            raise RuntimeError("client boom")

    set_llama_client(FailingClient())  # type: ignore[arg-type]
    try:
        planner = FallbackQueryPlanner(
            LlamaQueryPlanner(model_path=str(model)),
        )
        assert planner.plan("寻找北境线索").planner_source == "rule_based"

        candidates = [
            MemoryCandidate(memory_id=1, content="北境森林脚印", metadata={}, hybrid_score=0.8),
        ]
        reranker = LlamaReranker(
            LlamaRerankConfig(
                enabled=True,
                model_path=str(model),
            )
        )
        assert reranker.rerank("寻找北境线索", candidates) == candidates
    finally:
        set_llama_client(None)


def test_configure_llama_client_from_memory_settings_updates_process_config():
    set_llama_client(None)
    try:
        client = configure_llama_client_from_memory_settings(
            SimpleNamespace(
                llama_process_enabled=False,
                llama_request_timeout_ms=1234,
                llama_startup_timeout_ms=5678,
                llama_max_parallel_models=9,
            )
        )
        assert client is get_llama_client()
        assert client.enabled is False
        assert client.request_timeout_ms == 1234
        assert client.startup_timeout_ms == 5678
        assert client.max_parallel_models == 9
    finally:
        set_llama_client(None)


@pytest.mark.asyncio
async def test_llama_completion_provider_uses_to_thread_and_extracts_dict(monkeypatch):
    calls: list[dict[str, object]] = []
    to_thread_calls: list[str] = []

    class FakeCompletionModel:
        def __init__(self, model_path, **kwargs) -> None:  # noqa: ANN001
            calls.append({"model_path": str(model_path), **kwargs})

        def complete(self, prompt, **kwargs):  # noqa: ANN001
            calls.append({"prompt": prompt, **kwargs})
            return {"choices": [{"text": "hello from llama"}]}

    async def fake_to_thread(func, *args, **kwargs):  # noqa: ANN001
        to_thread_calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(llama_provider_module, "LlamaCompletionModel", FakeCompletionModel)
    monkeypatch.setattr(llama_provider_module.asyncio, "to_thread", fake_to_thread)

    provider = LlamaCompletionProvider(model_path="/tmp/fake.gguf", max_tokens=11, temperature=0.3)
    result = await provider.chat([{"role": "user", "content": "Hi"}])

    assert to_thread_calls == ["complete"]
    assert result.content == "hello from llama"
    assert result.tool_calls is None
    assert calls[1]["max_tokens"] == 11
    assert calls[1]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_llama_completion_provider_extracts_plain_string(monkeypatch):
    class FakeCompletionModel:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def complete(self, *_args, **_kwargs):
            return "plain text"

    monkeypatch.setattr(llama_provider_module, "LlamaCompletionModel", FakeCompletionModel)

    provider = LlamaCompletionProvider(model_path="/tmp/fake.gguf")
    result = await provider.chat([{"role": "user", "content": "Hi"}])

    assert result.content == "plain text"


@pytest.mark.asyncio
async def test_llama_completion_provider_builds_openai_tool_call(monkeypatch):
    class FakeCompletionModel:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def complete(self, prompt, **_kwargs):  # noqa: ANN001
            assert "TOOLS:" in prompt
            return '{"tool":"set_state","arguments":{"key":"地点","value":"大厅"}}'

    monkeypatch.setattr(llama_provider_module, "LlamaCompletionModel", FakeCompletionModel)

    provider = LlamaCompletionProvider(model_path="/tmp/fake.gguf")
    result = await provider.chat(
        [{"role": "user", "content": "change state"}],
        tools=[_tool_schema("set_state")],
    )

    assert result.finish_reason == "tool_calls"
    assert result.tool_calls
    call = result.tool_calls[0]
    assert call["type"] == "function"
    assert call["function"]["name"] == "set_state"
    assert '"key": "地点"' in call["function"]["arguments"]


@pytest.mark.asyncio
async def test_llama_completion_provider_uses_first_tool_when_name_missing(monkeypatch):
    class FakeCompletionModel:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def complete(self, *_args, **_kwargs):
            return '{"arguments":{"summary_text":"done"}}'

    monkeypatch.setattr(llama_provider_module, "LlamaCompletionModel", FakeCompletionModel)

    provider = LlamaCompletionProvider(model_path="/tmp/fake.gguf")
    result = await provider.chat(
        [{"role": "user", "content": "summarize"}],
        tools=[_tool_schema("generate_summary")],
    )

    assert result.tool_calls
    assert result.tool_calls[0]["function"]["name"] == "generate_summary"


@pytest.mark.asyncio
async def test_llama_completion_provider_keeps_unknown_tool_name(monkeypatch):
    class FakeCompletionModel:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def complete(self, *_args, **_kwargs):
            return '{"tool":"unknown_tool","arguments":{"x":1}}'

    monkeypatch.setattr(llama_provider_module, "LlamaCompletionModel", FakeCompletionModel)

    provider = LlamaCompletionProvider(model_path="/tmp/fake.gguf")
    result = await provider.chat(
        [{"role": "user", "content": "call"}],
        tools=[_tool_schema("known_tool")],
    )

    assert result.tool_calls
    assert result.tool_calls[0]["function"]["name"] == "unknown_tool"


@pytest.mark.asyncio
async def test_llama_completion_provider_invalid_json_returns_raw_content(monkeypatch):
    class FakeCompletionModel:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def complete(self, *_args, **_kwargs):
            return "not json"

    monkeypatch.setattr(llama_provider_module, "LlamaCompletionModel", FakeCompletionModel)

    provider = LlamaCompletionProvider(model_path="/tmp/fake.gguf")
    result = await provider.chat(
        [{"role": "user", "content": "call"}],
        tools=[_tool_schema("known_tool")],
    )

    assert result.content == "not json"
    assert result.tool_calls is None


@pytest.mark.asyncio
async def test_llama_completion_provider_empty_output_has_no_tool_call(monkeypatch):
    class FakeCompletionModel:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def complete(self, *_args, **_kwargs):
            return ""

    monkeypatch.setattr(llama_provider_module, "LlamaCompletionModel", FakeCompletionModel)

    provider = LlamaCompletionProvider(model_path="/tmp/fake.gguf")
    result = await provider.chat(
        [{"role": "user", "content": "call"}],
        tools=[_tool_schema("known_tool")],
    )

    assert result.tool_calls is None


@pytest.mark.asyncio
async def test_llama_completion_provider_chat_stream_yields_final_chunk(monkeypatch):
    class FakeCompletionModel:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def complete(self, *_args, **_kwargs):
            return '{"tool":"known_tool","arguments":{"x":1}}'

    monkeypatch.setattr(llama_provider_module, "LlamaCompletionModel", FakeCompletionModel)

    provider = LlamaCompletionProvider(model_path="/tmp/fake.gguf")
    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            [{"role": "user", "content": "call"}],
            tools=[_tool_schema("known_tool")],
        )
    ]

    assert len(chunks) == 1
    assert chunks[0].content
    assert chunks[0].tool_calls
    assert chunks[0].finish_reason == "tool_calls"
    assert chunks[0].model == "/tmp/fake.gguf"
    assert chunks[0].usage is None


def _tool_schema(name: str) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    }
