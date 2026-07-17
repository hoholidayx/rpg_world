from __future__ import annotations

from fastapi.testclient import TestClient

from dream_service.client import DreamClientError, DreamServiceUnavailable
from dream_service.schemas import (
    DreamEvidenceResponse,
    DreamMemoryListResponse,
    DreamMemoryResponse,
    DreamMemoryRevisionResponse,
    DreamProposalItemResponse,
    DreamProposalListResponse,
    DreamProposalResponse,
)
from play_api import dream_client
from play_api.main import app
from rpg_data.services import reset_data_service_gateways


def _proposal(
    status: str = "ready",
    *,
    proposal_id: str = "proposal1",
) -> DreamProposalResponse:
    return DreamProposalResponse(
        proposalId=proposal_id,
        sessionId="s_forest001",
        depth="shallow",
        scope="incremental",
        status=status,
        ledgerRevision=2,
        items=[
            DreamProposalItemResponse(
                itemId="item1",
                action="add",
                selected=True,
                text="夏澄答应在黎明前返回。",
                memoryKind="commitment",
                epistemicStatus="confirmed",
                salience=0.8,
                reason="长期承诺",
                evidence=[
                    DreamEvidenceResponse(
                        messageId=2,
                        turnId=1,
                        messageVersion=1,
                        contentHash="a" * 64,
                    )
                ],
            )
        ],
        createdAt="2026-07-17T01:00:00Z",
        updatedAt="2026-07-17T01:01:00Z",
        finishedAt="2026-07-17T01:01:00Z",
    )


def _memory(lifecycle: str = "retired") -> DreamMemoryResponse:
    revision = DreamMemoryRevisionResponse(
        revisionNumber=1,
        text="夏澄答应在黎明前返回。",
        memoryKind="commitment",
        epistemicStatus="confirmed",
        salience=0.8,
        dedupeKey="b" * 64,
        proposalId="proposal1",
        createdAt="2026-07-17T01:02:00Z",
    )
    return DreamMemoryResponse(
        memoryId="memory1",
        sessionId="s_forest001",
        lifecycle=lifecycle,
        currentRevisionNumber=1,
        evidenceValid=True,
        currentRevision=revision,
        revisions=[revision],
        evidence=[
            DreamEvidenceResponse(
                messageId=2,
                turnId=1,
                messageVersion=1,
                contentHash="a" * 64,
            )
        ],
        createdAt="2026-07-17T01:02:00Z",
        updatedAt="2026-07-17T01:02:00Z",
    )


class _FakeDreamClient:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def aclose(self) -> None:
        self.calls.append(("close",))

    async def create_proposal(self, session_id, *, depth, scope):  # noqa: ANN001, ANN201
        self.calls.append(("create", session_id, depth, scope))
        return _proposal("generating")

    async def get_proposal(self, session_id, proposal_id):  # noqa: ANN001, ANN201
        self.calls.append(("get", session_id, proposal_id))
        return _proposal()

    async def list_proposals(self, session_id):  # noqa: ANN001, ANN201
        self.calls.append(("list-proposals", session_id))
        return DreamProposalListResponse(
            items=[
                _proposal("generating"),
                _proposal("interrupted", proposal_id="proposal2"),
            ]
        )

    async def update_proposal(self, session_id, proposal_id, body):  # noqa: ANN001, ANN201
        self.calls.append(("update", session_id, proposal_id, body))
        assert body.items[0].item_id == "item1"
        assert body.items[0].memory_kind == "clue"
        return _proposal()

    async def apply_proposal(self, session_id, proposal_id):  # noqa: ANN001, ANN201
        self.calls.append(("apply", session_id, proposal_id))
        return _proposal("applied")

    async def reject_proposal(self, session_id, proposal_id):  # noqa: ANN001, ANN201
        self.calls.append(("reject", session_id, proposal_id))
        return _proposal("rejected")

    async def list_memories(self, session_id, *, lifecycle=None):  # noqa: ANN001, ANN201
        self.calls.append(("list", session_id, lifecycle))
        return DreamMemoryListResponse(
            items=[_memory(lifecycle or "retired")],
            activeCount=1,
            activeLimit=64,
        )

    async def restore_memory(self, session_id, memory_id):  # noqa: ANN001, ANN201
        self.calls.append(("restore", session_id, memory_id))
        return _memory("active")


def _prepare(tmp_path, monkeypatch, fake) -> None:  # noqa: ANN001
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "play.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    monkeypatch.setattr(dream_client, "_client", fake)


def test_play_dream_proxy_contract(tmp_path, monkeypatch) -> None:
    fake = _FakeDreamClient()
    _prepare(tmp_path, monkeypatch, fake)

    with TestClient(app) as client:
        created = client.post(
            "/play-api/v1/sessions/s_forest001/dream/proposals",
            json={"depth": "shallow", "scope": "incremental"},
        )
        assert created.status_code == 202
        assert created.json()["proposalId"] == "proposal1"
        assert created.json()["status"] == "generating"

        proposals = client.get(
            "/play-api/v1/sessions/s_forest001/dream/proposals"
        )
        assert proposals.status_code == 200
        assert [item["status"] for item in proposals.json()["items"]] == [
            "generating",
            "interrupted",
        ]
        assert [item["proposalId"] for item in proposals.json()["items"]] == [
            "proposal1",
            "proposal2",
        ]

        proposal = client.get(
            "/play-api/v1/sessions/s_forest001/dream/proposals/proposal1"
        )
        assert proposal.status_code == 200
        assert proposal.json()["items"][0]["evidence"][0]["turnId"] == 1

        updated = client.patch(
            "/play-api/v1/sessions/s_forest001/dream/proposals/proposal1",
            json={
                "items": [
                    {
                        "itemId": "item1",
                        "selected": True,
                        "text": "咖啡馆钥匙藏在旧钟后。",
                        "memoryKind": "clue",
                        "epistemicStatus": "reported",
                        "salience": 0.7,
                    }
                ]
            },
        )
        assert updated.status_code == 200

        applied = client.post(
            "/play-api/v1/sessions/s_forest001/dream/proposals/proposal1/apply"
        )
        assert applied.status_code == 200
        assert applied.json()["status"] == "applied"

        rejected = client.post(
            "/play-api/v1/sessions/s_forest001/dream/proposals/proposal1/reject"
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"

        memories = client.get(
            "/play-api/v1/sessions/s_forest001/dream/memories",
            params={"lifecycle": "retired"},
        )
        assert memories.status_code == 200
        assert memories.json()["activeLimit"] == 64
        assert memories.json()["items"][0]["evidenceValid"] is True

        restored = client.post(
            "/play-api/v1/sessions/s_forest001/dream/memories/memory1/restore"
        )
        assert restored.status_code == 200
        assert restored.json()["lifecycle"] == "active"

    assert ("create", "s_forest001", "shallow", "incremental") in fake.calls
    assert ("list-proposals", "s_forest001") in fake.calls
    assert ("list", "s_forest001", "retired") in fake.calls


class _UnavailableDreamClient(_FakeDreamClient):
    async def list_memories(self, session_id, *, lifecycle=None):  # noqa: ANN001, ANN201
        raise DreamServiceUnavailable("offline")


def test_dream_outage_is_isolated_as_503(tmp_path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch, _UnavailableDreamClient())
    with TestClient(app) as client:
        response = client.get(
            "/play-api/v1/sessions/s_forest001/dream/memories"
        )
        assert response.status_code == 503
        assert response.json()["detail"]["errorCode"] == "DREAM_SERVICE_UNAVAILABLE"


class _StaleDreamClient(_FakeDreamClient):
    async def apply_proposal(self, session_id, proposal_id):  # noqa: ANN001, ANN201
        raise DreamClientError(
            "proposal source changed",
            error_code="DREAM_PROPOSAL_STALE",
            status_code=409,
        )


def test_dream_business_error_is_preserved(tmp_path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch, _StaleDreamClient())
    with TestClient(app) as client:
        response = client.post(
            "/play-api/v1/sessions/s_forest001/dream/proposals/proposal1/apply"
        )
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "errorCode": "DREAM_PROPOSAL_STALE",
            "message": "proposal source changed",
        }


class _ContractErrorDreamClient(_FakeDreamClient):
    async def get_proposal(self, session_id, proposal_id):  # noqa: ANN001, ANN201
        raise DreamClientError(
            "Dream service returned an invalid response",
            error_code="DREAM_SERVICE_CONTRACT_ERROR",
            status_code=502,
        )


def test_dream_contract_error_is_isolated_as_502(tmp_path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch, _ContractErrorDreamClient())
    with TestClient(app) as client:
        response = client.get(
            "/play-api/v1/sessions/s_forest001/dream/proposals/proposal1"
        )
        assert response.status_code == 502
        assert response.json()["detail"] == {
            "errorCode": "DREAM_SERVICE_CONTRACT_ERROR",
            "message": "Dream service returned an invalid response",
        }
