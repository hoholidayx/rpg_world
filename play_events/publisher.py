"""Loop-owned HTTP publisher for best-effort Play events."""

from __future__ import annotations

import asyncio
import logging

import httpx

from play_events.contracts import PlayEvent


logger = logging.getLogger(__name__)


class PlayEventPublisher:
    def __init__(
        self,
        *,
        endpoint_url: str,
        token: str,
        timeout_ms: int = 2000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        endpoint = str(endpoint_url).strip()
        if not endpoint:
            raise ValueError("Play event endpoint_url must not be empty")
        resolved_token = str(token).strip()
        if not resolved_token:
            raise ValueError("Play event token must not be empty")
        self._endpoint_url = endpoint
        self._token = resolved_token
        self._timeout = max(1, int(timeout_ms)) / 1000
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    async def publish(self, event: PlayEvent) -> None:
        self._bind_loop()
        if self._closed:
            raise RuntimeError("Play event publisher is closed")
        client = self._client
        if client is None:
            client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            )
            self._client = client
        response = await client.post(
            self._endpoint_url,
            headers={"Authorization": f"Bearer {self._token}"},
            json=event.to_wire(),
        )
        response.raise_for_status()
        self._log_acknowledgement(event, response)

    async def close(self) -> None:
        self._bind_loop()
        if self._closed:
            return
        self._closed = True
        client = self._client
        self._client = None
        if client is not None:
            await client.aclose()

    def _bind_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError(
                "Play event publisher cannot be reused across event loops"
            )

    @staticmethod
    def _log_acknowledgement(
        event: PlayEvent,
        response: httpx.Response,
    ) -> None:
        try:
            acknowledgement = response.json()
        except ValueError:
            logger.debug(
                "Play event publish acknowledgement is not JSON event_id=%s event_type=%s",
                event.event_id,
                event.event_type.value,
            )
            return
        subscribers = (
            acknowledgement.get("subscribers")
            if isinstance(acknowledgement, dict)
            else None
        )
        if not isinstance(subscribers, int) or isinstance(subscribers, bool):
            logger.debug(
                "Play event publish acknowledgement has no subscriber count "
                "event_id=%s event_type=%s",
                event.event_id,
                event.event_type.value,
            )
            return
        log = logger.warning if subscribers == 0 else logger.info
        log(
            "Play event publish acknowledged event_id=%s event_type=%s "
            "session_id=%s subscribers=%s",
            event.event_id,
            event.event_type.value,
            event.session_id,
            subscribers,
        )
