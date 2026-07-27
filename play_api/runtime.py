"""Lifespan-owned resources for the Play API process."""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from agent_service.client import AgentClient
from commons.runtime_lifecycle import cleanup_runtime_resources
from dream_service.client import DreamClient
from media_service.client import MediaClient
from play_api.agent_client import close_agent_client, create_agent_client
from play_api.data_runtime import PlayDataRuntime
from play_api.dream_client import close_dream_client, create_dream_client
from play_api.event_hub import PlayEventHub, PlayEventRuntime
from play_api.media_client import close_media_client, create_media_client
from play_api.settings import PlayApiSettings
from play_api.tts_client import close_tts_client, create_tts_client
from play_events.auth import uses_default_play_event_token
from tts_service.client import TTSClient


@dataclass(slots=True)
class PlayServiceRuntime:
    """Own the event Hub, data runtime, and four loop-owned HTTP clients."""

    events: PlayEventRuntime
    data: PlayDataRuntime
    agent_client: AgentClient
    dream_client: DreamClient
    media_client: MediaClient
    tts_client: TTSClient
    _event_hub: PlayEventHub = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    async def create(cls, *, settings: PlayApiSettings) -> "PlayServiceRuntime":
        event_cfg = settings.events
        if uses_default_play_event_token(event_cfg.token_env):
            logger.warning(
                "{} is not set; using the local Play event token fallback",
                event_cfg.token_env,
            )
        event_hub = PlayEventHub(
            subscriber_queue_capacity=event_cfg.subscriber_queue_capacity,
        )
        events = PlayEventRuntime(
            hub=event_hub,
            token=event_cfg.token,
            heartbeat_seconds=event_cfg.heartbeat_seconds,
            retry_ms=event_cfg.retry_ms,
        )

        data: PlayDataRuntime | None = None
        agent: AgentClient | None = None
        dream: DreamClient | None = None
        media: MediaClient | None = None
        tts: TTSClient | None = None
        try:
            data = PlayDataRuntime.create()
            agent = create_agent_client()
            dream = create_dream_client()
            media = create_media_client()
            tts = create_tts_client()
            return cls(
                events=events,
                data=data,
                agent_client=agent,
                dream_client=dream,
                media_client=media,
                tts_client=tts,
                _event_hub=event_hub,
            )
        except BaseException as startup_error:
            steps = [("event_hub", event_hub.close)]
            if dream is not None:
                steps.append(
                    (
                        "dream_client",
                        lambda: close_dream_client(dream),
                    )
                )
            if media is not None:
                steps.append(
                    (
                        "media_client",
                        lambda: close_media_client(media),
                    )
                )
            if tts is not None:
                steps.append(
                    (
                        "tts_client",
                        lambda: close_tts_client(tts),
                    )
                )
            if agent is not None:
                steps.append(
                    (
                        "agent_client",
                        lambda: close_agent_client(agent),
                    )
                )
            if data is not None:
                steps.append(("play_data", data.close))
            try:
                await cleanup_runtime_resources("PlayServiceRuntime", steps)
            except BaseException as cleanup_error:
                raise BaseExceptionGroup(
                    "PlayServiceRuntime startup and cleanup failed",
                    [startup_error, cleanup_error],
                ) from startup_error
            raise

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await cleanup_runtime_resources(
            "PlayServiceRuntime",
            (
                ("event_hub", self._event_hub.close),
                (
                    "dream_client",
                    lambda: close_dream_client(self.dream_client),
                ),
                (
                    "media_client",
                    lambda: close_media_client(self.media_client),
                ),
                (
                    "tts_client",
                    lambda: close_tts_client(self.tts_client),
                ),
                (
                    "agent_client",
                    lambda: close_agent_client(self.agent_client),
                ),
                ("play_data", self.data.close),
            ),
        )


__all__ = ["PlayServiceRuntime"]
