from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from dream_service.client import DreamClient, DreamClientError, DreamServiceUnavailable
from dream_service.schemas import (
    DreamProposalItemUpdateRequest,
    DreamProposalUpdateRequest,
)


def _proposal() -> dict[str, object]:
    return {
        "proposalId": "p1",
        "sessionId": "s1",
        "depth": "shallow",
        "scope": "incremental",
        "status": "generating",
        "ledgerRevision": 0,
        "items": [],
        "errorCode": "",
        "errorMessage": "",
        "createdAt": "",
        "updatedAt": "",
        "finishedAt": "",
    }


async def test_client_proposal_contract_and_patch_aliases() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"items": [_proposal()]})
        return httpx.Response(200, json=_proposal())

    client = DreamClient(
        base_url="http://dream.test/dream/v1",
        transport=httpx.MockTransport(handler),
    )
    created = await client.create_proposal(
        "s1",
        depth="shallow",
        scope="incremental",
        recover_proposal_id="orphan",
    )
    await client.update_proposal(
        "s1",
        "p1",
        DreamProposalUpdateRequest(
            items=[
                DreamProposalItemUpdateRequest(
                    itemId="i1",
                    memoryKind="clue",
                    selected=True,
                )
            ]
        ),
    )
    listed = await client.list_proposals("s1")
    assert created.proposal_id == "p1"
    assert listed.items[0].proposal_id == "p1"
    assert requests[0].url.path.endswith("/sessions/s1/dream/proposals")
    assert requests[0].content == (
        b'{"depth":"shallow","scope":"incremental",'
        b'"recoverProposalId":"orphan"}'
    )
    assert requests[1].content == b'{"items":[{"itemId":"i1","selected":true,"memoryKind":"clue"}]}'
    assert requests[2].url.path.endswith("/sessions/s1/dream/proposals")
    await client.aclose()


async def test_client_preserves_remote_error() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "detail": {
                    "errorCode": "DREAM_PROPOSAL_STALE",
                    "message": "changed",
                }
            },
        )

    client = DreamClient(
        base_url="http://dream.test/dream/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DreamClientError) as caught:
        await client.apply_proposal("s1", "p1")
    assert caught.value.error_code == "DREAM_PROPOSAL_STALE"
    assert caught.value.status_code == 409
    await client.aclose()


async def test_client_maps_transport_failure_to_unavailable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = DreamClient(
        base_url="http://dream.test/dream/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DreamServiceUnavailable) as caught:
        await client.get_proposal("s1", "p1")
    assert caught.value.error_code == "DREAM_SERVICE_UNAVAILABLE"
    assert caught.value.status_code == 503
    await client.aclose()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"proposalId": "p1"}),
    ],
)
async def test_client_maps_invalid_success_response_to_contract_error(
    response: httpx.Response,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return response

    client = DreamClient(
        base_url="http://dream.test/dream/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DreamClientError) as caught:
        await client.get_proposal("s1", "p1")
    assert caught.value.error_code == "DREAM_SERVICE_CONTRACT_ERROR"
    assert caught.value.status_code == 502
    assert str(caught.value) == "Dream service returned an invalid response"
    await client.aclose()


def test_patch_schema_rejects_oversize_fact_text() -> None:
    with pytest.raises(ValidationError):
        DreamProposalItemUpdateRequest(itemId="i1", text="x" * 1001)
