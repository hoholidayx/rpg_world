"""Telegram-specific background turn coordination and delivery."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from loguru import logger

from agent_service.client import AgentClient
from rpg_core.agent.protocol import StreamEventKind, TurnCancelStatus

from channels.telegram.render import (
    chunk_rendered_text,
    project_rp_text,
    render_markdown_to_telegram_html,
)

_PLACEHOLDER_TEXT = "⏳ 正在生成，请稍候…"
_FAILURE_TEXT = "处理消息失败，请稍后重试。"
_UNKNOWN_STATE_TEXT = "本轮状态暂时无法确认，可能已在后台完成。请先查看会话记录，再决定是否重试。"
_COMMITTED_DELIVERY_FAILURE_TEXT = (
    "回复已生成并保存，但 Telegram 投递未完成。你可以稍后重试或从其他入口查看。"
)
_EMPTY_REPLY_TEXT = "本轮已完成，但没有返回可显示的文本。"
_STOPPED_TEXT = "已停止"
_TELEGRAM_MAX_MESSAGE_LENGTH = 4096
_STOP_RETRY_INITIAL_SECONDS = 0.01
_STOP_RETRY_MAX_SECONDS = 0.25
_STOP_REGISTRATION_GRACE_SECONDS = 2.0


class TelegramTurnPhase(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    FINALIZING = "finalizing"


class TelegramTurnBusyReason(StrEnum):
    CHAT = "chat"
    SESSION = "session"
    CLOSING = "closing"


@dataclass
class ActiveTelegramTurn:
    chat_id: str
    session_id: str
    request_id: str
    phase: TelegramTurnPhase
    streaming: bool
    task: asyncio.Task[None] | None = None
    placeholder_message_id: int | None = None
    accumulated_text: str = ""
    rendered_sent_text: str = ""
    last_edit_at: float = 0.0
    progress_edit_attempted: bool = False
    stop_action_token: str = ""
    stop_task: asyncio.Task[str] | None = None
    stop_requested: bool = False
    stop_status: str = ""
    committed_turn_id: int | None = None
    terminal_received: bool = False
    stream_event_received: bool = False
    transport_finished: bool = False


@dataclass(frozen=True)
class TelegramTurnReservation:
    active: ActiveTelegramTurn | None = None
    busy_reason: TelegramTurnBusyReason | None = None

    @property
    def accepted(self) -> bool:
        return self.active is not None and self.busy_reason is None


class TelegramTurnPresenter(Protocol):
    """Telegram Bot I/O used by the flow after text is rendered to HTML."""

    async def send_html(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: object | None = None,
        terminal: bool = False,
    ) -> int | None: ...

    async def edit_html(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        *,
        terminal: bool = False,
    ) -> bool: ...

    async def delete_message(self, chat_id: str, message_id: int) -> bool: ...

    async def clear_reply_markup(self, chat_id: str, message_id: int) -> bool: ...


class TelegramTurnFlow:
    """Own one background generation per chat and per session."""

    def __init__(
        self,
        *,
        presenter: TelegramTurnPresenter,
        streaming: bool,
        stream_edit_interval_seconds: float,
        stream_edit_min_chars: int,
        clock: Callable[[], float] = time.monotonic,
        request_id_factory: Callable[[], str] | None = None,
        agent_client: AgentClient | None = None,
        stop_markup_factory: Callable[[ActiveTelegramTurn], object | None] | None = None,
        terminal_cleanup: Callable[[ActiveTelegramTurn], None] | None = None,
        active_session_callback: Callable[[ActiveTelegramTurn, str], None] | None = None,
        shutdown_grace_seconds: float = 15.0,
        stop_registration_grace_seconds: float = _STOP_REGISTRATION_GRACE_SECONDS,
    ) -> None:
        self._presenter = presenter
        self._streaming = bool(streaming)
        self._stream_edit_interval = max(0.0, float(stream_edit_interval_seconds))
        self._stream_edit_min_chars = max(1, int(stream_edit_min_chars))
        self._clock = clock
        self._request_id_factory = request_id_factory or (lambda: f"tg_{uuid.uuid4().hex}")
        self._agent_client = agent_client
        self._stop_markup_factory = stop_markup_factory
        self._terminal_cleanup = terminal_cleanup
        self._active_session_callback = active_session_callback
        self._shutdown_grace_seconds = max(0.001, float(shutdown_grace_seconds))
        self._stop_registration_grace_seconds = max(
            0.001,
            float(stop_registration_grace_seconds),
        )
        self._active_by_chat: dict[str, ActiveTelegramTurn] = {}
        self._active_by_session: dict[str, ActiveTelegramTurn] = {}
        self._owned_stop_tasks: set[asyncio.Task[str]] = set()
        self._closing = False

    def bind_agent_client(self, client: AgentClient) -> None:
        self._agent_client = client

    def busy_reason(self, chat_id: str, session_id: str) -> TelegramTurnBusyReason | None:
        if self._closing:
            return TelegramTurnBusyReason.CLOSING
        if str(chat_id) in self._active_by_chat:
            return TelegramTurnBusyReason.CHAT
        if str(session_id) in self._active_by_session:
            return TelegramTurnBusyReason.SESSION
        return None

    def reserve(self, chat_id: str, session_id: str) -> TelegramTurnReservation:
        """Atomically reserve both indexes before any await occurs."""
        chat_id = str(chat_id)
        session_id = str(session_id)
        busy = self.busy_reason(chat_id, session_id)
        if busy is not None:
            return TelegramTurnReservation(busy_reason=busy)
        active = ActiveTelegramTurn(
            chat_id=chat_id,
            session_id=session_id,
            request_id=str(self._request_id_factory()),
            phase=TelegramTurnPhase.STARTING,
            streaming=self._streaming,
        )
        self._active_by_chat[chat_id] = active
        self._active_by_session[session_id] = active
        return TelegramTurnReservation(active=active)

    def attach_task(self, active: ActiveTelegramTurn, task: asyncio.Task[None]) -> bool:
        if not self._owns(active):
            return False
        active.task = task
        return True

    def release(self, active: ActiveTelegramTurn) -> None:
        """Release only if both indexes still point at the same request."""
        if self._same_request(self._active_by_chat.get(active.chat_id), active):
            self._active_by_chat.pop(active.chat_id, None)
        if self._same_request(self._active_by_session.get(active.session_id), active):
            self._active_by_session.pop(active.session_id, None)

    async def request_stop(self, chat_id: str) -> str:
        """Ask Agent service to cancel the exact active SSE request."""
        active = self._active_by_chat.get(str(chat_id))
        if active is None or active.phase is TelegramTurnPhase.FINALIZING:
            return TurnCancelStatus.NOT_RUNNING.value
        return await asyncio.shield(self._ensure_stop_task(active))

    def _ensure_stop_task(self, active: ActiveTelegramTurn) -> asyncio.Task[str]:
        active.stop_requested = True
        task = active.stop_task
        if task is None or task.done():
            task = asyncio.create_task(self._stop_active(active))
            active.stop_task = task
            self._owned_stop_tasks.add(task)
            task.add_done_callback(self._owned_stop_tasks.discard)
        return task

    async def _stop_active(self, active: ActiveTelegramTurn) -> str:
        if active.phase is TelegramTurnPhase.STARTING:
            active.stop_status = TurnCancelStatus.CANCELLED.value
            active.phase = TelegramTurnPhase.FINALIZING
            task = active.task
            current = asyncio.current_task()
            if task is not None and task is not current and not task.done():
                task.cancel()
            try:
                await self._render_stopped(active)
            finally:
                self.release(active)
            return TurnCancelStatus.CANCELLED.value

        client = self._agent_client
        if client is None:
            active.stop_status = "error"
            return "error"

        retry_delay = _STOP_RETRY_INITIAL_SECONDS
        retry_deadline = (
            asyncio.get_running_loop().time()
            + self._stop_registration_grace_seconds
        )
        registration_timed_out = False
        while True:
            try:
                remaining = retry_deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    registration_timed_out = True
                    break
                payload = await asyncio.wait_for(
                    client.stop(
                        active.session_id,
                        request_id=active.request_id,
                    ),
                    timeout=remaining,
                )
                status = str(
                    payload.get("status")
                    or TurnCancelStatus.NOT_RUNNING.value
                )
            except TimeoutError:
                registration_timed_out = True
                break
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "telegram stop failed: chat_id={} session_id={} request_id={}",
                    active.chat_id,
                    active.session_id,
                    self._request_preview(active.request_id),
                )
                status = "error"
            if status not in {
                TurnCancelStatus.NOT_RUNNING.value,
                TurnCancelStatus.STALE.value,
            }:
                break
            task = active.task
            if (
                active.phase is TelegramTurnPhase.FINALIZING
                or active.stream_event_received
                or active.transport_finished
                or task is None
                or task.done()
            ):
                break
            remaining = retry_deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                registration_timed_out = True
                break
            await asyncio.sleep(min(retry_delay, remaining))
            retry_delay = min(
                retry_delay * 2,
                _STOP_RETRY_MAX_SECONDS,
            )
        if registration_timed_out:
            return await self._finish_unconfirmed_stop(active)
        if (
            status == TurnCancelStatus.CANCELLED.value
            and active.phase is TelegramTurnPhase.FINALIZING
        ):
            status = TurnCancelStatus.NOT_RUNNING.value
        active.stop_status = status

        if status != TurnCancelStatus.CANCELLED.value:
            return status

        active.phase = TelegramTurnPhase.FINALIZING
        task = active.task
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            task.cancel()
        try:
            await self._render_stopped(active)
        finally:
            self.release(active)
        return status

    async def _finish_unconfirmed_stop(
        self,
        active: ActiveTelegramTurn,
    ) -> str:
        """Bound a pre-registration stop without claiming remote cancellation."""
        logger.warning(
            "telegram stop confirmation timed out; closing local transport "
            "chat_id={} session_id={} request_id={}",
            active.chat_id,
            active.session_id,
            self._request_preview(active.request_id),
        )
        active.stop_status = "error"
        active.phase = TelegramTurnPhase.FINALIZING
        task = active.task
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            task.cancel()
        try:
            await self._render_unknown(active)
        finally:
            self.release(active)
        return "error"

    async def run(self, active: ActiveTelegramTurn, text: str) -> None:
        """Run one reserved turn and guarantee terminal state cleanup."""
        cancelled = False
        try:
            active.placeholder_message_id = await self._presenter.send_html(
                active.chat_id,
                _PLACEHOLDER_TEXT,
                reply_markup=(
                    self._stop_markup_factory(active)
                    if self._stop_markup_factory is not None
                    else None
                ),
            )
            if active.stop_requested:
                await asyncio.shield(self._ensure_stop_task(active))
                return
            active.phase = TelegramTurnPhase.RUNNING
            client = self._agent_client
            if client is None:
                raise RuntimeError("Agent client is not bound")
            await self._run_stream(client, active, text)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception:
            if await self._is_confirmed_stop(active):
                return
            logger.exception(
                "telegram turn failed: chat_id={} session_id={} request_id={}",
                active.chat_id,
                active.session_id,
                self._request_preview(active.request_id),
            )
            active.phase = TelegramTurnPhase.FINALIZING
            if active.terminal_received or active.committed_turn_id is not None:
                await self._render_delivery_incomplete(active)
            else:
                await self._render_unknown(active)
        finally:
            if active.stop_status != TurnCancelStatus.CANCELLED.value:
                self.release(active)
            logger.debug(
                "telegram turn released: chat_id={} session_id={} request_id={} cancelled={}",
                active.chat_id,
                active.session_id,
                self._request_preview(active.request_id),
                cancelled,
            )

    async def shutdown(self) -> None:
        """Reject new turns and finish all flow-owned work within the grace."""
        self._closing = True
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._shutdown_grace_seconds
        terminal_budget = min(
            1.0,
            self._shutdown_grace_seconds / 2,
        )
        drain_deadline = deadline - terminal_budget
        actives = list({
            id(active): active
            for active in self._active_by_chat.values()
        }.values())
        current = asyncio.current_task()
        owned_tasks: set[asyncio.Task] = set()
        notice_tasks: set[asyncio.Task[None]] = set()
        try:
            for active in actives:
                if active.phase is not TelegramTurnPhase.FINALIZING:
                    self._ensure_stop_task(active)
            owned_tasks = {
                task
                for active in actives
                for task in (active.task, active.stop_task)
                if task is not None and task is not current and not task.done()
            }
            owned_tasks.update(
                task
                for task in self._owned_stop_tasks
                if task is not current and not task.done()
            )
            pending: set[asyncio.Task] = set()
            if owned_tasks:
                _, pending = await asyncio.wait(
                    owned_tasks,
                    timeout=max(0.0, drain_deadline - loop.time()),
                )
            timed_out = [
                active
                for active in actives
                if (
                    active.task in pending
                    or (
                        active.stop_task in pending
                        and active.stop_status == TurnCancelStatus.CANCELLED.value
                    )
                )
            ]
            for task in pending:
                task.cancel()
            if pending:
                cancellation_budget = min(
                    0.05,
                    max(0.0, deadline - loop.time()) / 2,
                )
                _, pending = await asyncio.wait(
                    pending,
                    timeout=cancellation_budget,
                )

            for active in timed_out:
                if active.task in pending or active.stop_task in pending:
                    logger.warning(
                        "telegram shutdown skipped duplicate terminal notice "
                        "because prior cleanup is still cancelling: "
                        "chat_id={} session_id={} request_id={}",
                        active.chat_id,
                        active.session_id,
                        self._request_preview(active.request_id),
                    )
                    continue
                if active.stop_status == TurnCancelStatus.CANCELLED.value:
                    notice = self._render_stopped(active)
                elif active.terminal_received or active.committed_turn_id is not None:
                    notice = self._render_delivery_incomplete(active)
                else:
                    notice = self._render_unknown(active)
                notice_tasks.add(asyncio.create_task(notice))

            if notice_tasks:
                _, pending_notices = await asyncio.wait(
                    notice_tasks,
                    timeout=max(0.0, deadline - loop.time()),
                )
                for task in pending_notices:
                    task.cancel()
                pending.update(pending_notices)
            for task in pending:
                task.cancel()
            if pending and loop.time() < deadline:
                await asyncio.wait(
                    pending,
                    timeout=max(0.0, deadline - loop.time()),
                )
        finally:
            remaining_tasks = {
                task
                for task in owned_tasks | notice_tasks
                if not task.done()
            }
            for task in remaining_tasks:
                task.cancel()
            if remaining_tasks:
                await asyncio.sleep(0)
            for task in owned_tasks | notice_tasks:
                if task.done() and not task.cancelled():
                    try:
                        task.result()
                    except Exception:
                        logger.exception(
                            "telegram shutdown task failed during cleanup"
                        )
            still_pending = sum(
                not task.done()
                for task in owned_tasks | notice_tasks
            )
            if still_pending:
                logger.warning(
                    "telegram shutdown left cancelling tasks after grace: count={}",
                    still_pending,
                )
            for active in actives:
                self.release(active)
            self._active_by_chat.clear()
            self._active_by_session.clear()
            self._owned_stop_tasks.clear()

    async def _run_stream(
        self,
        client: AgentClient,
        active: ActiveTelegramTurn,
        text: str,
    ) -> None:
        saw_done = False
        try:
            async for event in client.stream(
                active.session_id,
                text,
                request_id=active.request_id,
            ):
                active.stream_event_received = True
                if event.kind == StreamEventKind.TEXT:
                    active.accumulated_text += event.content
                    if active.streaming:
                        await self._render_progress(active)
                    continue
                if event.kind == StreamEventKind.DONE:
                    saw_done = True
                    active.phase = TelegramTurnPhase.FINALIZING
                    active.terminal_received = True
                    active.committed_turn_id = event.committed_turn_id
                    self._sync_active_session(active, event.active_session)
                    final_text = event.content or active.accumulated_text
                    await self._render_success(
                        active,
                        final_text,
                        committed_turn_id=event.committed_turn_id,
                    )
                    break
                if event.kind == StreamEventKind.ERROR:
                    active.transport_finished = True
                    if await self._is_confirmed_stop(active):
                        return
                    logger.warning(
                        "telegram stream returned error: chat_id={} session_id={} request_id={} error_code={} status_code={}",
                        active.chat_id,
                        active.session_id,
                        self._request_preview(active.request_id),
                        event.error_code,
                        event.status_code,
                    )
                    active.phase = TelegramTurnPhase.FINALIZING
                    await self._render_failure(active)
                    return
        finally:
            active.transport_finished = True
        if not saw_done:
            if await self._is_confirmed_stop(active):
                return
            logger.warning(
                "telegram stream ended without DONE: chat_id={} session_id={} request_id={}",
                active.chat_id,
                active.session_id,
                self._request_preview(active.request_id),
            )
            active.phase = TelegramTurnPhase.FINALIZING
            await self._render_unknown(active)

    def _sync_active_session(
        self,
        active: ActiveTelegramTurn,
        session_id: object,
    ) -> None:
        """Propagate a backend-confirmed terminal session locator to the adapter."""
        target_session_id = str(session_id or "").strip()
        callback = self._active_session_callback
        if not target_session_id or callback is None:
            return
        try:
            callback(active, target_session_id)
        except Exception:
            logger.exception(
                "telegram active-session callback failed: "
                "chat_id={} source_session_id={} target_session_id={} request_id={}",
                active.chat_id,
                active.session_id,
                target_session_id,
                self._request_preview(active.request_id),
            )

    async def _render_progress(self, active: ActiveTelegramTurn) -> None:
        if not active.accumulated_text or active.placeholder_message_id is None:
            return
        projected = project_rp_text(active.accumulated_text, streaming=True)
        rendered = render_markdown_to_telegram_html(projected)
        if not rendered or len(rendered) > _TELEGRAM_MAX_MESSAGE_LENGTH:
            return
        now = self._clock()
        pending_chars = len(rendered) - len(active.rendered_sent_text)
        if active.progress_edit_attempted:
            elapsed = now - active.last_edit_at
            if elapsed < self._stream_edit_interval and pending_chars < self._stream_edit_min_chars:
                return
        if rendered == active.rendered_sent_text:
            return
        edited = await self._presenter.edit_html(
            active.chat_id,
            active.placeholder_message_id,
            rendered,
        )
        active.last_edit_at = now
        active.progress_edit_attempted = True
        if edited:
            active.rendered_sent_text = rendered

    async def _render_success(
        self,
        active: ActiveTelegramTurn,
        text: str,
        *,
        committed_turn_id: int | None = None,
    ) -> None:
        display_text = project_rp_text(text, streaming=False) or _EMPTY_REPLY_TEXT
        rendered = render_markdown_to_telegram_html(display_text)
        await self._clear_terminal_controls(active)
        chunks = chunk_rendered_text(rendered)
        delivered = await self._deliver_chunks(active, chunks)
        if not delivered:
            logger.warning(
                "telegram committed reply delivery incomplete: chat_id={} session_id={} request_id={} committed_turn_id={}",
                active.chat_id,
                active.session_id,
                self._request_preview(active.request_id),
                committed_turn_id,
            )
            await self._render_delivery_incomplete(active)

    async def _deliver_chunks(self, active: ActiveTelegramTurn, chunks: list[str]) -> bool:
        if not chunks:
            chunks = [_EMPTY_REPLY_TEXT]
        message_id = active.placeholder_message_id
        start_index = 0
        if message_id is not None:
            first = chunks[0]
            if first == active.rendered_sent_text:
                first_delivered = True
            else:
                first_delivered = await self._presenter.edit_html(
                    active.chat_id,
                    message_id,
                    first,
                    terminal=True,
                )
            if first_delivered:
                active.rendered_sent_text = first
                start_index = 1
            else:
                sent_id = await self._presenter.send_html(
                    active.chat_id,
                    first,
                    terminal=True,
                )
                if sent_id is None:
                    return False
                start_index = 1
                await self._presenter.delete_message(active.chat_id, message_id)

        for chunk in chunks[start_index:]:
            sent_id = await self._presenter.send_html(
                active.chat_id,
                chunk,
                terminal=True,
            )
            if sent_id is None:
                return False
        return True

    async def _render_failure(self, active: ActiveTelegramTurn) -> None:
        await self._clear_terminal_controls(active)
        message_id = active.placeholder_message_id
        if message_id is not None:
            edited = await self._presenter.edit_html(
                active.chat_id,
                message_id,
                _FAILURE_TEXT,
                terminal=True,
            )
            if edited:
                active.rendered_sent_text = _FAILURE_TEXT
                return
        await self._presenter.send_html(
            active.chat_id,
            _FAILURE_TEXT,
            terminal=True,
        )

    async def _render_stopped(self, active: ActiveTelegramTurn) -> None:
        await self._clear_terminal_controls(active)
        message_id = active.placeholder_message_id
        if message_id is not None:
            edited = await self._presenter.edit_html(
                active.chat_id,
                message_id,
                _STOPPED_TEXT,
                terminal=True,
            )
            if edited:
                active.rendered_sent_text = _STOPPED_TEXT
                return
        await self._presenter.send_html(
            active.chat_id,
            _STOPPED_TEXT,
            terminal=True,
        )

    async def _render_unknown(self, active: ActiveTelegramTurn) -> None:
        await self._render_terminal_notice(active, _UNKNOWN_STATE_TEXT)

    async def _render_delivery_incomplete(self, active: ActiveTelegramTurn) -> None:
        await self._render_terminal_notice(
            active,
            _COMMITTED_DELIVERY_FAILURE_TEXT,
        )

    async def _render_terminal_notice(
        self,
        active: ActiveTelegramTurn,
        text: str,
    ) -> None:
        await self._clear_terminal_controls(active)
        message_id = active.placeholder_message_id
        if message_id is not None:
            edited = await self._presenter.edit_html(
                active.chat_id,
                message_id,
                text,
                terminal=True,
            )
            if edited:
                active.rendered_sent_text = text
                return
        await self._presenter.send_html(
            active.chat_id,
            text,
            terminal=True,
        )

    async def _clear_terminal_controls(self, active: ActiveTelegramTurn) -> None:
        if self._terminal_cleanup is not None:
            self._terminal_cleanup(active)
        if active.placeholder_message_id is not None:
            await self._presenter.clear_reply_markup(
                active.chat_id,
                active.placeholder_message_id,
            )

    @staticmethod
    async def _is_confirmed_stop(active: ActiveTelegramTurn) -> bool:
        if active.stop_task is not None and not active.stop_task.done():
            await asyncio.shield(active.stop_task)
        return active.stop_status == TurnCancelStatus.CANCELLED.value

    def _owns(self, active: ActiveTelegramTurn) -> bool:
        return (
            self._same_request(self._active_by_chat.get(active.chat_id), active)
            and self._same_request(self._active_by_session.get(active.session_id), active)
        )

    @staticmethod
    def _same_request(current: ActiveTelegramTurn | None, expected: ActiveTelegramTurn) -> bool:
        return current is expected and current.request_id == expected.request_id

    @staticmethod
    def _request_preview(request_id: str) -> str:
        return request_id[:11]


__all__ = [
    "ActiveTelegramTurn",
    "TelegramTurnBusyReason",
    "TelegramTurnFlow",
    "TelegramTurnPhase",
    "TelegramTurnPresenter",
    "TelegramTurnReservation",
]
