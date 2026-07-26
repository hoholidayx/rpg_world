from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from rpg_core.agent.protocol import AgentStreamEvent, StreamEventKind

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
        self.fail_terminal_send_after: int | None = None
        self.terminal_send_attempts = 0
        self.edit_gate: asyncio.Event | None = None
        self.clear_gate: asyncio.Event | None = None

    async def send_html(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: object | None = None,
        terminal: bool = False,
    ) -> int | None:
        del reply_markup
        if terminal:
            self.terminal_send_attempts += 1
            if (
                self.fail_terminal_send_after is not None
                and self.terminal_send_attempts > self.fail_terminal_send_after
            ):
                return None
        if self.fail_send:
            return None
        message_id = self.next_message_id
        self.next_message_id += 1
        self.sent.append((chat_id, text, message_id))
        return message_id

    async def edit_html(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        *,
        terminal: bool = False,
    ) -> bool:
        del terminal
        if self.edit_gate is not None:
            gate = self.edit_gate
            self.edit_gate = None
            await gate.wait()
        self.edited.append((chat_id, message_id, text))
        return not self.fail_edit

    async def delete_message(self, chat_id: str, message_id: int) -> bool:
        self.deleted.append((chat_id, message_id))
        return True

    async def clear_reply_markup(self, chat_id: str, message_id: int) -> bool:
        self.cleared_markup.append((chat_id, message_id))
        if self.clear_gate is not None:
            gate = self.clear_gate
            self.clear_gate = None
            await gate.wait()
        return True


class _Agent:
    def __init__(self, events: list[AgentStreamEvent] | None = None) -> None:
        self.events = events or []
        self.stream_calls: list[tuple[str, str, str | None]] = []
        self.send_calls: list[tuple[str, str]] = []
        self.stream_gate: asyncio.Event | None = None
        self.stop_status = "cancelled"
        self.stop_calls: list[tuple[str, str | None]] = []
        self.stop_gate: asyncio.Event | None = None

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
        if self.stop_gate is not None:
            await self.stop_gate.wait()
        return {"status": self.stop_status, "session_id": session_id, "request_id": request_id}


def _flow(
    presenter: _Presenter,
    agent: _Agent,
    *,
    streaming: bool = True,
    clock=lambda: 100.0,  # noqa: B008
    shutdown_grace_seconds: float = 0.05,
    stop_registration_grace_seconds: float = 0.05,
    active_session_callback=None,  # noqa: ANN001
) -> TelegramTurnFlow:
    return TelegramTurnFlow(
        presenter=presenter,
        streaming=streaming,
        stream_edit_interval_seconds=0.8,
        stream_edit_min_chars=24,
        clock=clock,
        request_id_factory=lambda: "tg_1234567890abcdef",
        agent_client=agent,  # type: ignore[arg-type]
        shutdown_grace_seconds=shutdown_grace_seconds,
        stop_registration_grace_seconds=stop_registration_grace_seconds,
        active_session_callback=active_session_callback,
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
    presenter = _Presenter()
    flow = _flow(
        presenter,
        _Agent([AgentStreamEvent(kind=StreamEventKind.ERROR, content="bad")]),
    )
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert presenter.edited[-1][2] == "处理消息失败，请稍后重试。"
    assert flow.busy_reason("1", "s1") is None


async def test_missing_done_renders_unknown_state_warning() -> None:
    presenter = _Presenter()
    flow = _flow(
        presenter,
        _Agent([AgentStreamEvent(kind=StreamEventKind.TEXT, content="partial")]),
    )
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert "状态暂时无法确认" in presenter.edited[-1][2]


async def test_empty_done_uses_visible_completion_message() -> None:
    presenter = _Presenter()
    flow = _flow(presenter, _Agent([AgentStreamEvent(kind=StreamEventKind.DONE)]))
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert presenter.edited[-1][2] == "本轮已完成，但没有返回可显示的文本。"


async def test_non_stream_runs_in_same_reservation_model() -> None:
    presenter = _Presenter()
    session_updates: list[tuple[str, str]] = []
    agent = _Agent([
        AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content="reply:go",
            active_session="s2",
        )
    ])
    flow = _flow(
        presenter,
        agent,
        streaming=False,
        active_session_callback=(
            lambda active, session_id: session_updates.append(
                (active.chat_id, session_id)
            )
        ),
    )
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert agent.send_calls == []
    assert agent.stream_calls == [("s1", "go", "tg_1234567890abcdef")]
    assert presenter.edited[-1][2] == "reply:go"
    assert session_updates == [("1", "s2")]


async def test_finalizing_remains_busy_until_delivery_finishes() -> None:
    presenter = _Presenter()
    edit_gate = asyncio.Event()
    presenter.edit_gate = edit_gate
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

    edit_gate.set()
    await task
    assert flow.busy_reason("1", "s1") is None


async def test_terminal_action_is_invalidated_before_markup_cleanup_await() -> None:
    presenter = _Presenter()
    clear_gate = asyncio.Event()
    presenter.clear_gate = clear_gate
    cleanup_calls: list[str] = []
    flow = TelegramTurnFlow(
        presenter=presenter,
        streaming=True,
        stream_edit_interval_seconds=0,
        stream_edit_min_chars=1,
        request_id_factory=lambda: "tg_1234567890abcdef",
        agent_client=_Agent([
            AgentStreamEvent(kind=StreamEventKind.DONE, content="done")
        ]),  # type: ignore[arg-type]
        terminal_cleanup=lambda active: cleanup_calls.append(active.request_id),
    )
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)

    while not presenter.cleared_markup:
        await asyncio.sleep(0)

    assert cleanup_calls == ["tg_1234567890abcdef"]
    assert not task.done()
    clear_gate.set()
    await task


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
    assert agent.stop_calls == [("s1", "tg_1234567890abcdef")]
    assert flow.busy_reason("1", "s1") == TelegramTurnBusyReason.CLOSING
    assert all(item[1] != "处理消息失败，请稍后重试。" for item in presenter.sent)
    assert presenter.edited[-1][2] == "已停止"


async def test_shutdown_finishes_confirmed_stop_cleanup_owned_by_flow() -> None:
    presenter = _Presenter()
    presenter.clear_gate = asyncio.Event()
    agent = _Agent()
    agent.stream_gate = asyncio.Event()
    flow = _flow(presenter, agent, shutdown_grace_seconds=0.001)
    active = flow.reserve("1", "s1").active
    assert active is not None
    turn_task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, turn_task)
    await asyncio.sleep(0)

    stop_waiter = asyncio.create_task(flow.request_stop("1"))
    while not presenter.cleared_markup:
        await asyncio.sleep(0)
    assert active.stop_status == "cancelled"
    assert flow.busy_reason("1", "s1") == TelegramTurnBusyReason.CHAT

    await flow.shutdown()
    await asyncio.gather(stop_waiter, return_exceptions=True)

    assert active.stop_task is not None and active.stop_task.cancelled()
    assert presenter.edited[-1][2] == "已停止"


async def test_shutdown_cancels_slow_owned_stop_after_turn_finishes() -> None:
    presenter = _Presenter()
    agent = _Agent([
        AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content="done",
            committed_turn_id=9,
        )
    ])
    agent.stream_gate = asyncio.Event()
    agent.stop_gate = asyncio.Event()
    flow = _flow(presenter, agent, shutdown_grace_seconds=0.001)
    active = flow.reserve("1", "s1").active
    assert active is not None
    turn_task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, turn_task)
    await asyncio.sleep(0)
    stop_waiter = asyncio.create_task(flow.request_stop("1"))
    while not agent.stop_calls:
        await asyncio.sleep(0)

    agent.stream_gate.set()
    await turn_task
    assert flow.busy_reason("1", "s1") is None
    assert active.stop_task is not None and not active.stop_task.done()

    await flow.shutdown()
    await asyncio.gather(stop_waiter, return_exceptions=True)

    assert active.stop_task.cancelled()
    assert presenter.edited[-1][2] == "done"


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
    await asyncio.gather(task, return_exceptions=True)

    assert status == "cancelled"
    assert agent.stop_calls == [("s1", "tg_1234567890abcdef")]
    assert task.cancelled()
    assert presenter.edited[-1][2] == "已停止"
    assert flow.busy_reason("1", "s1") is None


async def test_stop_during_placeholder_prevents_agent_stream_from_starting() -> None:
    class _StartingPresenter(_Presenter):
        def __init__(self) -> None:
            super().__init__()
            self.placeholder_started = asyncio.Event()
            self.placeholder_gate = asyncio.Event()

        async def send_html(
            self,
            chat_id: str,
            text: str,
            *,
            reply_markup: object | None = None,
            terminal: bool = False,
        ) -> int | None:
            if text == "⏳ 正在生成，请稍候…" and not terminal:
                self.placeholder_started.set()
                await self.placeholder_gate.wait()
            return await super().send_html(
                chat_id,
                text,
                reply_markup=reply_markup,
                terminal=terminal,
            )

    presenter = _StartingPresenter()
    agent = _Agent([
        AgentStreamEvent(kind=StreamEventKind.DONE, content="generated"),
    ])
    agent.stop_status = "not_running"
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await presenter.placeholder_started.wait()

    status = await flow.request_stop("1")
    await asyncio.gather(task, return_exceptions=True)

    assert status == "cancelled"
    assert task.cancelled()
    assert agent.stop_calls == []
    assert agent.stream_calls == []
    assert presenter.sent[-1][1] == "已停止"
    assert flow.busy_reason("1", "s1") is None


async def test_buffered_presentation_turn_is_still_stoppable() -> None:
    presenter = _Presenter()
    agent = _Agent()
    agent.stream_gate = asyncio.Event()
    flow = _flow(presenter, agent, streaming=False)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await asyncio.sleep(0)

    status = await flow.request_stop("1")
    await asyncio.gather(task, return_exceptions=True)

    assert status == "cancelled"
    assert agent.stop_calls == [("s1", "tg_1234567890abcdef")]
    assert presenter.edited[-1][2] == "已停止"


async def test_stale_stop_keeps_generation_running() -> None:
    class _RegisteredAgent(_Agent):
        async def stream(
            self,
            session_id: str,
            text: str,
            request_id: str | None = None,
            **_kwargs: object,
        ) -> AsyncIterator[AgentStreamEvent]:
            self.stream_calls.append((session_id, text, request_id))
            yield AgentStreamEvent(
                kind=StreamEventKind.ROUND_START,
                round_index=1,
            )
            if self.stream_gate is not None:
                await self.stream_gate.wait()
            for event in self.events:
                yield event

    presenter = _Presenter()
    agent = _RegisteredAgent([
        AgentStreamEvent(kind=StreamEventKind.DONE, content="done"),
    ])
    agent.stop_status = "stale"
    agent.stream_gate = asyncio.Event()
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    while not active.stream_event_received:
        await asyncio.sleep(0)

    assert await flow.request_stop("1") == "stale"
    assert not task.done()
    agent.stream_gate.set()
    await task
    assert presenter.edited[-1][2] == "done"


async def test_stop_retries_until_running_request_is_registered() -> None:
    class _RegistrationRaceAgent(_Agent):
        async def stop(
            self,
            session_id: str,
            *,
            request_id: str | None = None,
        ) -> dict[str, object]:
            self.stop_calls.append((session_id, request_id))
            status = (
                "not_running"
                if len(self.stop_calls) == 1
                else "cancelled"
            )
            return {
                "status": status,
                "session_id": session_id,
                "request_id": request_id,
            }

    presenter = _Presenter()
    agent = _RegistrationRaceAgent()
    agent.stream_gate = asyncio.Event()
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    while not agent.stream_calls:
        await asyncio.sleep(0)

    status = await flow.request_stop("1")
    await asyncio.gather(task, return_exceptions=True)

    assert status == "cancelled"
    assert agent.stop_calls == [
        ("s1", "tg_1234567890abcdef"),
        ("s1", "tg_1234567890abcdef"),
    ]
    assert task.cancelled()
    assert presenter.edited[-1][2] == "已停止"


async def test_stop_registration_retry_has_bounded_unknown_fallback() -> None:
    presenter = _Presenter()
    agent = _Agent()
    agent.stop_status = "not_running"
    agent.stream_gate = asyncio.Event()
    flow = _flow(
        presenter,
        agent,
        stop_registration_grace_seconds=0.01,
    )
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    while not agent.stream_calls:
        await asyncio.sleep(0)

    status = await asyncio.wait_for(flow.request_stop("1"), timeout=0.1)
    await asyncio.gather(task, return_exceptions=True)

    assert status == "error"
    assert task.cancelled()
    assert agent.stop_calls
    assert "状态暂时无法确认" in presenter.edited[-1][2]
    assert all(item[2] != "已停止" for item in presenter.edited)
    assert flow.busy_reason("1", "s1") is None


async def test_finalizing_turn_rejects_stop_without_agent_call() -> None:
    presenter = _Presenter()
    edit_gate = asyncio.Event()
    presenter.edit_gate = edit_gate
    agent = _Agent([
        AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content="done",
            committed_turn_id=9,
        )
    ])
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await asyncio.sleep(0)
    assert active.phase is TelegramTurnPhase.FINALIZING

    assert await flow.request_stop("1") == "not_running"
    assert agent.stop_calls == []

    edit_gate.set()
    await task
    assert presenter.edited[-1][2] == "done"


async def test_cancelled_stop_waiter_does_not_strand_flow_owned_stop_task() -> None:
    presenter = _Presenter()
    agent = _Agent()
    agent.stream_gate = asyncio.Event()
    agent.stop_gate = asyncio.Event()
    flow = _flow(presenter, agent)
    active = flow.reserve("1", "s1").active
    assert active is not None
    turn_task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, turn_task)
    await asyncio.sleep(0)

    waiter = asyncio.create_task(flow.request_stop("1"))
    while not agent.stop_calls:
        await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)
    assert active.stop_task is not None
    assert not active.stop_task.done()

    agent.stop_gate.set()
    assert await active.stop_task == "cancelled"
    await asyncio.gather(turn_task, return_exceptions=True)
    assert presenter.edited[-1][2] == "已停止"
    assert flow.busy_reason("1", "s1") is None


async def test_shutdown_drains_finalizing_turn_within_grace() -> None:
    presenter = _Presenter()
    edit_gate = asyncio.Event()
    presenter.edit_gate = edit_gate
    agent = _Agent([
        AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content="done",
            committed_turn_id=9,
        )
    ])
    flow = _flow(presenter, agent, shutdown_grace_seconds=0.2)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await asyncio.sleep(0)
    assert active.phase is TelegramTurnPhase.FINALIZING

    shutdown_task = asyncio.create_task(flow.shutdown())
    await asyncio.sleep(0)
    assert not shutdown_task.done()
    assert agent.stop_calls == []
    edit_gate.set()
    await shutdown_task

    assert task.done() and not task.cancelled()
    assert presenter.edited[-1][2] == "done"


async def test_shutdown_timeout_marks_committed_delivery_incomplete() -> None:
    presenter = _Presenter()
    presenter.edit_gate = asyncio.Event()
    agent = _Agent([
        AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content="done",
            committed_turn_id=9,
        )
    ])
    flow = _flow(presenter, agent, shutdown_grace_seconds=0.001)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await asyncio.sleep(0)
    assert active.phase is TelegramTurnPhase.FINALIZING

    await flow.shutdown()

    assert task.cancelled()
    assert "Telegram 投递未完成" in presenter.edited[-1][2]


async def test_shutdown_grace_bounds_blocked_terminal_fallback() -> None:
    class _BlockedTerminalPresenter(_Presenter):
        def __init__(self) -> None:
            super().__init__()
            self.terminal_gate = asyncio.Event()

        async def edit_html(
            self,
            chat_id: str,
            message_id: int,
            text: str,
            *,
            terminal: bool = False,
        ) -> bool:
            if terminal:
                await self.terminal_gate.wait()
            return await super().edit_html(
                chat_id,
                message_id,
                text,
                terminal=terminal,
            )

        async def send_html(
            self,
            chat_id: str,
            text: str,
            *,
            reply_markup: object | None = None,
            terminal: bool = False,
        ) -> int | None:
            if terminal:
                await self.terminal_gate.wait()
            return await super().send_html(
                chat_id,
                text,
                reply_markup=reply_markup,
                terminal=terminal,
            )

    presenter = _BlockedTerminalPresenter()
    agent = _Agent([
        AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content="done",
            committed_turn_id=9,
        )
    ])
    flow = _flow(presenter, agent, shutdown_grace_seconds=0.01)
    active = flow.reserve("1", "s1").active
    assert active is not None
    task = asyncio.create_task(flow.run(active, "go"))
    flow.attach_task(active, task)
    await asyncio.sleep(0)
    assert active.phase is TelegramTurnPhase.FINALIZING

    await asyncio.wait_for(flow.shutdown(), timeout=0.1)

    assert task.cancelled()
    assert flow.busy_reason("1", "s1") == TelegramTurnBusyReason.CLOSING


async def test_partial_committed_delivery_updates_placeholder_with_notice() -> None:
    presenter = _Presenter()
    presenter.fail_terminal_send_after = 0
    text = "x" * 5000
    flow = _flow(
        presenter,
        _Agent([
            AgentStreamEvent(
                kind=StreamEventKind.DONE,
                content=text,
                committed_turn_id=9,
            )
        ]),
    )
    active = flow.reserve("1", "s1").active
    assert active is not None

    await flow.run(active, "go")

    assert "Telegram 投递未完成" in presenter.edited[-1][2]


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
