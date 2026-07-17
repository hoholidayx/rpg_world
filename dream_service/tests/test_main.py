from __future__ import annotations

import httpx

from dream_service.contracts import DreamProposalListView, DreamProposalView
from dream_service.main import DreamRuntime, app, set_runtime_for_tests
from rp_memory.dream.errors import DreamAlreadyRunningError


def _proposal(proposal_id: str, *, status: str = "generating") -> DreamProposalView:
    return DreamProposalView(
        proposal_id=proposal_id,
        session_id="s1",
        depth="shallow",
        scope="incremental",
        status=status,
        ledger_revision=0,
        items=(),
        error_code="",
        error_message="",
        created_at="2026-01-01",
        updated_at="2026-01-01",
        finished_at="",
    )


class _Repository:
    def __init__(self, *, get_error: Exception | None = None) -> None:
        self.get_error = get_error

    def list_proposals(self, session_id: str) -> DreamProposalListView:
        assert session_id == "s1"
        return DreamProposalListView((_proposal("new"), _proposal("old", status="interrupted")))

    def get_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView | None:
        assert session_id == "s1"
        assert proposal_id == "new"
        if self.get_error is not None:
            raise self.get_error
        return _proposal(proposal_id)


class _Tasks:
    def __init__(self, *, conflict: bool = False) -> None:
        self.conflict = conflict

    async def create_proposal(self, session_id, *, depth, scope):  # noqa: ANN001, ANN202
        assert session_id == "s1"
        if self.conflict:
            raise DreamAlreadyRunningError("already running")
        return _proposal("new")


async def test_http_create_and_recoverable_proposal_list_contract() -> None:
    runtime = DreamRuntime(
        repository=_Repository(),  # type: ignore[arg-type]
        tasks=_Tasks(),  # type: ignore[arg-type]
    )
    set_runtime_for_tests(runtime)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://dream.test",
        ) as client:
            created = await client.post(
                "/dream/v1/sessions/s1/dream/proposals",
                json={"depth": "shallow", "scope": "incremental"},
            )
            listed = await client.get("/dream/v1/sessions/s1/dream/proposals")
        assert created.status_code == 202
        assert created.json()["proposalId"] == "new"
        assert [item["proposalId"] for item in listed.json()["items"]] == [
            "new",
            "old",
        ]
    finally:
        set_runtime_for_tests(None)


async def test_http_conflict_has_stable_business_error() -> None:
    runtime = DreamRuntime(
        repository=_Repository(),  # type: ignore[arg-type]
        tasks=_Tasks(conflict=True),  # type: ignore[arg-type]
    )
    set_runtime_for_tests(runtime)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://dream.test",
        ) as client:
            response = await client.post(
                "/dream/v1/sessions/s1/dream/proposals",
                json={"depth": "deep", "scope": "full"},
            )
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "errorCode": "DREAM_ALREADY_RUNNING",
            "message": "already running",
        }
    finally:
        set_runtime_for_tests(None)


async def test_http_get_proposal_maps_repository_failure() -> None:
    runtime = DreamRuntime(
        repository=_Repository(  # type: ignore[arg-type]
            get_error=RuntimeError("database unavailable")
        ),
        tasks=_Tasks(),  # type: ignore[arg-type]
    )
    set_runtime_for_tests(runtime)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://dream.test",
        ) as client:
            response = await client.get(
                "/dream/v1/sessions/s1/dream/proposals/new"
            )
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "errorCode": "DREAM_SERVICE_UNAVAILABLE",
            "message": "database unavailable",
        }
    finally:
        set_runtime_for_tests(None)
