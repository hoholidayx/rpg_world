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
from rpg_core.agent.agent_types import StreamEventKind

from channels.telegram.render import (
    chunk_rendered_text,
    render_markdown_to_telegram_html,
)

_PLACEHOLDER_TEXT = "⏳ 正在生成，请稍候…"
_FAILURE_TEXT = "处理消息失败，请稍后重试。"
_EMPTY_REPLY_TEXT = "本轮已完成，但没有返回可显示的文本。"
_TELEGRAM_MAX_MESSAGE_LENGTH = 4096


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


@dataclass(frozen=True)
class TelegramTurnReservation:
    active: ActiveTelegramTurn | None = None
    busy_reason: TelegramTurnBusyReason | None = None

    @property
    def accepted(self) -> bool:
        return self.active is not None and self.busy_reason is None


class TelegramTurnPresenter(Protocol):
    """Telegram Bot I/O used by the flow after text is rendered to HTML."""

    async def send_html(self, chat_id: str, text: str) -> int | None: ...

    async def edit_html(self, chat_id: str, message_id: int, text: str) -> bool: ...

    async def delete_message(self, chat_id: str, message_id: int) -> bool: ...


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
    ) -> None:
        self._presenter = presenter
        self._streaming = bool(streaming)
        self._stream_edit_interval = max(0.0, float(stream_edit_interval_seconds))
        self._stream_edit_min_chars = max(1, int(stream_edit_min_chars))
        self._clock = clock
        self._request_id_factory = request_id_factory or (lambda: f"tg_{uuid.uuid4().hex}")
        self._agent_client = agent_client
        self._active_by_chat: dict[str, ActiveTelegramTurn] = {}
        self._active_by_session: dict[str, ActiveTelegramTurn] = {}
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

    async def run(self, active: ActiveTelegramTurn, text: str) -> None:
        """Run one reserved turn and guarantee terminal state cleanup."""
        cancelled = False
        try:
            active.placeholder_message_id = await self._presenter.send_html(
                active.chat_id,
                _PLACEHOLDER_TEXT,
            )
            active.phase = TelegramTurnPhase.RUNNING
            client = self._agent_client
            if client is None:
                raise RuntimeError("Agent client is not bound")
            if active.streaming:
                await self._run_stream(client, active, text)
            else:
                await self._run_non_stream(client, active, text)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception:
            logger.exception(
                "telegram turn failed: chat_id={} session_id={} request_id={}",
                active.chat_id,
                active.session_id,
                self._request_preview(active.request_id),
            )
            await self._render_failure(active)
        finally:
            self.release(active)
            logger.debug(
                "telegram turn released: chat_id={} session_id={} request_id={} cancelled={}",
                active.chat_id,
                active.session_id,
                self._request_preview(active.request_id),
                cancelled,
            )

    async def shutdown(self) -> None:
        """Reject new turns, cancel managed tasks, and clear local state."""
        self._closing = True
        current = asyncio.current_task()
        tasks = {
            active.task
            for active in self._active_by_chat.values()
            if active.task is not None and active.task is not current and not active.task.done()
        }
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._active_by_chat.clear()
        self._active_by_session.clear()

    async def _run_stream(
        self,
        client: AgentClient,
        active: ActiveTelegramTurn,
        text: str,
    ) -> None:
        saw_done = False
        async for event in client.stream(
            active.session_id,
            text,
            request_id=active.request_id,
        ):
            if event.kind == StreamEventKind.TEXT:
                active.accumulated_text += event.content
                await self._render_progress(active)
                continue
            if event.kind == StreamEventKind.DONE:
                saw_done = True
                active.phase = TelegramTurnPhase.FINALIZING
                final_text = event.content or active.accumulated_text
                await self._render_success(
                    active,
                    final_text,
                    committed_turn_id=event.committed_turn_id,
                )
                break
            if event.kind == StreamEventKind.ERROR:
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
        if not saw_done:
            logger.warning(
                "telegram stream ended without DONE: chat_id={} session_id={} request_id={}",
                active.chat_id,
                active.session_id,
                self._request_preview(active.request_id),
            )
            active.phase = TelegramTurnPhase.FINALIZING
            await self._render_failure(active)

    async def _run_non_stream(
        self,
        client: AgentClient,
        active: ActiveTelegramTurn,
        text: str,
    ) -> None:
        result = await client.send(active.session_id, text)
        active.phase = TelegramTurnPhase.FINALIZING
        await self._render_success(active, str(result.get("reply", "")))

    async def _render_progress(self, active: ActiveTelegramTurn) -> None:
        if not active.accumulated_text or active.placeholder_message_id is None:
            return
        rendered = render_markdown_to_telegram_html(active.accumulated_text)
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
        display_text = text or _EMPTY_REPLY_TEXT
        rendered = render_markdown_to_telegram_html(display_text)
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
                first_delivered = await self._presenter.edit_html(active.chat_id, message_id, first)
            if first_delivered:
                active.rendered_sent_text = first
                start_index = 1
            else:
                await self._presenter.delete_message(active.chat_id, message_id)

        delivered = True
        for chunk in chunks[start_index:]:
            sent_id = await self._presenter.send_html(active.chat_id, chunk)
            if sent_id is None:
                delivered = False
        return delivered

    async def _render_failure(self, active: ActiveTelegramTurn) -> None:
        message_id = active.placeholder_message_id
        if message_id is not None:
            edited = await self._presenter.edit_html(active.chat_id, message_id, _FAILURE_TEXT)
            if edited:
                active.rendered_sent_text = _FAILURE_TEXT
                return
        await self._presenter.send_html(active.chat_id, _FAILURE_TEXT)

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
