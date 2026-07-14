from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind

from channels.telegram.turn_flow import (
    TelegramTurnBusyReason,
    TelegramTurnFlow,
    TelegramTurnPhase,
)


class _Presenter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, int]] = []
        self.edited: list[tuple[str, int, str]] = []
        self.deleted: list[tuple[str, int]] = []
        self.cleared_markup: list[tuple[str, int]] = []
        self.next_message_id = 1
        self.fail_send = False
        self.fail_edit = False
        self.edit_gate: asyncio.Event | None = None

    async def send_html(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: object | None = None,
    ) -> int | None:
        if self.fail_send:
            return None
        message_id = self.next_message_id
        self.next_message_id += 1
        self.sent.append((chat_id, text, message_id))
        return message_id

    async def edit_html(self, chat_id: str, message_id: int, text: str) -> bool:
        if self.edit_gate is not None:
            await self.edit_gate.wait()
        self.edited.append((chat_id, message_id, text))
        return not self.fail_edit

    async def delete_message(self, chat_id: str, message_id: int) -> bool:
        self.deleted.append((chat_id, message_id))
        return True

    async def clear_reply_markup(self, chat_id: str, message_id: int) -> bool:
        self.cleared_markup.append((chat_id, message_id))
        return True


class _Agent:
    def __init__(self, events: list[AgentStreamEvent] | None = None) -> None:
        self.events = events or []
        self.stream_calls: list[tuple[str, str, str | None]] = []
        self.send_calls: list[tuple[str, str]] = []
        self.stream_gate: asyncio.Event | None = None
        self.stop_status = "cancelled"
        self.stop_calls: list[tuple[str, str | None]] = []

    async def stream(
        self,
        session_id: str,
        text: str,
        request_id: str | None = None,
        **_kwargs: object,
    ) -> AsyncIterator[AgentStreamEvent]:
        self.stream_calls.append((session_id, text, request_id))
        if self.stream_gate is not None:
            await self.stream_gate.wait()
        for event in self.events:
            yield event

    async def send(self, session_id: str, text: str, **_kwargs: object) -> dict[str, object]:
        self.send_calls.append((session_id, text))
        return {"reply": f"reply:{text}"}

    async def stop(self, session_id: str, *, request_id: str | None = None) -> dict[str, object]:
        self.stop_calls.append((session_id, request_id))
        return {"status": self.stop_status, "session_id": session_id, "request_id": request_id}


def _flow(
    presenter: _Presenter,
    agent: _Agent,
    *,
    streaming: bool = True,
    clock=lambda: 100.0,  # noqa: B008
) -> TelegramTurnFlow:
    return TelegramTurnFlow(
        presenter=presenter,
        streaming=streaming,
        stream_edit_interval_seconds=0.8,
        stream_edit_min_chars=24,
        clock=clock,
        request_id_factory=lambda: "tg_1234567890abcdef",
        agent_client=agent,  # type: ignore[arg-type]
    )


def test_reservation_blocks_same_chat_and_same_session() -> None:
    flow = _flow(_Presenter(), _Agent())

    first = flow.reserve("chat-1", "session-1")
    same_chat = flow.reserve("chat-1", "session-2")
    same_session = flow.reserve("chat-2", "session-1")
    independent = flow.reserve("chat-2", "session-2")

    assert first.accepted
    assert same_chat.busy_reason == TelegramTurnBusyReason.CHAT
    assert same_session.busy_reason == TelegramTurnBusyReason.SESSION
    assert independent.accepted


async def test_stream_uses_request_id_and_releases_after_done() -> None:
    presenter = _Presenter()
    agent = _Agent([
        AgentStreamEvent(kind=StreamEventKind.TEXT, content="Hello "),
        AgentStreamEvent(kind=StreamEventKind.DONE, content="Hello World", committed_turn_id=7),
    ])
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert agent.stream_calls == [("s1", "go", "tg_1234567890abcdef")]
    assert presenter.sent[0][1] == "⏳ 正在生成，请稍候…"
    assert presenter.edited[0][2] == "Hello "
    assert presenter.edited[-1][2] == "Hello World"
    assert flow.busy_reason("1", "s1") is None


async def test_progress_is_throttled_but_done_flushes_final_text() -> None:
    presenter = _Presenter()
    agent = _Agent([
        AgentStreamEvent(kind=StreamEventKind.TEXT, content="A"),
        AgentStreamEvent(kind=StreamEventKind.TEXT, content="B"),
        AgentStreamEvent(kind=StreamEventKind.DONE, content="AB"),
    ])
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert [item[2] for item in presenter.edited] == ["A", "AB"]


async def test_failed_first_progress_edit_is_still_throttled() -> None:
    presenter = _Presenter()
    presenter.fail_edit = True
    agent = _Agent([
        AgentStreamEvent(kind=StreamEventKind.TEXT, content="A"),
        AgentStreamEvent(kind=StreamEventKind.TEXT, content="B"),
        AgentStreamEvent(kind=StreamEventKind.DONE, content="AB"),
    ])
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert [item[2] for item in presenter.edited] == ["A", "AB"]


async def test_error_and_missing_done_render_failure() -> None:
    for events in (
        [AgentStreamEvent(kind=StreamEventKind.ERROR, content="bad")],
        [AgentStreamEvent(kind=StreamEventKind.TEXT, content="partial")],
    ):
        presenter = _Presenter()
        flow = _flow(presenter, _Agent(events))
        active = flow.reserve("1", "s1").active
        assert active is not None

        await flow.run(active, "go")

        assert presenter.edited[-1][2] == "处理消息失败，请稍后重试。"
        assert flow.busy_reason("1", "s1") is None


async def test_empty_done_uses_visible_completion_message() -> None:
    presenter = _Presenter()
    flow = _flow(presenter, _Agent([AgentStreamEvent(kind=StreamEventKind.DONE)]))
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert presenter.edited[-1][2] == "本轮已完成，但没有返回可显示的文本。"


async def test_non_stream_runs_in_same_reservation_model() -> None:
    presenter = _Presenter()
    agent = _Agent()
    flow = _flow(presenter, agent, streaming=False)
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert agent.send_calls == [("s1", "go")]
    assert agent.stream_calls == []
    assert presenter.edited[-1][2] == "reply:go"


async def test_finalizing_remains_busy_until_delivery_finishes() -> None:
    presenter = _Presenter()
    presenter.edit_gate = asyncio.Event()
    flow = _flow(
        presenter,
        _Agent([AgentStreamEvent(kind=StreamEventKind.DONE, content="done")]),
    )
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)

    await asyncio.sleep(0)
    assert active.phase == TelegramTurnPhase.FINALIZING
    assert flow.busy_reason("1", "s1") == TelegramTurnBusyReason.CHAT

    presenter.edit_gate.set()
    await task
    assert flow.busy_reason("1", "s1") is None


def test_old_release_cannot_clear_new_request() -> None:
    counter = iter(("old", "new"))
    presenter = _Presenter()
    flow = TelegramTurnFlow(
        presenter=presenter,
        streaming=True,
        stream_edit_interval_seconds=0,
        stream_edit_min_chars=1,
        request_id_factory=lambda: next(counter),
        agent_client=_Agent(),  # type: ignore[arg-type]
    )
    old = flow.reserve("1", "s1").active
    assert old is not None
    flow.release(old)
    new = flow.reserve("1", "s1").active
    assert new is not None

    flow.release(old)

    assert flow.busy_reason("1", "s1") == TelegramTurnBusyReason.CHAT


async def test_long_reply_edits_first_chunk_and_sends_remaining_chunks() -> None:
    presenter = _Presenter()
    text = "x" * 5000
    flow = _flow(presenter, _Agent([AgentStreamEvent(kind=StreamEventKind.DONE, content=text)]))
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert len(presenter.edited[-1][2]) == 4096
    assert presenter.sent[-1][1] == "x" * (5000 - 4096)


async def test_final_edit_failure_deletes_placeholder_and_sends_full_reply() -> None:
    presenter = _Presenter()
    presenter.fail_edit = True
    flow = _flow(
        presenter,
        _Agent([AgentStreamEvent(kind=StreamEventKind.DONE, content="done")]),
    )
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert presenter.deleted == [("1", 1)]
    assert presenter.sent[-1][1] == "done"


async def test_shutdown_cancels_tasks_and_clears_indexes_without_failure_message() -> None:
    presenter = _Presenter()
    agent = _Agent()
    agent.stream_gate = asyncio.Event()
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await asyncio.sleep(0)

    await flow.shutdown()

    assert task.cancelled()
    assert flow.busy_reason("1", "s1") == TelegramTurnBusyReason.CLOSING
    assert all(item[1] != "处理消息失败，请稍后重试。" for item in presenter.sent)


async def test_stream_projects_rp_tags_and_tolerates_partial_open_tag() -> None:
    presenter = _Presenter()
    agent = _Agent([
        AgentStreamEvent(kind=StreamEventKind.TEXT, content='<rp-character name="Ali'),
        AgentStreamEvent(kind=StreamEventKind.TEXT, content='ce">你好'),
        AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content='<rp-character name="Alice">你好</rp-character>',
        ),
    ])
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert presenter.edited[-1][2] == "Alice：你好"
    assert all("rp-character" not in item[2] for item in presenter.edited)


async def test_cancelled_stop_uses_exact_request_and_stops_local_task() -> None:
    presenter = _Presenter()
    agent = _Agent()
    agent.stream_gate = asyncio.Event()
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await asyncio.sleep(0)

    status = await flow.request_stop("1")

    assert status == "cancelled"
    assert agent.stop_calls == [("s1", "tg_1234567890abcdef")]
    assert task.cancelled()
    assert presenter.edited[-1][2] == "已停止"
    assert flow.busy_reason("1", "s1") is None


async def test_stale_stop_keeps_generation_running() -> None:
    presenter = _Presenter()
    agent = _Agent([AgentStreamEvent(kind=StreamEventKind.DONE, content="done")])
    agent.stop_status = "stale"
    agent.stream_gate = asyncio.Event()
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await asyncio.sleep(0)

    assert await flow.request_stop("1") == "stale"
    assert not task.done()
    agent.stream_gate.set()
    await task
    assert presenter.edited[-1][2] == "done"


async def test_not_running_stop_without_active_turn() -> None:
    flow = _flow(_Presenter(), _Agent())

    assert await flow.request_stop("missing") == "not_running"


async def test_confirmed_stop_does_not_render_missing_done_failure() -> None:
    class _RaceAgent(_Agent):
        def __init__(self) -> None:
            super().__init__()
            self.stream_gate = asyncio.Event()

        async def stream(self, session_id, text, request_id=None, **_kwargs):  # noqa: ANN001
            self.stream_calls.append((session_id, text, request_id))
            await self.stream_gate.wait()
            if False:
                yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="")

        async def stop(self, session_id: str, *, request_id: str | None = None) -> dict[str, object]:
            self.stop_calls.append((session_id, request_id))
            self.stream_gate.set()
            await asyncio.sleep(0)
            return {"status": "cancelled", "session_id": session_id, "request_id": request_id}

    presenter = _Presenter()
    agent = _RaceAgent()
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await asyncio.sleep(0)

    assert await flow.request_stop("1") == "cancelled"
    assert all(item[2] != "处理消息失败，请稍后重试。" for item in presenter.edited)
    assert presenter.edited[-1][2] == "已停止"
