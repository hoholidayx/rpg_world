"""Loop-owned async client for the standalone TTS service."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx

from tts_service.schemas import TTSJobResponse
from tts_service.settings import settings


class TTSClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "TTS_SERVICE_ERROR",
        status_code: int = 503,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


class TTSClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        request_timeout_ms: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        config = settings.tts_client
        self.base_url = (base_url or config.base_url).rstrip("/")
        timeout = request_timeout_ms or config.request_timeout_ms
        self._http = httpx.AsyncClient(
            timeout=max(1, timeout) / 1000.0,
            transport=transport,
        )
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    async def create_job(self, session_id: str, message_id: int) -> TTSJobResponse:
        response = await self._request(
            "POST",
            f"/sessions/{session_id}/messages/{message_id}/jobs",
        )
        return TTSJobResponse.model_validate(response.json())

    async def get_job(self, session_id: str, job_id: str) -> TTSJobResponse:
        response = await self._request("GET", f"/sessions/{session_id}/jobs/{job_id}")
        return TTSJobResponse.model_validate(response.json())

    async def retry_job(self, session_id: str, job_id: str) -> TTSJobResponse:
        response = await self._request("POST", f"/sessions/{session_id}/jobs/{job_id}/retry")
        return TTSJobResponse.model_validate(response.json())

    async def get_audio(
        self,
        session_id: str,
        job_id: str,
        part_index: int,
        *,
        range_header: str | None = None,
    ) -> httpx.Response:
        headers = {"Range": range_header} if range_header else None
        return await self._request(
            "GET",
            f"/sessions/{session_id}/jobs/{job_id}/parts/{part_index}/audio",
            headers=headers,
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._assert_loop()
        self._closed = True
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        self._assert_loop()
        try:
            response = await self._http.request(method, f"{self.base_url}{path}", **kwargs)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise TTSClientError(f"TTS service unavailable: {exc}") from exc
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if isinstance(payload, Mapping) and isinstance(payload.get("detail"), Mapping):
                payload = payload["detail"]
            if not isinstance(payload, Mapping):
                payload = {}
            raise TTSClientError(
                str(payload.get("message") or response.text or "TTS service request failed"),
                error_code=str(payload.get("errorCode") or "TTS_SERVICE_ERROR"),
                status_code=response.status_code,
            )
        return response

    def _assert_loop(self) -> None:
        if self._closed:
            raise RuntimeError("TTS client is closed")
        loop = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = loop
        elif self._owner_loop is not loop:
            raise RuntimeError("TTS client cannot be reused across event loops")
