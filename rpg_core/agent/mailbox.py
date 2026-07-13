"""Serialized Agent work queue and stream cancellation ownership."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from loguru import logger

from commons.errors import (
    MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE,
    MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE,
    TURN_METADATA_INVALID_ERROR_CODE,
    TURN_METADATA_INVALID_STATUS_CODE,
    MainContextWindowThresholdExceededError,
    format_turn_metadata_error_message,
)
from rpg_core.agent.agent_types import (
    AgentStreamEvent,
    QueueItem,
    QueueKind,
    StreamEventKind,
    TurnCancelResult,
    TurnCancelStatus,
    _StreamSentinel,
)
from rpg_core.session import InvalidTurnMetadataError

if TYPE_CHECKING:
    from rpg_core.agent.command import CommandDispatcher, CommandResult
    from rpg_core.agent.loop import AgentReply
    from rpg_core.agent.turn.models import TurnRequest
    from rpg_core.agent.turn.service import AgentTurnService

_TAG = "[AgentMailbox]"


class AgentMailbox:
    """Own FIFO serialization, stream tasks, and request-id cancellation."""

    def __init__(
        self,
        *,
        session_id: Callable[[], str],
        model: Callable[[], str | None],
        turn_service: "AgentTurnService",
        command_dispatcher: "CommandDispatcher",
        truncate_history: Callable[[int], dict[str, object]],
        deferred_status: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._session_id = session_id
        self._model = model
        self._turn_service = turn_service
        self._command_dispatcher = command_dispatcher
        self._truncate_history = truncate_history
        self._deferred_status = deferred_status
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._consumer_task: asyncio.Task | None = None
        self._active_stream_task: asyncio.Task | None = None
        self._active_stream_request_id: str | None = None
        self._queued_stream_request_ids: set[str] = set()
        self._cancelled_request_ids: set[str] = set()

    def start(self) -> None:
        if self._consumer_task is None or self._consumer_task.done():
            self._consumer_task = asyncio.create_task(self._consume())

    async def wait_idle(self) -> None:
        await self._queue.join()

    async def close(self) -> None:
        """Cancel owned background tasks; primarily used by scoped runtimes/tests."""
        active = self._active_stream_task
        if active is not None and not active.done():
            active.cancel()
            with suppress(asyncio.CancelledError):
                await active
        consumer = self._consumer_task
        if consumer is not None and not consumer.done():
            consumer.cancel()
            with suppress(asyncio.CancelledError):
                await consumer
        self._active_stream_task = None
        self._active_stream_request_id = None
        self._consumer_task = None

    async def send(self, request: "TurnRequest") -> "AgentReply":
        future = self._create_future()
        await self._queue.put(
            QueueItem(
                kind=QueueKind.SEND,
                future=future,
                turn_request=request,
            )
        )
        logger.debug(_TAG + " send enqueued: input={!r:.60}", request.text)
        return await future

    async def send_stream(
        self,
        request: "TurnRequest",
    ) -> AsyncIterator[AgentStreamEvent]:
        event_queue: asyncio.Queue[
            AgentStreamEvent | BaseException | _StreamSentinel
        ] = asyncio.Queue()
        future = self._create_future()
        request_id = request.request_id
        if request_id:
            self._queued_stream_request_ids.add(request_id)
        await self._queue.put(
            QueueItem(
                kind=QueueKind.SEND_STREAM,
                future=future,
                event_queue=event_queue,
                turn_request=request,
            )
        )
        logger.debug(
            _TAG + " stream enqueued: request_id={}, input={!r:.60}",
            request_id,
            request.text,
        )
        stream_completed = False
        try:
            while True:
                item = await event_queue.get()
                if isinstance(item, _StreamSentinel):
                    stream_completed = True
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            if request_id and not stream_completed and not future.done():
                logger.info(
                    _TAG + " stream consumer closed before completion; cancelling turn: session_id={}, request_id={}",
                    self._session_id(),
                    request_id,
                )
                try:
                    await self.cancel_current_turn(request_id=request_id)
                except Exception as exc:
                    logger.opt(exception=exc).warning(
                        _TAG + " stream close cancellation failed: session_id={}, request_id={}",
                        self._session_id(),
                        request_id,
                    )
        if future.done() and future.exception():
            raise future.exception()

    async def execute_command(self, command: str) -> "CommandResult":
        future = self._create_future()
        await self._queue.put(
            QueueItem(
                kind=QueueKind.COMMAND,
                future=future,
                command=command,
            )
        )
        logger.debug(_TAG + " command enqueued: command={!r:.60}", command)
        return await future

    async def truncate_history_from_turn(self, turn_id: int) -> dict[str, object]:
        future = self._create_future()
        await self._queue.put(
            QueueItem(
                kind=QueueKind.TRUNCATE_HISTORY,
                future=future,
                turn_id=int(turn_id),
            )
        )
        logger.debug(
            _TAG + " truncate enqueued: session_id={}, turn_id={}",
            self._session_id(),
            turn_id,
        )
        return await future

    async def cancel_current_turn(
        self,
        request_id: str | None = None,
    ) -> TurnCancelResult:
        active_task = self._active_stream_task
        active_request_id = self._active_stream_request_id
        if active_task is not None and active_task.done():
            self._active_stream_task = None
            self._active_stream_request_id = None
            active_task = None
            active_request_id = None

        if request_id and request_id in self._queued_stream_request_ids:
            self._cancelled_request_ids.add(request_id)
            logger.info(
                _TAG + " queued stream cancel requested: session_id={}, request_id={}",
                self._session_id(),
                request_id,
            )
            return TurnCancelResult(
                status=TurnCancelStatus.CANCELLED,
                session_id=self._session_id(),
                request_id=request_id,
            )
        if active_task is None:
            logger.info(
                _TAG + " stream cancel requested but no active turn: session_id={}, request_id={}",
                self._session_id(),
                request_id,
            )
            return TurnCancelResult(
                status=TurnCancelStatus.NOT_RUNNING,
                session_id=self._session_id(),
                request_id=request_id,
            )
        if request_id and active_request_id != request_id:
            logger.info(
                _TAG + " stale stream cancel ignored: session_id={}, request_id={}, active_request_id={}",
                self._session_id(),
                request_id,
                active_request_id,
            )
            return TurnCancelResult(
                status=TurnCancelStatus.STALE,
                session_id=self._session_id(),
                request_id=request_id,
            )
        active_task.cancel()
        logger.info(
            _TAG + " active stream cancel requested: session_id={}, request_id={}",
            self._session_id(),
            active_request_id,
        )
        return TurnCancelResult(
            status=TurnCancelStatus.CANCELLED,
            session_id=self._session_id(),
            request_id=active_request_id or request_id,
        )

    async def _consume(self) -> None:
        while True:
            item = await self._queue.get()
            logger.debug(
                _TAG + " consumer processing: kind={}, input={!r:.60}",
                item.kind,
                item.input_text,
            )
            try:
                match item.kind:
                    case QueueKind.SEND:
                        if item.turn_request is None:
                            raise ValueError("turn_request is required for send")
                        reply = await self._turn_service.execute_sync(item.turn_request)
                        item.future.set_result(reply)
                        if reply.committed_turn_id is not None:
                            await asyncio.sleep(0)
                            await self._run_deferred_status()
                    case QueueKind.SEND_STREAM:
                        await self._run_stream_item(item)
                    case QueueKind.COMMAND:
                        if item.command is None:
                            raise ValueError("command is required")
                        item.future.set_result(
                            await self._command_dispatcher.dispatch(item.command)
                        )
                    case QueueKind.TRUNCATE_HISTORY:
                        if item.turn_id is None:
                            raise ValueError("turn_id is required")
                        item.future.set_result(self._truncate_history(item.turn_id))
            except Exception as exc:
                logger.warning(_TAG + " consumer error on kind={}: {}", item.kind, exc)
                if item.kind == QueueKind.SEND_STREAM and item.event_queue is not None:
                    await self._emit_stream_error(item.event_queue, exc)
                    if not item.future.done():
                        item.future.set_result(None)
                elif not item.future.done():
                    item.future.set_exception(exc)
            finally:
                self._queue.task_done()

    async def _run_stream_item(self, item: QueueItem) -> None:
        if item.event_queue is None:
            raise ValueError("event_queue is required for send_stream")
        request_id = item.request_id
        if request_id:
            self._queued_stream_request_ids.discard(request_id)
            if request_id in self._cancelled_request_ids:
                self._cancelled_request_ids.discard(request_id)
                logger.info(
                    _TAG + " skipping cancelled queued stream: session_id={}, request_id={}",
                    self._session_id(),
                    request_id,
                )
                await item.event_queue.put(_StreamSentinel())
                if not item.future.done():
                    item.future.set_result(None)
                return
        if item.turn_request is None:
            raise ValueError("turn_request is required for send_stream")

        task = asyncio.create_task(
            self._turn_service.execute_stream(item.turn_request, item.event_queue)
        )
        self._active_stream_task = task
        self._active_stream_request_id = request_id
        logger.debug(
            _TAG + " stream task started: session_id={}, request_id={}",
            self._session_id(),
            request_id,
        )
        try:
            committed_turn_id = await task
        except asyncio.CancelledError:
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelling():
                raise
            logger.info(
                _TAG + " stream task cancelled: session_id={}, request_id={}",
                self._session_id(),
                request_id,
            )
            await item.event_queue.put(_StreamSentinel())
            if not item.future.done():
                item.future.set_result(None)
            return
        finally:
            if self._active_stream_task is task:
                self._active_stream_task = None
                self._active_stream_request_id = None
        if not item.future.done():
            item.future.set_result(None)
        if committed_turn_id is not None:
            await asyncio.sleep(0)
            await self._run_deferred_status()

    async def _run_deferred_status(self) -> None:
        if self._deferred_status is None:
            return
        try:
            await self._deferred_status()
        except Exception as exc:
            logger.opt(exception=exc).warning(
                _TAG + " deferred status reconciliation failed: session_id={}",
                self._session_id(),
            )

    @staticmethod
    def _create_future() -> asyncio.Future:
        return asyncio.get_running_loop().create_future()

    @classmethod
    async def _emit_stream_error(
        cls,
        event_queue: asyncio.Queue,
        error: BaseException,
    ) -> None:
        await event_queue.put(cls.stream_error_event(error))
        await event_queue.put(_StreamSentinel())

    @staticmethod
    def stream_error_event(error: BaseException) -> AgentStreamEvent:
        if isinstance(error, MainContextWindowThresholdExceededError):
            return AgentStreamEvent(
                kind=StreamEventKind.ERROR,
                content=str(error),
                error_code=MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE,
                status_code=MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE,
            )
        if isinstance(error, InvalidTurnMetadataError):
            return AgentStreamEvent(
                kind=StreamEventKind.ERROR,
                content=format_turn_metadata_error_message(error),
                error_code=TURN_METADATA_INVALID_ERROR_CODE,
                status_code=TURN_METADATA_INVALID_STATUS_CODE,
            )
        return AgentStreamEvent(kind=StreamEventKind.ERROR, content=str(error))
