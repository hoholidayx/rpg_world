from __future__ import annotations

from fastapi.testclient import TestClient

from agent_service.client import AgentClientError, AgentServiceUnavailable
from play_api import agent_client
from play_api.main import app


class _FailingHistoryClient:
    async def get_history(self, session_id: str) -> dict[str, object]:
        raise AgentClientError("Agent service returned HTTP 502")


class _UnavailableHistoryClient:
    async def get_history(self, session_id: str) -> dict[str, object]:
        raise AgentServiceUnavailable("Agent service unavailable: connection refused")


class _UnavailableSendClient:
    async def send(self, session_id: str, text: str) -> dict[str, object]:
        raise AgentServiceUnavailable("Agent service unavailable: connection refused")


class _FailingStreamClient:
    async def stream(self, session_id: str, text: str):
        if False:
            yield None
        raise AgentClientError("stream failed")


def test_history_maps_agent_client_error_to_bad_gateway(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    monkeypatch.setattr(agent_client, "_client", _FailingHistoryClient())

    with TestClient(app) as client:
        response = client.get("/play-api/v1/sessions/s_forest001/history")

    assert response.status_code == 502
    assert response.json()["detail"] == "Agent service returned HTTP 502"


def test_history_maps_agent_unavailable_to_service_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    monkeypatch.setattr(agent_client, "_client", _UnavailableHistoryClient())

    with TestClient(app) as client:
        response = client.get("/play-api/v1/sessions/s_forest001/history")

    assert response.status_code == 503
    assert response.json()["detail"] == "Agent service unavailable: connection refused"


def test_turn_maps_agent_unavailable_to_service_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    monkeypatch.setattr(agent_client, "_client", _UnavailableSendClient())

    with TestClient(app) as client:
        response = client.post(
            "/play-api/v1/sessions/s_forest001/turn",
            json={"text": "hello"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Agent service unavailable: connection refused"


def test_stream_maps_agent_client_error_to_sse_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    monkeypatch.setattr(agent_client, "_client", _FailingStreamClient())

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/play-api/v1/sessions/s_forest001/stream",
            json={"text": "hello"},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"kind": "error"' in body
    assert "stream failed" in body
