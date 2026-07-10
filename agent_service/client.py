"""Shared Agent service HTTP/SSE client."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TypedDict, cast

import httpx

from agent_service.schemas import (
    AgentCommandResultPayload,
    AgentCommandsPayload,
    AgentHealthPayload,
    AgentHistoryPayload,
    AgentMainLLMProviderCatalogPayload,
    AgentMainLLMSelectionPayload,
    AgentReplyPayload,
    AgentSessionCreatePayload,
    AgentSessionPayloadDict,
    AgentSessionsPayload,
    AgentTurnCancelPayload,
)
from agent_service.settings import settings
from commons.types import JsonObject
from llm_service.types import LLMUsage
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind


class AgentClientError(RuntimeError):
    """Base error raised by ``AgentClient``."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AgentServiceUnavailable(AgentClientError):
    """Raised when the Agent service cannot be reached."""


class ContextPreviewTotals(TypedDict):
    layerCount: int
    activeLayers: int
    tokenCount: int
    messageCount: int


class ContextPreviewLayer(TypedDict):
    index: int
    type: str
    role: str
    status: str
    charCount: int
    tokenCount: int
    description: str
    content: str


class ContextPreviewPayload(TypedDict):
    formatVersion: str
    sessionId: str
    hotHistoryRounds: int | None
    totals: ContextPreviewTotals
    layers: list[ContextPreviewLayer]
    messages: list[JsonObject]
    usageEstimate: JsonObject | None


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

    async def health(self) -> AgentHealthPayload:
        return cast(AgentHealthPayload, await self._get("/health"))

    async def get_history(
        self,
        session_id: str,
    ) -> AgentHistoryPayload:
        params = {"session_id": session_id}
        return cast(AgentHistoryPayload, await self._get("/chat/history", params=params))

    async def list_commands(
        self,
        session_id: str,
    ) -> AgentCommandsPayload:
        params = {"session_id": session_id}
        return cast(AgentCommandsPayload, await self._get("/chat/commands", params=params))

    async def get_context_preview(
        self,
        session_id: str,
    ) -> ContextPreviewPayload:
        params = {"session_id": session_id}
        return cast(ContextPreviewPayload, await self._get("/chat/context-preview", params=params))

    async def get_main_llm_options(self) -> AgentMainLLMProviderCatalogPayload:
        return cast(
            AgentMainLLMProviderCatalogPayload,
            await self._get("/chat/main-llm/options"),
        )

    async def get_story_main_llm(
        self,
        workspace_id: str,
        story_id: int,
    ) -> AgentMainLLMSelectionPayload:
        return cast(
            AgentMainLLMSelectionPayload,
            await self._get(
                "/chat/main-llm/story",
                params={"workspace_id": workspace_id, "story_id": story_id},
            ),
        )

    async def set_story_main_llm(
        self,
        workspace_id: str,
        story_id: int,
        provider_key: str | None,
    ) -> AgentMainLLMSelectionPayload:
        return cast(
            AgentMainLLMSelectionPayload,
            await self._post(
                "/chat/main-llm/story",
                json={
                    "workspace_id": workspace_id,
                    "story_id": story_id,
                    "provider_key": provider_key,
                },
            ),
        )

    async def get_session_main_llm(
        self,
        session_id: str,
    ) -> AgentMainLLMSelectionPayload:
        return cast(
            AgentMainLLMSelectionPayload,
            await self._get(
                "/chat/main-llm/session",
                params={"session_id": session_id},
            ),
        )

    async def set_session_main_llm(
        self,
        session_id: str,
        provider_key: str | None,
    ) -> AgentMainLLMSelectionPayload:
        return cast(
            AgentMainLLMSelectionPayload,
            await self._post(
                "/chat/main-llm/session",
                json={"session_id": session_id, "provider_key": provider_key},
            ),
        )

    async def list_sessions(
        self,
        workspace_id: str,
        story_id: int,
    ) -> AgentSessionsPayload:
        params = {"workspace_id": workspace_id, "story_id": story_id}
        return cast(AgentSessionsPayload, await self._get("/chat/sessions", params=params))

    async def create_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str = "",
        player_character_id: int | None = None,
    ) -> AgentSessionCreatePayload:
        payload: dict[str, object] = {"workspace_id": workspace_id, "story_id": story_id, "title": title}
        if player_character_id is not None:
            payload["player_character_id"] = player_character_id
        result = await self._post(
            "/chat/sessions",
            json=payload,
        )
        return cast(AgentSessionCreatePayload, result)

    async def ensure_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        session_id: str | None = None,
        title: str = "",
        player_character_id: int | None = None,
    ) -> AgentSessionPayloadDict:
        payload: dict[str, object] = {
            "workspace_id": workspace_id,
            "story_id": story_id,
            "session_id": session_id,
            "title": title,
        }
        if player_character_id is not None:
            payload["player_character_id"] = player_character_id
        result = await self._post(
            "/chat/session/ensure",
            json=payload,
        )
        return cast(AgentSessionPayloadDict, result)

    async def send(
        self,
        session_id: str,
        message: str,
    ) -> AgentReplyPayload:
        result = await self._post(
            "/chat/send",
            json={"session_id": session_id, "message": message},
        )
        return cast(AgentReplyPayload, result)

    async def reload_history(
        self,
        session_id: str,
    ) -> JsonObject:
        result = await self._post(
            "/chat/session/reload-history",
            json={"session_id": session_id},
        )
        return result

    async def bind_player_character(
        self,
        session_id: str,
        player_character_id: int,
    ) -> JsonObject:
        result = await self._post(
            "/chat/session/player-character",
            json={"session_id": session_id, "player_character_id": int(player_character_id)},
        )
        return result

    async def truncate_turn(
        self,
        session_id: str,
        turn_id: int,
    ) -> JsonObject:
        result = await self._post(
            f"/chat/session/turns/{int(turn_id)}/truncate",
            json={"session_id": session_id},
        )
        return result

    async def delete_message(
        self,
        session_id: str,
        message_id: int,
    ) -> JsonObject:
        return await self._delete(
            f"/chat/messages/{int(message_id)}",
            params={"session_id": session_id},
        )

    async def execute_command(
        self,
        session_id: str,
        command: str,
    ) -> AgentCommandResultPayload:
        result = await self._post(
            "/chat/command",
            json={"session_id": session_id, "command": command},
        )
        return cast(AgentCommandResultPayload, result)

    async def stop(
        self,
        session_id: str,
        request_id: str | None = None,
    ) -> AgentTurnCancelPayload:
        payload: JsonObject = {"session_id": session_id}
        if request_id:
            payload["request_id"] = request_id
        result = await self._post("/chat/stop", json=payload)
        return cast(AgentTurnCancelPayload, result)

    async def stream(
        self,
        session_id: str,
        message: str,
        request_id: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        payload: JsonObject = {"session_id": session_id, "message": message}
        if request_id:
            payload["request_id"] = request_id
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
                    payload_obj: object = json.loads(raw)
                    if isinstance(payload_obj, dict):
                        yield _event_from_dict(cast(JsonObject, payload_obj))
        except httpx.ConnectError as exc:
            raise AgentServiceUnavailable(f"Agent service unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise AgentClientError(_http_error_message(exc.response), status_code=exc.response.status_code) from exc
        except httpx.HTTPError as exc:
            raise AgentClientError(str(exc)) from exc

    async def _get(self, path: str, *, params: dict[str, str | int] | None = None) -> JsonObject:
        client = self._request_http_client()
        try:
            response = await client.get(self._url(path), params=params)
            response.raise_for_status()
            return _json_response(response)
        except httpx.ConnectError as exc:
            raise AgentServiceUnavailable(f"Agent service unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise AgentClientError(_http_error_message(exc.response), status_code=exc.response.status_code) from exc
        except httpx.HTTPError as exc:
            raise AgentClientError(str(exc)) from exc

    async def _post(self, path: str, *, json: JsonObject) -> JsonObject:
        client = self._request_http_client()
        try:
            response = await client.post(self._url(path), json=json)
            response.raise_for_status()
            return _json_response(response)
        except httpx.ConnectError as exc:
            raise AgentServiceUnavailable(f"Agent service unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise AgentClientError(_http_error_message(exc.response), status_code=exc.response.status_code) from exc
        except httpx.HTTPError as exc:
            raise AgentClientError(str(exc)) from exc

    async def _delete(self, path: str, *, params: dict[str, str | int] | None = None) -> JsonObject:
        client = self._request_http_client()
        try:
            response = await client.delete(self._url(path), params=params)
            response.raise_for_status()
            return _json_response(response)
        except httpx.ConnectError as exc:
            raise AgentServiceUnavailable(f"Agent service unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise AgentClientError(_http_error_message(exc.response), status_code=exc.response.status_code) from exc
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


def _http_error_message(response: httpx.Response) -> str:
    try:
        payload: object = response.json()
        detail = payload.get("detail") if isinstance(payload, dict) else response.text
    except Exception:
        detail = response.text
    return str(detail or f"Agent service returned HTTP {response.status_code}")


def _json_response(response: httpx.Response) -> JsonObject:
    payload: object = response.json()
    if not isinstance(payload, dict):
        raise AgentClientError(f"Agent service returned non-object JSON from {response.url}")
    return cast(JsonObject, payload)


def _event_from_dict(data: JsonObject) -> AgentStreamEvent:
    usage = data.get("usage")
    usage_obj = None
    if isinstance(usage, dict):
        usage_obj = LLMUsage(
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            total_tokens=int(usage.get("total_tokens", 0) or 0),
            prompt_tokens_details={"cached_tokens": int(usage.get("cached_tokens", 0) or 0)},
            prompt_cache_hit_tokens=int(usage.get("cached_tokens", 0) or 0),
            raw_usage=usage,
        )
    kind = StreamEventKind(str(data.get("kind") or "text"))
    return AgentStreamEvent(
        kind=kind,
        content=str(data.get("content", "") or ""),
        error_code=_optional_string(data.get("error_code")),
        status_code=_optional_int(data.get("status_code")),
        tool_name=_optional_string(data.get("tool_name")),
        tool_arguments=_optional_string(data.get("tool_arguments")),
        tool_result_preview=_optional_string(data.get("tool_result_preview")),
        round_index=int(data.get("round_index", 0) or 0),
        usage=usage_obj,
        model=_optional_string(data.get("model")),
        finish_reason=_optional_string(data.get("finish_reason")),
        duration_ms=float(data.get("duration_ms", 0.0) or 0.0),
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
