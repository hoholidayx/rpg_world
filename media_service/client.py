"""Async client used by Play API to access the independent media service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel

from media_service.schemas import (
    MediaAssetDeleteResponse,
    MediaBackgroundResponse,
    MediaBackgroundSetRequest,
    MediaBriefRequest,
    MediaBriefResponse,
    MediaGalleryItemResponse,
    MediaGalleryResponse,
    MediaJobCreateRequest,
    MediaJobResponse,
    MediaProviderCatalogResponse,
    MediaSourceTurnsResponse,
)
from media_service.settings import settings

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class MediaClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class MediaServiceUnavailable(MediaClientError):
    pass


@dataclass(frozen=True)
class MediaContentStream:
    media_type: str
    content_length: int | None
    chunks: AsyncIterator[bytes]


class MediaClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        request_timeout_ms: int | None = None,
    ) -> None:
        configured = settings.media_client
        self.base_url = (base_url or configured.base_url).rstrip("/")
        self.request_timeout_ms = request_timeout_ms or configured.request_timeout_ms
        self._client: httpx.AsyncClient | None = None

    async def list_providers(self, session_id: str) -> MediaProviderCatalogResponse:
        return await self._get_model(
            f"/sessions/{session_id}/providers",
            MediaProviderCatalogResponse,
        )

    async def list_source_turns(self, session_id: str) -> MediaSourceTurnsResponse:
        return await self._get_model(
            f"/sessions/{session_id}/source-turns",
            MediaSourceTurnsResponse,
        )

    async def create_brief(
        self,
        session_id: str,
        body: MediaBriefRequest,
    ) -> MediaBriefResponse:
        return await self._send_model(
            "POST",
            f"/sessions/{session_id}/briefs",
            MediaBriefResponse,
            body=body,
        )

    async def create_job(
        self,
        session_id: str,
        body: MediaJobCreateRequest,
    ) -> MediaJobResponse:
        return await self._send_model(
            "POST",
            f"/sessions/{session_id}/jobs",
            MediaJobResponse,
            body=body,
        )

    async def get_job(self, session_id: str, job_id: str) -> MediaJobResponse:
        return await self._get_model(
            f"/sessions/{session_id}/jobs/{job_id}",
            MediaJobResponse,
        )

    async def cancel_job(self, session_id: str, job_id: str) -> MediaJobResponse:
        return await self._send_model(
            "POST",
            f"/sessions/{session_id}/jobs/{job_id}/cancel",
            MediaJobResponse,
        )

    async def retry_job(self, session_id: str, job_id: str) -> MediaJobResponse:
        return await self._send_model(
            "POST",
            f"/sessions/{session_id}/jobs/{job_id}/retry",
            MediaJobResponse,
        )

    async def get_gallery(self, session_id: str) -> MediaGalleryResponse:
        return await self._get_model(
            f"/sessions/{session_id}/gallery",
            MediaGalleryResponse,
        )

    async def get_background(self, session_id: str) -> MediaBackgroundResponse:
        return await self._get_model(
            f"/sessions/{session_id}/background",
            MediaBackgroundResponse,
        )

    async def set_background(
        self,
        session_id: str,
        body: MediaBackgroundSetRequest,
    ) -> MediaBackgroundResponse:
        return await self._send_model(
            "PUT",
            f"/sessions/{session_id}/background",
            MediaBackgroundResponse,
            body=body,
        )

    async def clear_background(self, session_id: str) -> MediaBackgroundResponse:
        return await self._send_model(
            "DELETE",
            f"/sessions/{session_id}/background",
            MediaBackgroundResponse,
        )

    async def get_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> MediaGalleryItemResponse:
        return await self._get_model(
            f"/sessions/{session_id}/assets/{asset_id}",
            MediaGalleryItemResponse,
        )

    async def delete_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> MediaAssetDeleteResponse:
        return await self._send_model(
            "DELETE",
            f"/sessions/{session_id}/assets/{asset_id}",
            MediaAssetDeleteResponse,
        )

    async def stream_asset_content(
        self,
        session_id: str,
        asset_id: str,
    ) -> MediaContentStream:
        client = self._http_client()
        request = client.build_request(
            "GET",
            self._url(f"/sessions/{session_id}/assets/{asset_id}/content"),
        )
        try:
            response = await client.send(request, stream=True)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise MediaServiceUnavailable(f"Media service unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            await exc.response.aread()
            await exc.response.aclose()
            raise _client_http_error(exc.response) from exc
        except httpx.HTTPError as exc:
            raise MediaClientError(str(exc)) from exc

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
            finally:
                await response.aclose()

        length_header = response.headers.get("content-length")
        try:
            content_length = int(length_header) if length_header else None
        except ValueError:
            content_length = None
        return MediaContentStream(
            media_type=response.headers.get("content-type", "application/octet-stream"),
            content_length=content_length,
            chunks=chunks(),
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_model(
        self,
        path: str,
        response_model: type[ResponseT],
    ) -> ResponseT:
        return await self._send_model("GET", path, response_model)

    async def _send_model(
        self,
        method: str,
        path: str,
        response_model: type[ResponseT],
        *,
        body: BaseModel | None = None,
    ) -> ResponseT:
        try:
            response = await self._http_client().request(
                method,
                self._url(path),
                json=(
                    body.model_dump(mode="json", by_alias=True)
                    if body is not None
                    else None
                ),
            )
            response.raise_for_status()
            return response_model.model_validate(response.json())
        except httpx.ConnectError as exc:
            raise MediaServiceUnavailable(f"Media service unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise _client_http_error(exc.response) from exc
        except httpx.HTTPError as exc:
            raise MediaClientError(str(exc)) from exc

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.request_timeout_ms / 1000),
            )
        return self._client

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"


def _client_http_error(response: httpx.Response) -> MediaClientError:
    message = response.text
    error_code = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            error_code = str(detail.get("errorCode", ""))
            message = str(detail.get("message", message))
        elif detail is not None:
            message = str(detail)
    return MediaClientError(
        message,
        status_code=response.status_code,
        error_code=error_code,
    )
