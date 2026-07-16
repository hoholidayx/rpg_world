from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from rpg_core.tests.integration.conftest import _create_integration_session
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways
from tests.integration.process_harness import ServiceProcess, _TOKEN, start_service


pytestmark = [
    pytest.mark.service_integration,
    pytest.mark.skipif(
        os.environ.get("SERVICE_INTEGRATION_TEST") != "1",
        reason="set SERVICE_INTEGRATION_TEST=1 to run cross-process service tests",
    ),
]


@dataclass
class BackendStack:
    llm: ServiceProcess
    agent: ServiceProcess
    media: ServiceProcess
    play: ServiceProcess
    db_path: Path
    workspace_root: Path

    def stop(self) -> None:
        for service in (self.play, self.media, self.agent, self.llm):
            service.stop()


@pytest_asyncio.fixture
async def backend_stack(tmp_path: Path, monkeypatch) -> BackendStack:
    db_path = tmp_path / "backend-stack.sqlite3"
    workspace_root = tmp_path / "workspace"
    provider_dir = tmp_path / "provider"
    workspace_root.mkdir()
    provider_dir.mkdir()
    (provider_dir / "generated.png").write_bytes(
        b"\x89PNG\r\n\x1a\nreal-http-service-smoke"
    )
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(db_path))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(workspace_root))
    reset_data_service_gateways()
    gateway = get_data_service_gateway(db_path)
    for session_id in (
        "service_stack_main",
        "service_stack_delete",
        "service_stack_failure",
    ):
        _create_integration_session(
            gateway,
            workspace_root,
            session_id,
        )
    reset_data_service_gateways()

    started: list[ServiceProcess] = []
    try:
        llm = start_service("llm")
        started.append(llm)
        await _wait_ready(llm)
        agent = start_service(
            "agent",
            db_path=db_path,
            workspace_root=workspace_root,
            llm_url=llm.base_url,
        )
        started.append(agent)
        await _wait_ready(agent)
        media = start_service(
            "media",
            db_path=db_path,
            workspace_root=workspace_root,
            llm_url=llm.base_url,
            provider_dir=provider_dir,
        )
        started.append(media)
        await _wait_ready(media)
        play = start_service(
            "play",
            db_path=db_path,
            workspace_root=workspace_root,
            agent_url=agent.base_url,
            media_url=media.base_url,
        )
        started.append(play)
        await _wait_ready(play, path="/sessions/service_stack_main")
        stack = BackendStack(
            llm=llm,
            agent=agent,
            media=media,
            play=play,
            db_path=db_path,
            workspace_root=workspace_root,
        )
        yield stack
    finally:
        for service in reversed(started):
            service.stop()
        reset_data_service_gateways()


async def _wait_ready(service: ServiceProcess, *, path: str = "/health") -> None:
    deadline = asyncio.get_running_loop().time() + 10
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=1) as client:
        while asyncio.get_running_loop().time() < deadline:
            if not service.process.is_alive():
                raise RuntimeError(f"{service.kind} service exited during startup")
            try:
                response = await client.get(f"{service.base_url}{path}")
                if response.status_code < 500:
                    return
            except httpx.HTTPError as exc:
                last_error = exc
            await asyncio.sleep(0.05)
    raise RuntimeError(f"{service.kind} service was not ready: {last_error}")


def _data_payloads(text: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.mark.asyncio
async def test_backend_services_cover_chat_media_deletion_and_failure_isolation(
    backend_stack: BackendStack,
) -> None:
    auth = {"Authorization": f"Bearer {_TOKEN}"}
    async with httpx.AsyncClient(timeout=10) as client:
        health = await client.get(f"{backend_stack.llm.base_url}/health")
        catalog = await client.get(
            f"{backend_stack.llm.base_url}/catalog/agent.main",
            headers=auth,
        )
        embedded = await client.post(
            f"{backend_stack.llm.base_url}/embeddings",
            headers=auth,
            json={"bizKey": "memory.embed", "texts": ["银色天文仪"]},
        )
        dimension = await client.get(
            f"{backend_stack.llm.base_url}/embeddings/dimension",
            headers=auth,
            params={"bizKey": "memory.embed"},
        )
        reranked = await client.post(
            f"{backend_stack.llm.base_url}/rerank",
            headers=auth,
            json={
                "bizKey": "memory.rerank",
                "query": "天文仪",
                "documents": ["天文仪位于北侧", "大厅没有目标"],
            },
        )

        assert health.json() == {"status": "ok", "configLoaded": True}
        assert catalog.status_code == 200
        assert catalog.json()["bizKey"] == "agent.main"
        assert embedded.status_code == 200 and len(embedded.json()["vectors"][0]) == 3
        assert dimension.json() == {"dimension": 3}
        assert [item["score"] for item in reranked.json()["scores"]] == [0.9, 0.2]

        turn = await client.post(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/turn",
            json={"text": "观察大厅"},
        )
        preview = await client.get(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/context-preview"
        )
        stream = await client.post(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/stream",
            json={"text": "继续前进", "requestId": "service-stack-stream"},
        )
        history = await client.get(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/history"
        )

        assert turn.status_code == 200
        assert turn.json()["reply"] == "<rp-narration>真实 HTTP 集成回复。</rp-narration>"
        assert turn.json()["committedTurnId"] == 1
        assert turn.json()["usage"]["total_tokens"] > 0
        assert preview.status_code == 200
        assert preview.json()["sessionId"] == "service_stack_main"
        stream_events = _data_payloads(stream.text)
        assert [event["type"] for event in stream_events] == [
            "turn_started",
            "text_delta",
            "text_delta",
            "turn_completed",
        ]
        assert stream_events[-1]["payload"]["committedTurnId"] == 2
        assert len(history.json()) == 2
        assert [turn_payload["turnId"] for turn_payload in history.json()] == [1, 2]

        providers = await client.get(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/media/providers"
        )
        brief = await client.post(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/media/briefs",
            json={"startTurnId": 1, "endTurnId": 1},
        )
        assert providers.status_code == 200
        assert providers.json()["defaultKey"] == "local_file"
        assert brief.status_code == 200
        assert brief.json()["brief"]["sceneDescription"] == "月光下的测试大厅"

        job = await client.post(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/media/jobs",
            json={
                "providerKey": "local_file",
                "startTurnId": 1,
                "endTurnId": 1,
                "sourceFingerprint": brief.json()["sourceFingerprint"],
                "visualBrief": brief.json()["brief"],
                "generationParams": {},
            },
        )
        assert job.status_code == 200
        job_id = job.json()["jobId"]
        job_payload = job.json()
        for _ in range(100):
            current = await client.get(
                f"{backend_stack.play.base_url}/sessions/service_stack_main/media/jobs/{job_id}"
            )
            job_payload = current.json()
            if job_payload["status"] not in {"queued", "running", "cancelling"}:
                break
            await asyncio.sleep(0.03)
        assert job_payload["status"] == "succeeded"

        gallery = await client.get(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/media/gallery"
        )
        asset_id = gallery.json()["items"][0]["assetId"]
        content = await client.get(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/media/assets/{asset_id}/content"
        )
        background = await client.put(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/media/background",
            json={"assetId": asset_id},
        )
        blocked_delete = await client.delete(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/media/assets/{asset_id}"
        )
        unsupported_analysis = await client.post(
            f"{backend_stack.play.base_url}/workspaces/integration_workspace/media/library/analyze",
            files={
                "file": (
                    "generated.png",
                    b"\x89PNG\r\n\x1a\nanalysis",
                    "image/png",
                )
            },
        )

        assert content.status_code == 200
        assert content.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert background.json()["background"]["assetId"] == asset_id
        assert blocked_delete.status_code == 409
        assert blocked_delete.json()["detail"]["errorCode"] == "MEDIA_ASSET_IN_USE"
        assert unsupported_analysis.status_code == 422
        assert (
            unsupported_analysis.json()["detail"]["errorCode"]
            == "MEDIA_IMAGE_ANALYSIS_UNSUPPORTED"
        )

        delete_turn = await client.post(
            f"{backend_stack.play.base_url}/sessions/service_stack_delete/turn",
            json={"text": "delete this session"},
        )
        deleted = await client.delete(
            f"{backend_stack.play.base_url}/sessions/service_stack_delete"
        )
        deleted_lookup = await client.get(
            f"{backend_stack.play.base_url}/sessions/service_stack_delete"
        )
        assert delete_turn.status_code == 200
        assert deleted.status_code == 200
        assert deleted.json()["sessionId"] == "service_stack_delete"
        assert deleted_lookup.status_code == 404

        backend_stack.media.stop()
        media_unavailable = await client.get(
            f"{backend_stack.play.base_url}/sessions/service_stack_main/media/providers"
        )
        chat_survives = await client.post(
            f"{backend_stack.play.base_url}/sessions/service_stack_failure/turn",
            json={"text": "media outage must not block chat"},
        )
        assert media_unavailable.status_code == 503
        assert (
            media_unavailable.json()["detail"]["errorCode"]
            == "MEDIA_SERVICE_UNAVAILABLE"
        )
        assert chat_survives.status_code == 200

        backend_stack.llm.stop()
        llm_unavailable = await client.post(
            f"{backend_stack.play.base_url}/sessions/service_stack_failure/turn",
            json={"text": "llm outage"},
        )
        agent_health = await client.get(f"{backend_stack.agent.base_url}/health")
        assert llm_unavailable.status_code == 503
        assert llm_unavailable.json()["detail"]["errorCode"] == "LLM_SERVICE_UNAVAILABLE"
        assert agent_health.json() == {
            "status": "degraded",
            "llm_service": "unavailable",
        }
