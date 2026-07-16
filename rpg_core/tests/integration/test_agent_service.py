from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import pytest_asyncio

from agent_service import main as service_main
from llm_client.keys import AGENT_MAIN_BIZ_KEY
from llm_client.types import ProviderChunk
from rpg_core.agent.manager import AgentManager
from rpg_core.tests.integration.conftest import (
    _create_integration_session,
    _shutdown_agent,
)
from rpg_core.tests.integration.scripted_llm import (
    CONFIG_PROVIDER_KEY,
    SESSION_PROVIDER_KEY,
    STORY_PROVIDER_KEY,
    scripted_usage,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def agent_service_client(
    integration_settings,  # noqa: ARG001
    integration_workspace,  # noqa: ARG001
    integration_data_gateway,  # noqa: ARG001
    scripted_llm_manager,  # noqa: ARG001
    monkeypatch,
):
    await AgentManager.areset()
    async with service_main.app.router.lifespan_context(service_main.app):
        transport = httpx.ASGITransport(app=service_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent.test") as client:
            try:
                yield client
            finally:
                for agent in list(AgentManager._instances.values()):
                    await _shutdown_agent(agent)


def _sse_events(response: httpx.Response) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.mark.asyncio
async def test_agent_service_send_history_and_context_preview_use_real_runtime(
    agent_service_client,
    integration_workspace,
    integration_data_gateway,
):
    session_id = "service_send"
    _create_integration_session(integration_data_gateway, integration_workspace, session_id)

    sent = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "hello service"},
    )
    persisted = integration_data_gateway.messages.list(session_id)
    integration_data_gateway.messages.mark_summary_processed(
        session_id,
        [next(row.id for row in persisted if row.role == "user")],
        batch_id=404,
    )
    history = await agent_service_client.get(
        "/agent/v1/chat/history",
        params={"session_id": session_id},
    )
    preview = await agent_service_client.get(
        "/agent/v1/chat/context-preview",
        params={"session_id": session_id},
    )

    assert sent.status_code == 200
    assert sent.json()["reply"] == "config-model response"
    # Narrative Outcome preflight makes the normal path two LLM calls:
    # StatusSubAgent decision + main Agent narration.
    assert sent.json()["usage"]["total_tokens"] == 36
    assert history.status_code == 200
    assert [(row["role"], row["content"], row["turnId"], row["seqInTurn"]) for row in history.json()["history"]] == [
        ("user", "hello service", 1, 1),
        ("assistant", "config-model response", 1, 2),
    ]
    assert preview.status_code == 200
    assert preview.json()["sessionId"] == session_id
    assert preview.json()["usageEstimate"]["contextLimit"] == 128_000
    preview_contents = [row["content"] for row in preview.json()["messages"]]
    assert all("hello service" not in content for content in preview_contents)
    assert "config-model response" in preview_contents


@pytest.mark.asyncio
async def test_agent_service_stream_success_and_failure_preserve_transaction_semantics(
    agent_service_client,
    integration_workspace,
    integration_data_gateway,
    scripted_llm_manager,
):
    success_id = "service_stream_ok"
    failure_id = "service_stream_fail"
    _create_integration_session(integration_data_gateway, integration_workspace, success_id)
    _create_integration_session(integration_data_gateway, integration_workspace, failure_id)

    success = await agent_service_client.post(
        "/agent/v1/chat/stream",
        json={"session_id": success_id, "message": "stream hello", "request_id": "req_ok"},
    )
    success_events = _sse_events(success)

    assert success.status_code == 200
    assert [event["kind"] for event in success_events] == [
        "round_start",
        "text",
        "round_end",
        "done",
    ]
    assert success_events[-1]["content"] == "config-model streamed"
    assert success_events[-1]["usage"]["total_tokens"] == 36
    assert integration_data_gateway.messages.count(success_id) == 2
    assert integration_data_gateway.backup.messages.count(success_id) == 2

    scripted_llm_manager.main_provider().queue_stream(RuntimeError("service stream failed"))
    failed = await agent_service_client.post(
        "/agent/v1/chat/stream",
        json={"session_id": failure_id, "message": "must rollback", "request_id": "req_fail"},
    )
    failed_events = _sse_events(failed)

    assert [event["kind"] for event in failed_events] == ["round_start", "error"]
    assert failed_events[-1]["content"] == "service stream failed"
    assert integration_data_gateway.messages.count(failure_id) == 0
    assert integration_data_gateway.backup.messages.count(failure_id) == 0


@pytest.mark.asyncio
async def test_agent_service_stop_uses_request_id_and_discards_active_stream(
    agent_service_client,
    integration_workspace,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "service_stop"
    _create_integration_session(integration_data_gateway, integration_workspace, session_id)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocking_stream(_messages, _tools):  # noqa: ANN001, ANN202
        entered.set()
        await release.wait()
        return (
            ProviderChunk(content="partial"),
            ProviderChunk(
                finish_reason="stop",
                usage=scripted_usage(),
                model="config-model",
            ),
        )

    scripted_llm_manager.main_provider().queue_stream(blocking_stream)
    stream_task = asyncio.create_task(
        agent_service_client.post(
            "/agent/v1/chat/stream",
            json={
                "session_id": session_id,
                "message": "wait for stop",
                "request_id": "req_active",
            },
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    queued_task = asyncio.create_task(
        agent_service_client.post(
            "/agent/v1/chat/stream",
            json={
                "session_id": session_id,
                "message": "queued behind active",
                "request_id": "req_queued",
            },
        )
    )
    await asyncio.sleep(0)

    queued_cancelled = None
    for _ in range(100):
        candidate = await agent_service_client.post(
            "/agent/v1/chat/stop",
            json={"session_id": session_id, "request_id": "req_queued"},
        )
        if candidate.json()["status"] == "cancelled":
            queued_cancelled = candidate
            break
        await asyncio.sleep(0)
    assert queued_cancelled is not None
    stale = await agent_service_client.post(
        "/agent/v1/chat/stop",
        json={"session_id": session_id, "request_id": "req_stale"},
    )
    cancelled = await agent_service_client.post(
        "/agent/v1/chat/stop",
        json={"session_id": session_id, "request_id": "req_active"},
    )
    streamed = await asyncio.wait_for(stream_task, timeout=2)
    queued_streamed = await asyncio.wait_for(queued_task, timeout=2)
    not_running = await agent_service_client.post(
        "/agent/v1/chat/stop",
        json={"session_id": session_id, "request_id": "req_active"},
    )

    assert queued_cancelled.json() == {
        "status": "cancelled",
        "session_id": session_id,
        "request_id": "req_queued",
    }
    assert stale.json()["status"] == "stale"
    assert cancelled.json() == {
        "status": "cancelled",
        "session_id": session_id,
        "request_id": "req_active",
    }
    assert not_running.json()["status"] == "not_running"
    assert all(event["kind"] != "done" for event in _sse_events(streamed))
    assert _sse_events(queued_streamed) == []
    assert integration_data_gateway.messages.count(session_id) == 0
    assert integration_data_gateway.backup.messages.count(session_id) == 0


@pytest.mark.asyncio
async def test_agent_service_delete_closes_active_and_queued_turns_before_data_removal(
    agent_service_client,
    integration_workspace,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "service_delete_busy"
    _create_integration_session(integration_data_gateway, integration_workspace, session_id)
    runtime_dir = integration_data_gateway.catalog.get_session_runtime_dir(session_id)
    marker = runtime_dir / "delete-marker.bin"
    marker.write_bytes(b"delete")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocking_stream(_messages, _tools):  # noqa: ANN001, ANN202
        entered.set()
        await release.wait()
        return (
            ProviderChunk(content="must not commit"),
            ProviderChunk(finish_reason="stop", usage=scripted_usage()),
        )

    scripted_llm_manager.main_provider().queue_stream(blocking_stream)
    active_task = asyncio.create_task(
        agent_service_client.post(
            "/agent/v1/chat/stream",
            json={
                "session_id": session_id,
                "message": "active",
                "request_id": "req_delete_active",
            },
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    queued_task = asyncio.create_task(
        agent_service_client.post(
            "/agent/v1/chat/stream",
            json={
                "session_id": session_id,
                "message": "queued",
                "request_id": "req_delete_queued",
            },
        )
    )
    await asyncio.sleep(0)

    deleted = await agent_service_client.delete(
        "/agent/v1/chat/session",
        params={"session_id": session_id},
    )
    active_response, queued_response = await asyncio.wait_for(
        asyncio.gather(active_task, queued_task),
        timeout=2,
    )

    assert deleted.status_code == 200
    assert deleted.json() == {
        "status": "deleted",
        "session_id": session_id,
        "runtime_cleanup": "deleted",
    }
    assert all(event["kind"] != "done" for event in _sse_events(active_response))
    assert all(event["kind"] != "done" for event in _sse_events(queued_response))
    assert integration_data_gateway.catalog.get_session(session_id) is None
    assert session_id not in AgentManager._instances
    assert not runtime_dir.exists()

    missing = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "after delete"},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_agent_service_delete_failure_restores_runtime_and_allows_recreation(
    agent_service_client,
    integration_workspace,
    integration_data_gateway,
    monkeypatch,
):
    session_id = "service_delete_rollback"
    _create_integration_session(integration_data_gateway, integration_workspace, session_id)
    first = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "keep me"},
    )
    assert first.status_code == 200
    runtime_dir = integration_data_gateway.catalog.get_session_runtime_dir(session_id)
    marker = runtime_dir / "keep-marker.bin"
    marker.write_bytes(b"keep")

    def fail_delete(_session_id: str) -> bool:
        raise RuntimeError("database delete failed")

    monkeypatch.setattr(
        integration_data_gateway.session_deletion._sessions,
        "delete",
        fail_delete,
    )
    failed = await agent_service_client.delete(
        "/agent/v1/chat/session",
        params={"session_id": session_id},
    )

    assert failed.status_code == 500
    assert "database delete failed" in failed.json()["detail"]
    assert integration_data_gateway.catalog.get_session(session_id) is not None
    assert marker.read_bytes() == b"keep"
    assert session_id not in AgentManager._instances

    followup = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "still usable"},
    )
    assert followup.status_code == 200
    assert integration_data_gateway.messages.latest_turn_id(session_id) == 2


@pytest.mark.asyncio
async def test_agent_service_non_stream_failure_maps_error_without_writes(
    agent_service_client,
    integration_workspace,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "service_send_fail"
    _create_integration_session(integration_data_gateway, integration_workspace, session_id)
    scripted_llm_manager.main_provider().queue_chat(RuntimeError("service send failed"))

    failed = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "must rollback"},
    )

    assert failed.status_code == 400
    assert "service send failed" in failed.json()["detail"]
    assert integration_data_gateway.messages.count(session_id) == 0
    assert integration_data_gateway.backup.messages.count(session_id) == 0


@pytest.mark.asyncio
async def test_agent_service_player_character_binding_uses_command_path(
    agent_service_client,
    integration_workspace,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "service_role"
    catalog = _create_integration_session(
        integration_data_gateway,
        integration_workspace,
        session_id,
        bind_role=False,
        first_message="Agent Service 开场。",
    )

    blocked = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "blocked"},
    )
    bound = await agent_service_client.post(
        "/agent/v1/chat/session/player-character",
        json={"session_id": session_id, "player_character_id": catalog.character.id},
    )
    sent = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "continue"},
    )

    assert blocked.status_code == 200
    assert "请选择你要扮演的角色" in blocked.json()["reply"]
    assert bound.status_code == 200 and bound.json()["status"] == "bound"
    assert sent.status_code == 200 and sent.json()["reply"] == "config-model response"
    assert len(scripted_llm_manager.main_provider().calls) == 1
    rows = integration_data_gateway.messages.list(session_id)
    assert [(row.role, row.content) for row in rows] == [
        ("assistant", "Agent Service 开场。"),
        ("user", "continue"),
        ("assistant", "config-model response"),
    ]
    assert integration_data_gateway.backup.messages.count(session_id) == 3


@pytest.mark.asyncio
async def test_agent_service_truncate_updates_cached_agent_and_keeps_backup(
    agent_service_client,
    integration_workspace,
    integration_data_gateway,
):
    session_id = "service_truncate"
    _create_integration_session(integration_data_gateway, integration_workspace, session_id)
    for message in ("turn one", "turn two"):
        response = await agent_service_client.post(
            "/agent/v1/chat/send",
            json={"session_id": session_id, "message": message},
        )
        assert response.status_code == 200

    truncated = await agent_service_client.post(
        "/agent/v1/chat/session/turns/2/truncate",
        json={"session_id": session_id},
    )
    history = await agent_service_client.get(
        "/agent/v1/chat/history",
        params={"session_id": session_id},
    )

    assert truncated.status_code == 200
    assert truncated.json()["removed"] == 2
    assert truncated.json()["agent_sync_status"] == "synced"
    assert [row["turnId"] for row in history.json()["history"]] == [1, 1]
    assert [message.turn_id for message in AgentManager._instances[session_id].history] == [1, 1]
    assert integration_data_gateway.backup.messages.count(session_id) == 4


@pytest.mark.asyncio
async def test_agent_service_main_llm_endpoints_change_provider_used_by_next_send(
    agent_service_client,
    integration_workspace,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "service_llm"
    catalog = _create_integration_session(
        integration_data_gateway,
        integration_workspace,
        session_id,
    )

    options = await agent_service_client.get("/agent/v1/chat/main-llm/options")
    first = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "config"},
    )
    story = await agent_service_client.post(
        "/agent/v1/chat/main-llm/story",
        json={
            "workspace_id": catalog.workspace_id,
            "story_id": catalog.story.id,
            "provider_key": STORY_PROVIDER_KEY,
        },
    )
    second = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "story"},
    )
    session = await agent_service_client.post(
        "/agent/v1/chat/main-llm/session",
        json={"session_id": session_id, "provider_key": SESSION_PROVIDER_KEY},
    )
    third = await agent_service_client.post(
        "/agent/v1/chat/send",
        json={"session_id": session_id, "message": "session"},
    )

    assert options.status_code == 200
    assert options.json()["config_default_provider_key"] == CONFIG_PROVIDER_KEY
    assert [item["provider_key"] for item in options.json()["options"]] == [
        CONFIG_PROVIDER_KEY,
        STORY_PROVIDER_KEY,
        SESSION_PROVIDER_KEY,
    ]
    assert first.json()["reply"] == "config-model response"
    assert story.json()["effective_source"] == "story"
    assert second.json()["reply"] == "story-model response"
    assert session.json()["effective_source"] == "session"
    assert third.json()["reply"] == "session-model response"
    assert [
        call.provider_key
        for call in scripted_llm_manager.calls
        if call.biz_key == AGENT_MAIN_BIZ_KEY
    ] == [CONFIG_PROVIDER_KEY, STORY_PROVIDER_KEY, SESSION_PROVIDER_KEY]
