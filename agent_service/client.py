"""Shared Agent service HTTP/SSE client."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind
from llm_service.types import LLMUsage
from agent_service.settings import settings


class AgentClientError(RuntimeError):
    """Base error raised by ``AgentClient``."""


class AgentServiceUnavailable(AgentClientError):
    """Raised when the Agent service cannot be reached."""


@dataclass(frozen=True)
class AgentClientConfig:
    base_url: str
    request_timeout_ms: int = 60000
    stream_timeout_ms: int = 300000


def _default_config() -> AgentClientConfig:
    cfg = settings.agent_client
    return AgentClientConfig(
        base_url=cfg.base_url,
        request_timeout_ms=cfg.request_timeout_ms,
        stream_timeout_ms=cfg.stream_timeout_ms,
    )


class AgentClient:
    """SDK used by all non-agent processes to call the Agent service."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        request_timeout_ms: int | None = None,
        stream_timeout_ms: int | None = None,
    ) -> None:
        cfg = _default_config()
        self.base_url = (base_url or cfg.base_url).rstrip("/")
        self.request_timeout_ms = request_timeout_ms or cfg.request_timeout_ms
        self.stream_timeout_ms = stream_timeout_ms or cfg.stream_timeout_ms
        self._request_client: httpx.AsyncClient | None = None
        self._stream_client: httpx.AsyncClient | None = None

    async def health(self) -> dict[str, Any]:
        return await self._get("/health")

    async def get_history(
        self,
        workspace: str,
        session_id: str,
    ) -> dict[str, Any]:
        params = {"workspace": workspace, "session_id": session_id}
        return await self._get("/chat/history", params=params)

    async def list_commands(
        self,
        workspace: str,
        session_id: str,
    ) -> dict[str, Any]:
        params = {"workspace": workspace, "session_id": session_id}
        return await self._get("/chat/commands", params=params)

    async def list_sessions(
        self,
        workspace_id: str,
        story_id: int,
    ) -> dict[str, Any]:
        params = {"workspace_id": workspace_id, "story_id": story_id}
        return await self._get("/chat/sessions", params=params)

    async def create_session(self, workspace_id: str, story_id: int, *, title: str = "") -> dict[str, Any]:
        return await self._post(
            "/chat/sessions",
            json={"workspace_id": workspace_id, "story_id": story_id, "title": title},
        )

    async def ensure_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        session_id: str | None = None,
        title: str = "",
    ) -> dict[str, Any]:
        return await self._post(
            "/chat/session/ensure",
            json={
                "workspace_id": workspace_id,
                "story_id": story_id,
                "session_id": session_id,
                "title": title,
            },
        )

    async def delete_session(self, workspace: str, session_id: str) -> dict[str, Any]:
        return await self._delete(
            f"/chat/sessions/{session_id}",
            params={"workspace": workspace},
        )

    async def clone_session(self, workspace: str, session_id: str, target_session_id: str) -> dict[str, Any]:
        return await self._post(
            f"/chat/sessions/{session_id}/clone",
            json={"workspace": workspace, "target_session_id": target_session_id},
        )

    async def send(
        self,
        workspace: str,
        session_id: str,
        message: str,
    ) -> dict[str, Any]:
        return await self._post(
            "/chat/send",
            json=self._payload(workspace, session_id, message=message),
        )

    async def execute_command(
        self,
        workspace: str,
        session_id: str,
        command: str,
    ) -> dict[str, Any]:
        return await self._post(
            "/chat/command",
            json=self._payload(workspace, session_id, command=command),
        )

    async def stream(
        self,
        workspace: str,
        session_id: str,
        message: str,
    ) -> AsyncIterator[AgentStreamEvent]:
        payload = self._payload(workspace, session_id, message=message)
        client = self._stream_http_client()
        try:
            async with client.stream("POST", self._url("/chat/stream"), json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line.removeprefix("data:").strip()
                    if not raw:
                        continue
                    yield _event_from_dict(json.loads(raw))
        except httpx.ConnectError as exc:
            raise AgentServiceUnavailable(f"Agent service unavailable: {exc}") from exc
        except httpx.HTTPError as exc:
            raise AgentClientError(str(exc)) from exc

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        client = self._request_http_client()
        try:
            response = await client.get(self._url(path), params=params)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as exc:
            raise AgentServiceUnavailable(f"Agent service unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise AgentClientError(_http_error_message(exc.response)) from exc
        except httpx.HTTPError as exc:
            raise AgentClientError(str(exc)) from exc

    async def _post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        client = self._request_http_client()
        try:
            response = await client.post(self._url(path), json=json)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as exc:
            raise AgentServiceUnavailable(f"Agent service unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise AgentClientError(_http_error_message(exc.response)) from exc
        except httpx.HTTPError as exc:
            raise AgentClientError(str(exc)) from exc

    async def _delete(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        client = self._request_http_client()
        try:
            response = await client.delete(self._url(path), params=params)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as exc:
            raise AgentServiceUnavailable(f"Agent service unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise AgentClientError(_http_error_message(exc.response)) from exc
        except httpx.HTTPError as exc:
            raise AgentClientError(str(exc)) from exc

    async def aclose(self) -> None:
        if self._request_client is not None:
            await self._request_client.aclose()
            self._request_client = None
        if self._stream_client is not None:
            await self._stream_client.aclose()
            self._stream_client = None

    def _request_http_client(self) -> httpx.AsyncClient:
        if self._request_client is None:
            self._request_client = httpx.AsyncClient(timeout=httpx.Timeout(self.request_timeout_ms / 1000))
        return self._request_client

    def _stream_http_client(self) -> httpx.AsyncClient:
        if self._stream_client is None:
            self._stream_client = httpx.AsyncClient(timeout=httpx.Timeout(self.stream_timeout_ms / 1000))
        return self._stream_client

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    def _payload(
        workspace: str,
        session_id: str,
        **extra: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"workspace": workspace, "session_id": session_id}
        payload.update(extra)
        return payload


def _http_error_message(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = response.text
    return str(detail or f"Agent service returned HTTP {response.status_code}")


def _event_from_dict(data: dict[str, Any]) -> AgentStreamEvent:
    usage = data.get("usage")
    usage_obj = None
    if isinstance(usage, dict):
        usage_obj = LLMUsage(
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            total_tokens=int(usage.get("total_tokens", 0) or 0),
            prompt_tokens_details={"cached_tokens": int(usage.get("cached_tokens", 0) or 0)},
        )
    kind = StreamEventKind(data.get("kind", "text"))
    return AgentStreamEvent(
        kind=kind,
        content=str(data.get("content", "") or ""),
        tool_name=data.get("tool_name"),
        tool_arguments=data.get("tool_arguments"),
        tool_result_preview=data.get("tool_result_preview"),
        round_index=int(data.get("round_index", 0) or 0),
        usage=usage_obj,
        model=data.get("model"),
        finish_reason=data.get("finish_reason"),
        duration_ms=float(data.get("duration_ms", 0.0) or 0.0),
    )
