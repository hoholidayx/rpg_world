from __future__ import annotations

from fastapi.testclient import TestClient

from agent_service.client import AgentClientError, AgentServiceUnavailable
from play_api import agent_client
from play_api.main import app
from rpg_data.services import reset_data_service_gateways


def _job_payload(
    *,
    status: str = "queued",
    stage: str = "snapshotting",
) -> dict[str, object]:
    return {
        "job_id": "derive_job_1",
        "source_session_id": "s_forest001",
        "target_session_id": "s_branch001" if status == "ready" else None,
        "branch_turn_id": 7,
        "status": status,
        "stage": stage,
        "error_code": "",
        "error_message": "",
        "context_usage": (
            {
                "usedTokens": 1200,
                "contextLimit": 64000,
                "source": "context_preview",
                "accuracy": "estimated",
            }
            if status == "ready"
            else None
        ),
        "context_threshold_exceeded": False,
        "created_at": "2026-07-17T10:00:00+00:00",
        "started_at": "2026-07-17T10:00:01+00:00" if status == "ready" else "",
        "finished_at": "2026-07-17T10:00:02+00:00" if status == "ready" else "",
        "updated_at": "2026-07-17T10:00:02+00:00",
    }


class _DerivationAgentClient:
    def __init__(self) -> None:
        self.create_calls: list[tuple[str, int, str]] = []
        self.get_calls: list[str] = []

    async def create_session_derivation(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        title: str = "",
    ) -> dict[str, object]:
        self.create_calls.append((source_session_id, branch_turn_id, title))
        return _job_payload()

    async def get_session_derivation(self, job_id: str) -> dict[str, object]:
        self.get_calls.append(job_id)
        return _job_payload(status="ready", stage="ready")


class _RejectingDerivationAgentClient:
    async def create_session_derivation(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        title: str = "",
    ) -> dict[str, object]:
        del source_session_id, branch_turn_id, title
        raise AgentClientError(
            "source session already has an active derivation",
            status_code=409,
            error_code="SESSION_DERIVATION_CONFLICT",
        )


class _MissingDerivationAgentClient:
    async def get_session_derivation(self, job_id: str) -> dict[str, object]:
        del job_id
        raise AgentClientError("derivation job not found", status_code=404)


class _UnavailableDerivationAgentClient:
    async def get_session_derivation(self, job_id: str) -> dict[str, object]:
        del job_id
        raise AgentServiceUnavailable("Agent service unavailable: connection refused")


def _configure_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()


def test_create_and_get_session_derivation_contract(tmp_path, monkeypatch) -> None:
    _configure_data(tmp_path, monkeypatch)
    fake_agent = _DerivationAgentClient()
    monkeypatch.setattr(agent_client, "_client", fake_agent)

    with TestClient(app) as client:
        created = client.post(
            "/play-api/v1/sessions/s_forest001/derivations",
            json={"turnId": 7, "title": "岔路：钟楼"},
        )
        fetched = client.get(
            "/play-api/v1/session-derivations/derive_job_1"
        )

    assert created.status_code == 202
    assert created.json() == {
        "jobId": "derive_job_1",
        "sourceSessionId": "s_forest001",
        "targetSessionId": None,
        "turnId": 7,
        "status": "queued",
        "stage": "snapshotting",
        "errorCode": "",
        "errorMessage": "",
        "contextUsage": None,
        "contextThresholdExceeded": False,
        "createdAt": "2026-07-17T10:00:00+00:00",
        "startedAt": "",
        "finishedAt": "",
        "updatedAt": "2026-07-17T10:00:02+00:00",
    }
    assert fake_agent.create_calls == [("s_forest001", 7, "岔路：钟楼")]

    assert fetched.status_code == 200
    assert fetched.json()["targetSessionId"] == "s_branch001"
    assert fetched.json()["status"] == "ready"
    assert fetched.json()["contextUsage"] == {
        "usedTokens": 1200,
        "contextLimit": 64000,
        "source": "context_preview",
        "accuracy": "estimated",
    }
    assert "target_session_id" not in fetched.json()
    assert fake_agent.get_calls == ["derive_job_1"]


def test_create_session_derivation_validates_turn_id(
    tmp_path,
    monkeypatch,
) -> None:
    _configure_data(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_client, "_client", _DerivationAgentClient())

    with TestClient(app) as client:
        missing = client.post(
            "/play-api/v1/sessions/s_forest001/derivations",
            json={},
        )
        non_positive = client.post(
            "/play-api/v1/sessions/s_forest001/derivations",
            json={"turnId": 0},
        )
        extra_field = client.post(
            "/play-api/v1/sessions/s_forest001/derivations",
            json={"turnId": 7, "unexpected": True},
        )

    assert missing.status_code == 422
    assert non_positive.status_code == 422
    assert extra_field.status_code == 422


def test_create_session_derivation_preserves_agent_conflict(
    tmp_path,
    monkeypatch,
) -> None:
    _configure_data(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_client, "_client", _RejectingDerivationAgentClient())

    with TestClient(app) as client:
        response = client.post(
            "/play-api/v1/sessions/s_forest001/derivations",
            json={"turnId": 7},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "errorCode": "SESSION_DERIVATION_CONFLICT",
        "message": "source session already has an active derivation",
    }


def test_get_session_derivation_maps_agent_errors(tmp_path, monkeypatch) -> None:
    _configure_data(tmp_path, monkeypatch)

    monkeypatch.setattr(agent_client, "_client", _MissingDerivationAgentClient())
    with TestClient(app) as client:
        missing = client.get(
            "/play-api/v1/session-derivations/missing_job"
        )

    monkeypatch.setattr(agent_client, "_client", _UnavailableDerivationAgentClient())
    with TestClient(app) as client:
        unavailable = client.get(
            "/play-api/v1/session-derivations/derive_job_1"
        )

    assert missing.status_code == 404
    assert missing.json()["detail"] == "derivation job not found"
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == (
        "Agent service unavailable: connection refused"
    )
