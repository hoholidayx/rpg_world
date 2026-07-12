from __future__ import annotations

import asyncio

import pytest

from commons.errors import TURN_METADATA_INVALID_ERROR_CODE
from rpg_core.agent.agent_types import StreamEventKind, TurnCancelStatus
from rpg_core.agent.loop import AgentReply
from rpg_core.agent.mailbox import AgentMailbox
from rpg_core.agent.turn import TurnRequest
from rpg_core.session import InvalidTurnMetadataError


class _Commands:
    async def dispatch(self, command: str):  # noqa: ANN201
        return command


class _Turns:
    def __init__(self) -> None:
        self.send_started = asyncio.Event()
        self.stream_started = asyncio.Event()
        self.release_send = asyncio.Event()
        self.block_send = False
        self.stream_error: BaseException | None = None
        self.order: list[str] = []

    async def execute_sync(self, request: TurnRequest) -> AgentReply:
        self.order.append("send-start")
        self.send_started.set()
        if self.block_send:
            await self.release_send.wait()
        self.order.append("send-end")
        return AgentReply(text=request.text)

    async def execute_stream(self, request: TurnRequest, event_queue) -> None:  # noqa: ANN001
        del request, event_queue
        self.stream_started.set()
        if self.stream_error is not None:
            raise self.stream_error
        await asyncio.Event().wait()


def _mailbox(turns: _Turns, truncate=lambda _turn_id: {}):  # noqa: ANN001, ANN201
    mailbox = AgentMailbox(
        session_id=lambda: "s_mailbox",
        model=lambda: "test-model",
        turn_service=turns,
        command_dispatcher=_Commands(),
        truncate_history=truncate,
    )
    mailbox.start()
    return mailbox


async def _collect(mailbox: AgentMailbox, request: TurnRequest):
    return [event async for event in mailbox.send_stream(request)]


@pytest.mark.asyncio
async def test_mailbox_surfaces_stream_errors_and_terminates() -> None:
    turns = _Turns()
    turns.stream_error = RuntimeError("boom")
    mailbox = _mailbox(turns)
    try:
        events = await _collect(mailbox, TurnRequest.create("hello"))
        assert len(events) == 1
        assert events[0].kind is StreamEventKind.ERROR
        assert events[0].content == "boom"
    finally:
        await mailbox.close()


@pytest.mark.asyncio
async def test_mailbox_maps_turn_metadata_error_without_prefixing_content() -> None:
    turns = _Turns()
    turns.stream_error = InvalidTurnMetadataError("bad turn metadata")
    mailbox = _mailbox(turns)
    try:
        events = await _collect(mailbox, TurnRequest.create("hello"))
        assert events[0].kind is StreamEventKind.ERROR
        assert events[0].error_code == TURN_METADATA_INVALID_ERROR_CODE
        assert TURN_METADATA_INVALID_ERROR_CODE not in events[0].content
    finally:
        await mailbox.close()


@pytest.mark.asyncio
async def test_mailbox_serializes_truncate_after_send() -> None:
    turns = _Turns()
    turns.block_send = True

    def truncate(turn_id: int) -> dict[str, object]:
        turns.order.append(f"truncate-{turn_id}")
        return {"status": "truncated", "turn_id": turn_id}

    mailbox = _mailbox(turns, truncate)
    try:
        send_task = asyncio.create_task(mailbox.send(TurnRequest.create("go")))
        await turns.send_started.wait()
        truncate_task = asyncio.create_task(mailbox.truncate_history_from_turn(2))
        await asyncio.sleep(0)
        assert not truncate_task.done()
        turns.release_send.set()
        await send_task
        assert await truncate_task == {"status": "truncated", "turn_id": 2}
        assert turns.order == ["send-start", "send-end", "truncate-2"]
    finally:
        await mailbox.close()


@pytest.mark.asyncio
async def test_mailbox_cancels_active_stream_by_request_id() -> None:
    turns = _Turns()
    mailbox = _mailbox(turns)
    collect_task = asyncio.create_task(
        _collect(mailbox, TurnRequest.create("go", request_id="req-active"))
    )
    try:
        await turns.stream_started.wait()
        result = await mailbox.cancel_current_turn("req-active")
        assert result.status is TurnCancelStatus.CANCELLED
        assert await collect_task == []
    finally:
        await mailbox.close()


@pytest.mark.asyncio
async def test_mailbox_rejects_stale_cancel_without_stopping_active_turn() -> None:
    turns = _Turns()
    mailbox = _mailbox(turns)
    collect_task = asyncio.create_task(
        _collect(mailbox, TurnRequest.create("go", request_id="req-new"))
    )
    try:
        await turns.stream_started.wait()
        result = await mailbox.cancel_current_turn("req-old")
        assert result.status is TurnCancelStatus.STALE
        assert not collect_task.done()
        await mailbox.cancel_current_turn("req-new")
        await collect_task
    finally:
        await mailbox.close()


@pytest.mark.asyncio
async def test_mailbox_skips_cancelled_queued_stream() -> None:
    turns = _Turns()
    turns.block_send = True
    mailbox = _mailbox(turns)
    send_task = asyncio.create_task(mailbox.send(TurnRequest.create("first")))
    await turns.send_started.wait()
    collect_task = asyncio.create_task(
        _collect(mailbox, TurnRequest.create("queued", request_id="req-queued"))
    )
    try:
        await asyncio.sleep(0)
        result = await mailbox.cancel_current_turn("req-queued")
        assert result.status is TurnCancelStatus.CANCELLED
        turns.release_send.set()
        await send_task
        assert await collect_task == []
        assert not turns.stream_started.is_set()
    finally:
        turns.release_send.set()
        await mailbox.close()
