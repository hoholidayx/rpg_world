"""Async HTTP transport for the standalone LLM service."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping

import httpx

from llm_client.codec import catalog_from_wire, chunk_from_wire, response_from_wire, scores_from_wire
from llm_client.types import (
    DocumentScore,
    LLMBizCatalog,
    LLMResponse,
    LLMSpeechAudio,
    LLMSpeechProfile,
    ProviderChunk,
)


class LLMServiceClientError(Exception):
    """Base error raised by the LLM service client."""


class LLMServiceUnavailable(LLMServiceClientError):
    """The LLM service could not be reached."""


class LLMServiceTimeout(LLMServiceClientError):
    """The LLM service did not complete before the configured timeout."""


class LLMServiceAuthError(LLMServiceClientError):
    """The LLM service rejected the bearer token."""


class LLMServiceRemoteError(LLMServiceClientError):
    """The LLM service returned a structured business or provider error."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "LLM_SERVICE_ERROR",
        status_code: int = 502,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.request_id = request_id


class LLMServiceClient:
    """Loop-owned async client used by Agent, memory, media, and TTS callers."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        request_timeout_ms: int = 60000,
        stream_timeout_ms: int = 300000,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token.strip()
        self.request_timeout_ms = max(1, int(request_timeout_ms))
        self.stream_timeout_ms = max(1, int(stream_timeout_ms))
        self._async = httpx.AsyncClient(
            timeout=self.request_timeout_ms / 1000.0,
            transport=async_transport,
        )
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    async def health(self) -> dict[str, object]:
        """Probe process/config health; this endpoint intentionally has no auth."""
        self._assert_loop()
        try:
            response = await self._async.get(f"{self.base_url}/health")
        except httpx.TimeoutException as exc:
            raise LLMServiceTimeout("LLM health request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMServiceUnavailable(f"LLM service unavailable: {exc}") from exc
        self._raise_for_status(response)
        payload = response.json()
        return dict(payload) if isinstance(payload, Mapping) else {}

    async def get_catalog(self, biz_key: str) -> LLMBizCatalog:
        response = await self._request_async("GET", f"/catalog/{biz_key}")
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise LLMServiceRemoteError("invalid LLM catalog response")
        return catalog_from_wire(payload)

    async def chat(
        self,
        *,
        biz_key: str,
        provider_key: str | None,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> LLMResponse:
        response = await self._request_async(
            "POST",
            "/chat",
            json=self._inference_payload(
                biz_key=biz_key,
                provider_key=provider_key,
                messages=messages,
                tools=tools,
            ),
        )
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise LLMServiceRemoteError("invalid LLM chat response")
        return response_from_wire(payload)

    async def chat_stream(
        self,
        *,
        biz_key: str,
        provider_key: str | None,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> AsyncIterator[ProviderChunk]:
        self._assert_loop()
        timeout = httpx.Timeout(self.stream_timeout_ms / 1000.0)
        try:
            async with self._async.stream(
                "POST",
                f"{self.base_url}/chat/stream",
                headers=self._headers(),
                json=self._inference_payload(
                    biz_key=biz_key,
                    provider_key=provider_key,
                    messages=messages,
                    tools=tools,
                ),
                timeout=timeout,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    self._raise_for_status(response)
                completed = False
                async for event, data in _iter_sse(response):
                    if event == "chunk":
                        if not isinstance(data, Mapping):
                            raise LLMServiceRemoteError("invalid LLM stream chunk")
                        yield chunk_from_wire(data)
                    elif event == "done":
                        completed = True
                        break
                    elif event == "error":
                        raise _remote_error_from_payload(data)
                if not completed:
                    raise LLMServiceRemoteError(
                        "LLM stream ended without done event",
                        error_code="LLM_STREAM_INCOMPLETE",
                    )
        except LLMServiceClientError:
            raise
        except httpx.TimeoutException as exc:
            raise LLMServiceTimeout("LLM stream timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMServiceUnavailable(f"LLM service unavailable: {exc}") from exc

    async def embed(
        self,
        *,
        biz_key: str,
        provider_key: str | None,
        texts: list[str],
    ) -> list[list[float]]:
        response = await self._request_async(
            "POST",
            "/embeddings",
            json={"bizKey": biz_key, "providerKey": provider_key, "texts": texts},
        )
        payload = response.json()
        if not isinstance(payload, Mapping) or not isinstance(payload.get("vectors"), list):
            raise LLMServiceRemoteError("invalid LLM embeddings response")
        return [list(map(float, vector)) for vector in payload["vectors"]]

    async def embedding_dimension(
        self,
        *,
        biz_key: str,
        provider_key: str | None,
    ) -> int:
        params = {"bizKey": biz_key}
        if provider_key is not None:
            params["providerKey"] = provider_key
        response = await self._request_async("GET", "/embeddings/dimension", params=params)
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise LLMServiceRemoteError("invalid LLM embedding dimension response")
        return int(payload.get("dimension", 0) or 0)

    async def rerank(
        self,
        *,
        biz_key: str,
        provider_key: str | None,
        query: str,
        documents: list[str],
    ) -> list[DocumentScore]:
        response = await self._request_async(
            "POST",
            "/rerank",
            json={
                "bizKey": biz_key,
                "providerKey": provider_key,
                "query": query,
                "documents": documents,
            },
        )
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise LLMServiceRemoteError("invalid LLM rerank response")
        return scores_from_wire(payload.get("scores"))

    async def get_speech_profile(self, biz_key: str) -> LLMSpeechProfile:
        response = await self._request_async("GET", f"/speech/profile/{biz_key}")
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise LLMServiceRemoteError("invalid LLM speech profile response")
        try:
            profile = LLMSpeechProfile(
                biz_key=str(payload.get("bizKey") or ""),
                provider_key=str(payload.get("providerKey") or ""),
                model=str(payload.get("model") or ""),
                voice=str(payload.get("voice") or ""),
                response_format=str(payload.get("responseFormat") or ""),
                speed=float(payload.get("speed", 1.0)),
                cache_revision=str(payload.get("cacheRevision") or ""),
                config_fingerprint=str(payload.get("configFingerprint") or ""),
            )
        except (TypeError, ValueError) as exc:
            raise LLMServiceRemoteError(
                "invalid LLM speech profile response"
            ) from exc
        if profile.biz_key != biz_key or not all(
            (
                profile.provider_key,
                profile.model,
                profile.voice,
                profile.response_format,
                profile.cache_revision,
                profile.config_fingerprint,
            )
        ):
            raise LLMServiceRemoteError("invalid LLM speech profile response")
        return profile

    async def speech(
        self,
        *,
        biz_key: str,
        provider_key: str | None,
        text: str,
    ) -> LLMSpeechAudio:
        response = await self._request_async(
            "POST",
            "/speech",
            json={"bizKey": biz_key, "providerKey": provider_key, "text": text},
        )
        config_fingerprint = response.headers.get(
            "x-speech-config-fingerprint",
            "",
        )
        if not response.content or not config_fingerprint:
            raise LLMServiceRemoteError("invalid LLM speech response")
        return LLMSpeechAudio(
            content=response.content,
            media_type=response.headers.get(
                "content-type",
                "application/octet-stream",
            ).split(";", 1)[0],
            config_fingerprint=config_fingerprint,
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._assert_loop()
        self._closed = True
        await self._async.aclose()

    async def _request_async(self, method: str, path: str, **kwargs) -> httpx.Response:
        self._assert_loop()
        try:
            response = await self._async.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise LLMServiceTimeout(f"LLM request timed out: {path}") from exc
        except httpx.HTTPError as exc:
            raise LLMServiceUnavailable(f"LLM service unavailable: {exc}") from exc
        self._raise_for_status(response)
        return response

    def _assert_loop(self) -> None:
        if self._closed:
            raise RuntimeError("LLM service client is closed")
        loop = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = loop
        elif self._owner_loop is not loop:
            raise RuntimeError("LLM service client cannot be reused across event loops")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def _inference_payload(
        *,
        biz_key: str,
        provider_key: str | None,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> dict[str, object]:
        return {
            "bizKey": biz_key,
            "providerKey": provider_key,
            "messages": messages,
            "tools": tools,
        }

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, Mapping) and isinstance(payload.get("detail"), Mapping):
            payload = payload["detail"]
        if not isinstance(payload, Mapping):
            payload = {}
        message = str(payload.get("message") or response.text or "LLM service request failed")
        error_code = str(payload.get("errorCode") or "LLM_SERVICE_ERROR")
        request_id = str(payload.get("requestId")) if payload.get("requestId") is not None else None
        if response.status_code == 401:
            raise LLMServiceAuthError(message)
        raise LLMServiceRemoteError(
            message,
            error_code=error_code,
            status_code=response.status_code,
            request_id=request_id,
        )


async def _iter_sse(response: httpx.Response) -> AsyncIterator[tuple[str, object]]:
    event = "message"
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if data_lines:
                raw = "\n".join(data_lines)
                try:
                    payload: object = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise LLMServiceRemoteError("invalid JSON in LLM stream") from exc
                yield event, payload
            event = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if data_lines:
        yield event, json.loads("\n".join(data_lines))


def _remote_error_from_payload(payload: object) -> LLMServiceRemoteError:
    if not isinstance(payload, Mapping):
        return LLMServiceRemoteError("LLM stream failed")
    return LLMServiceRemoteError(
        str(payload.get("message") or "LLM stream failed"),
        error_code=str(payload.get("errorCode") or "LLM_STREAM_ERROR"),
        request_id=str(payload.get("requestId")) if payload.get("requestId") is not None else None,
    )
