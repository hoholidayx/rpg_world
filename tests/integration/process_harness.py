"""Spawn production ASGI applications behind real loopback HTTP sockets."""

from __future__ import annotations

import json
import multiprocessing
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from llm_client.types import DocumentScoreProvider, LLMProvider


_TOKEN = "rpg-world-integration-token"


@dataclass
class ServiceProcess:
    kind: str
    process: multiprocessing.Process
    base_url: str

    def stop(self) -> None:
        if not self.process.is_alive():
            self.process.join(timeout=1)
            return
        self.process.terminate()
        self.process.join(timeout=5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=2)


def start_service(kind: str, **config: Any) -> ServiceProcess:
    """Start one service with an isolated import graph and ephemeral port."""

    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_serve,
        args=(kind, dict(config), sender),
        name=f"rpg-world-test-{kind}",
        daemon=True,
    )
    process.start()
    sender.close()
    if not receiver.poll(15):
        process.terminate()
        process.join(timeout=2)
        raise RuntimeError(f"Timed out starting {kind} service")
    message = receiver.recv()
    receiver.close()
    if "error" in message:
        process.join(timeout=2)
        raise RuntimeError(f"Failed to start {kind} service: {message['error']}")
    prefix = str(message["prefix"])
    return ServiceProcess(
        kind=kind,
        process=process,
        base_url=f"http://127.0.0.1:{int(message['port'])}{prefix}",
    )


def _serve(kind: str, config: dict[str, Any], sender) -> None:  # noqa: ANN001
    sock: socket.socket | None = None
    try:
        _configure_environment(config)
        app, prefix = _build_app(kind, config)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        port = int(sock.getsockname()[1])
        sender.send({"port": port, "prefix": prefix})
        sender.close()

        import uvicorn

        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="warning",
                access_log=False,
                lifespan="on",
            )
        )
        server.run(sockets=[sock])
    except BaseException as exc:
        try:
            sender.send({"error": f"{type(exc).__name__}: {exc}"})
            sender.close()
        except Exception:
            pass
        raise
    finally:
        if sock is not None:
            sock.close()


def _configure_environment(config: dict[str, Any]) -> None:
    os.environ["RPG_WORLD_PROFILE"] = "test"
    os.environ["RPG_WORLD_LLM_SERVICE_TOKEN"] = _TOKEN
    if config.get("db_path"):
        os.environ["RPG_WORLD_DB_PATH"] = str(config["db_path"])
    if config.get("workspace_root"):
        os.environ["RPG_WORLD_WORKSPACE_ROOT_BASE"] = str(config["workspace_root"])


def _build_app(kind: str, config: dict[str, Any]):  # noqa: ANN202
    if kind == "llm":
        return _build_llm_app(), "/llm/v1"
    if kind == "agent":
        return _build_agent_app(config), "/agent/v1"
    if kind == "media":
        return _build_media_app(config), "/media/v1"
    if kind == "play":
        return _build_play_app(config), "/play-api/v1"
    raise ValueError(f"Unknown service kind: {kind}")


def _build_llm_app():  # noqa: ANN202
    from llm_service import main as service_main
    from llm_service.manager import LLMManager

    fake_manager = _DeterministicLLMManager()
    LLMManager.get = classmethod(lambda cls: fake_manager)  # type: ignore[method-assign]
    return service_main.app


def _build_agent_app(config: dict[str, Any]):  # noqa: ANN202
    from agent_service import main as service_main

    service_main.process_settings = SimpleNamespace(
        service=service_main.process_settings.service,
        llm_client=SimpleNamespace(
            base_url=str(config["llm_url"]),
            token=_TOKEN,
            request_timeout_ms=5_000,
            stream_timeout_ms=10_000,
        ),
    )
    return service_main.app


def _build_media_app(config: dict[str, Any]):  # noqa: ANN202
    from media_service import main as service_main
    from media_service.main import MediaRuntime
    from media_service.worker import MediaJobWorker
    from rpg_data.services import get_data_service_gateway
    from rpg_core.scene.status import SceneStatusService
    from rpg_media.brief import LLMVisualBriefPlanner
    from rpg_media.service import MediaApplicationService
    from rpg_media.providers.catalog import MediaProviderCatalog
    from rpg_media.providers.local_file import LocalFileProvider

    service_main.process_settings = SimpleNamespace(
        service=service_main.process_settings.service,
        worker=SimpleNamespace(concurrency=1),
        background_worker=SimpleNamespace(concurrency=1),
        llm_client=SimpleNamespace(
            base_url=str(config["llm_url"]),
            token=_TOKEN,
            request_timeout_ms=5_000,
            stream_timeout_ms=10_000,
        ),
    )
    gateway = get_data_service_gateway()
    media_service = MediaApplicationService(
        data=gateway.media,
        catalog=gateway.catalog,
        planner=LLMVisualBriefPlanner(),
        providers=MediaProviderCatalog(
            (LocalFileProvider(Path(config["provider_dir"])),),
            default_key="local_file",
        ),
        status=SceneStatusService(gateway.status),
    )
    runtime = MediaRuntime(
        gateway=gateway,
        service=media_service,
        worker=MediaJobWorker(service=media_service, concurrency=1),
    )
    service_main.set_runtime_for_tests(runtime)
    return service_main.app


def _build_play_app(config: dict[str, Any]):  # noqa: ANN202
    from agent_service.client import AgentClient
    from media_service.client import MediaClient
    from play_api import agent_client, media_client
    from play_api import main as service_main

    agent_client._client = AgentClient(
        base_url=str(config["agent_url"]),
        request_timeout_ms=5_000,
        stream_timeout_ms=10_000,
    )
    media_client._client = MediaClient(
        base_url=str(config["media_url"]),
        request_timeout_ms=5_000,
    )
    return service_main.app


class _DeterministicProvider(LLMProvider):
    def __init__(self, biz_key: str) -> None:
        self.biz_key = biz_key

    async def chat(self, messages: list[dict], tools: list[dict] | None = None):  # noqa: ANN201
        from llm_client.keys import (
            AGENT_MAIN_BIZ_KEY,
            MEDIA_IMAGE_METADATA_BIZ_KEY,
            MEDIA_SCENE_BACKGROUND_MATCH_BIZ_KEY,
            MEDIA_VISUAL_BRIEF_BIZ_KEY,
        )
        from llm_client.types import LLMResponse, LLMUsage

        del messages
        content = ""
        tool_calls = None
        if self.biz_key == AGENT_MAIN_BIZ_KEY:
            content = "<rp-narration>真实 HTTP 集成回复。</rp-narration>"
        elif self.biz_key == MEDIA_VISUAL_BRIEF_BIZ_KEY:
            content = json.dumps(
                {
                    "sceneDescription": "月光下的测试大厅",
                    "subjects": ["测试者"],
                    "environment": "石质大厅",
                    "action": "观察银色天文仪",
                    "composition": "横向中景",
                    "moodLighting": "冷色月光",
                    "style": "写实奇幻",
                    "negativeConstraints": "无文字水印",
                    "aspectRatio": "16:9",
                },
                ensure_ascii=False,
            )
        elif self.biz_key == MEDIA_IMAGE_METADATA_BIZ_KEY:
            content = json.dumps(
                {
                    "title": "月光大厅",
                    "description": "月光照亮石质大厅。",
                    "tags": ["大厅", "夜晚"],
                },
                ensure_ascii=False,
            )
        elif self.biz_key == MEDIA_SCENE_BACKGROUND_MATCH_BIZ_KEY:
            names = {
                str(schema.get("function", {}).get("name", ""))
                for schema in (tools or [])
            }
            if "keep_background" in names:
                tool_calls = [
                    {
                        "id": "keep_1",
                        "function": {
                            "name": "keep_background",
                            "arguments": json.dumps(
                                {"reason": "场景没有发生实质变化"},
                                ensure_ascii=False,
                            ),
                        },
                    }
                ]
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
            model=f"integration-{self.biz_key}",
        )

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None):
        from llm_client.types import LLMUsage, ProviderChunk

        del messages, tools
        yield ProviderChunk(content="<rp-narration>真实 HTTP ")
        yield ProviderChunk(content="流式回复。</rp-narration>")
        yield ProviderChunk(
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=6, completion_tokens=4, total_tokens=10),
            model=f"integration-{self.biz_key}",
        )

    def get_default_model(self) -> str:
        return f"integration-{self.biz_key}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [float((sum(map(ord, text)) + offset) % 17) / 17 for offset in range(3)]
            for text in texts
        ]

    async def dimension(self) -> int:
        return 3


class _DeterministicScoreProvider(_DeterministicProvider, DocumentScoreProvider):
    def __init__(self) -> None:
        super().__init__("memory.rerank")

    async def score_documents(self, query: str, documents: list[str]):  # noqa: ANN201
        from llm_client.types import DocumentScore

        return [
            DocumentScore(
                score=0.9 if query.casefold() in document.casefold() else 0.2,
                reason="deterministic integration score",
            )
            for document in documents
        ]


class _DeterministicLLMManager:
    def __init__(self) -> None:
        self._providers: dict[str, object] = {}

    def get_provider(self, biz_key: str, *, provider_key: str | None = None):  # noqa: ANN201
        from llm_client.keys import MEMORY_RERANK_BIZ_KEY

        del provider_key
        if biz_key not in self._providers:
            self._providers[biz_key] = (
                _DeterministicScoreProvider()
                if biz_key == MEMORY_RERANK_BIZ_KEY
                else _DeterministicProvider(biz_key)
            )
        return self._providers[biz_key]


__all__ = ["ServiceProcess", "start_service", "_TOKEN"]
