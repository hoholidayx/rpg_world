"""Process-local broadcast hub for best-effort Play events."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from play_events import PlayEvent

logger = logging.getLogger("play_api.event_hub")

PlayEventQueue = asyncio.Queue[PlayEvent | None]


class PlayEventHubClosedError(RuntimeError):
    pass


class PlayEventHub:
    def __init__(self, *, subscriber_queue_capacity: int = 64) -> None:
        self._queue_capacity = max(1, int(subscriber_queue_capacity))
        self._subscribers: set[PlayEventQueue] = set()
        self._lock = asyncio.Lock()
        self._closed = False

    async def subscribe(self) -> PlayEventQueue:
        queue: PlayEventQueue = asyncio.Queue(maxsize=self._queue_capacity)
        async with self._lock:
            if self._closed:
                raise PlayEventHubClosedError("Play event hub is closed")
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: PlayEventQueue) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, event: PlayEvent) -> int:
        async with self._lock:
            if self._closed:
                raise PlayEventHubClosedError("Play event hub is closed")
            subscribers = tuple(self._subscribers)
            overflowed = 0
            for queue in subscribers:
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    else:
                        overflowed += 1
                queue.put_nowait(event)
        if overflowed:
            logger.warning(
                "dropped oldest Play event for slow subscribers count=%s event_id=%s",
                overflowed,
                event.event_id,
            )
        return len(subscribers)

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            subscribers = tuple(self._subscribers)
            self._subscribers.clear()
            for queue in subscribers:
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(None)


@dataclass(frozen=True)
class PlayEventRuntime:
    hub: PlayEventHub
    token: str
    heartbeat_seconds: float
    retry_ms: int
