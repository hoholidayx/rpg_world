"""Loop-owned async HTTP client for the independent Dream service."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TypeVar

import httpx
from pydantic import BaseModel

from dream_service.schemas import (
    DreamMemoryListResponse,
    DreamMemoryResponse,
    DreamProposalListResponse,
    DreamProposalResponse,
    DreamProposalUpdateRequest,
)
from dream_service.settings import settings

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class DreamClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "DREAM_SERVICE_ERROR",
        status_code: int = 503,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


class DreamServiceUnavailable(DreamClientError):
    def __init__(self, message: str = "Dream service unavailable") -> None:
        super().__init__(
            message,
            error_code="DREAM_SERVICE_UNAVAILABLE",
            status_code=503,
        )


class DreamClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        request_timeout_ms: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        config = settings.dream_client
        self.base_url = (base_url or config.base_url).rstrip("/")
        timeout = request_timeout_ms or config.request_timeout_ms
        self._http = httpx.AsyncClient(
            timeout=max(1, timeout) / 1000.0,
            transport=transport,
        )
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    async def create_proposal(
        self,
        session_id: str,
        *,
        depth: str,
        scope: str,
    ) -> DreamProposalResponse:
        response = await self._request(
            "POST",
            f"/sessions/{session_id}/dream/proposals",
            json={"depth": depth, "scope": scope},
        )
        return self._parse_response(response, DreamProposalResponse)

    async def get_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalResponse:
        response = await self._request(
            "GET",
            f"/sessions/{session_id}/dream/proposals/{proposal_id}",
        )
        return self._parse_response(response, DreamProposalResponse)

    async def list_proposals(self, session_id: str) -> DreamProposalListResponse:
        response = await self._request(
            "GET",
            f"/sessions/{session_id}/dream/proposals",
        )
        return self._parse_response(response, DreamProposalListResponse)

    async def update_proposal(
        self,
        session_id: str,
        proposal_id: str,
        request: DreamProposalUpdateRequest,
    ) -> DreamProposalResponse:
        response = await self._request(
            "PATCH",
            f"/sessions/{session_id}/dream/proposals/{proposal_id}",
            json=request.model_dump(by_alias=True, exclude_none=True),
        )
        return self._parse_response(response, DreamProposalResponse)

    async def apply_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalResponse:
        response = await self._request(
            "POST",
            f"/sessions/{session_id}/dream/proposals/{proposal_id}/apply",
        )
        return self._parse_response(response, DreamProposalResponse)

    async def reject_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalResponse:
        response = await self._request(
            "POST",
            f"/sessions/{session_id}/dream/proposals/{proposal_id}/reject",
        )
        return self._parse_response(response, DreamProposalResponse)

    async def list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | None = None,
    ) -> DreamMemoryListResponse:
        params = {"lifecycle": lifecycle} if lifecycle else None
        response = await self._request(
            "GET",
            f"/sessions/{session_id}/dream/memories",
            params=params,
        )
        return self._parse_response(response, DreamMemoryListResponse)

    async def restore_memory(
        self,
        session_id: str,
        memory_id: str,
    ) -> DreamMemoryResponse:
        response = await self._request(
            "POST",
            f"/sessions/{session_id}/dream/memories/{memory_id}/restore",
        )
        return self._parse_response(response, DreamMemoryResponse)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._assert_loop()
        self._closed = True
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        self._assert_loop()
        try:
            response = await self._http.request(
                method,
                f"{self.base_url}{path}",
                **kwargs,
            )
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise DreamServiceUnavailable(f"Dream service unavailable: {exc}") from exc
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if isinstance(payload, Mapping) and isinstance(payload.get("detail"), Mapping):
                payload = payload["detail"]
            if not isinstance(payload, Mapping):
                payload = {}
            raise DreamClientError(
                str(
                    payload.get("message")
                    or response.text
                    or "Dream service request failed"
                ),
                error_code=str(payload.get("errorCode") or "DREAM_SERVICE_ERROR"),
                status_code=response.status_code,
            )
        return response

    @staticmethod
    def _parse_response(
        response: httpx.Response,
        response_model: type[ResponseModelT],
    ) -> ResponseModelT:
        try:
            payload = response.json()
            return response_model.model_validate(payload)
        except (TypeError, ValueError) as exc:
            raise DreamClientError(
                "Dream service returned an invalid response",
                error_code="DREAM_SERVICE_CONTRACT_ERROR",
                status_code=502,
            ) from exc

    def _assert_loop(self) -> None:
        if self._closed:
            raise RuntimeError("Dream client is closed")
        loop = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = loop
        elif self._owner_loop is not loop:
            raise RuntimeError("Dream client cannot be reused across event loops")
