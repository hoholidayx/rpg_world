"""Telegram process composition-root tests."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

import run_telegram


def _bot(*, enabled: bool = True, reference_menu_enabled: bool = False):
    return SimpleNamespace(
        enabled=enabled,
        reference_menu_enabled=reference_menu_enabled,
    )


def _settings(*bots):
    return SimpleNamespace(
        telegram_bots=list(bots),
        logging=object(),
    )


@pytest.mark.asyncio
async def test_main_skips_gateway_when_no_enabled_bot_requests_references(
    monkeypatch,
):
    settings = _settings(
        _bot(enabled=True, reference_menu_enabled=False),
        _bot(enabled=False, reference_menu_enabled=True),
    )
    runner_calls = []

    def unexpected_gateway():
        raise AssertionError("Gateway must not be created without a reference menu")

    async def fake_runner(*, reference_reader, configure_logging):
        runner_calls.append((reference_reader, configure_logging))
        return 17

    monkeypatch.setattr(run_telegram, "channels_settings", settings)
    monkeypatch.setattr(
        run_telegram,
        "configure_process_logging",
        lambda _name, _settings: None,
    )
    monkeypatch.setattr(
        run_telegram,
        "get_data_service_gateway",
        unexpected_gateway,
    )
    monkeypatch.setattr(run_telegram, "_telegram_main", fake_runner)

    assert await run_telegram.main() == 17
    assert runner_calls == [(None, False)]


@pytest.mark.asyncio
async def test_multiple_reference_bots_share_one_reader(monkeypatch):
    settings = _settings(
        _bot(enabled=True, reference_menu_enabled=True),
        _bot(enabled=True, reference_menu_enabled=True),
        _bot(enabled=True, reference_menu_enabled=False),
    )
    gateway = SimpleNamespace(
        close=lambda: None,
        close_thread_connection=lambda: None,
    )
    reader = SimpleNamespace(aclose=_noop_async)
    gateway_calls = []
    build_calls = []
    main_thread_id = threading.get_ident()
    build_thread_ids = []
    runner_readers = []

    def fake_gateway():
        gateway_calls.append("gateway")
        return gateway

    def fake_build(candidate):
        build_calls.append(candidate)
        build_thread_ids.append(threading.get_ident())
        return reader

    async def fake_runner(*, reference_reader, configure_logging):
        assert configure_logging is False
        runner_readers.append(reference_reader)
        return 0

    monkeypatch.setattr(run_telegram, "channels_settings", settings)
    monkeypatch.setattr(
        run_telegram,
        "configure_process_logging",
        lambda _name, _settings: None,
    )
    monkeypatch.setattr(run_telegram, "get_data_service_gateway", fake_gateway)
    monkeypatch.setattr(run_telegram, "_build_reference_reader", fake_build)
    monkeypatch.setattr(run_telegram, "_telegram_main", fake_runner)

    assert await run_telegram.main() == 0
    assert gateway_calls == ["gateway"]
    assert build_calls == [gateway]
    assert build_thread_ids != [main_thread_id]
    assert runner_readers == [reader]


@pytest.mark.asyncio
async def test_reference_initialization_failure_degrades_to_chat_only(
    monkeypatch,
):
    settings = _settings(_bot(enabled=True, reference_menu_enabled=True))
    events = []

    class FakeGateway:
        def close_thread_connection(self):
            events.append("gateway:close-worker")

        def close(self):
            events.append("gateway:close")

    gateway = FakeGateway()

    def fail_to_build(candidate):
        assert candidate is gateway
        events.append("reader:build")
        raise RuntimeError("reference initialization failed")

    async def fake_runner(*, reference_reader, configure_logging):
        events.append(("runner", reference_reader, configure_logging))
        return 9

    monkeypatch.setattr(run_telegram, "channels_settings", settings)
    monkeypatch.setattr(
        run_telegram,
        "configure_process_logging",
        lambda _name, _settings: None,
    )
    monkeypatch.setattr(
        run_telegram,
        "get_data_service_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        run_telegram,
        "_build_reference_reader",
        fail_to_build,
    )
    monkeypatch.setattr(run_telegram, "_telegram_main", fake_runner)

    assert await run_telegram.main() == 9
    assert events == [
        "reader:build",
        "gateway:close-worker",
        "gateway:close",
        ("runner", None, False),
    ]


@pytest.mark.asyncio
async def test_cancelled_initialization_drains_and_closes_built_reader(
    monkeypatch,
):
    settings = _settings(_bot(enabled=True, reference_menu_enabled=True))
    events = []
    started = threading.Event()
    release = threading.Event()

    class FakeReader:
        async def aclose(self):
            events.append("reader:aclose")

    class FakeGateway:
        def close_thread_connection(self):
            events.append("gateway:close-worker")

        def close(self):
            events.append("gateway:close")

    reader = FakeReader()
    gateway = FakeGateway()

    def blocked_build(candidate):
        assert candidate is gateway
        events.append("reader:build-start")
        started.set()
        release.wait(timeout=3)
        events.append("reader:build-end")
        return reader

    async def unexpected_runner(**_kwargs):
        raise AssertionError("Telegram runner must not start after cancellation")

    monkeypatch.setattr(run_telegram, "channels_settings", settings)
    monkeypatch.setattr(
        run_telegram,
        "configure_process_logging",
        lambda _name, _settings: None,
    )
    monkeypatch.setattr(
        run_telegram,
        "get_data_service_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(run_telegram, "_build_reference_reader", blocked_build)
    monkeypatch.setattr(run_telegram, "_telegram_main", unexpected_runner)

    task = asyncio.create_task(run_telegram.main())
    while not started.is_set():
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0.05)
    assert not task.done()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == [
        "reader:build-start",
        "reader:build-end",
        "gateway:close-worker",
        "reader:aclose",
        "gateway:close",
    ]


@pytest.mark.asyncio
async def test_shutdown_waits_for_runner_then_reader_before_gateway(
    monkeypatch,
):
    settings = _settings(_bot(enabled=True, reference_menu_enabled=True))
    events = []

    class FakeReader:
        async def aclose(self):
            events.append("reader:aclose")

    class FakeGateway:
        def close_thread_connection(self):
            events.append("gateway:close-worker")

        def close(self):
            events.append("gateway:close")

    reader = FakeReader()
    gateway = FakeGateway()

    async def fake_runner(*, reference_reader, configure_logging):
        assert reference_reader is reader
        assert configure_logging is False
        events.extend(("runner:start", "runner:end"))
        return 0

    monkeypatch.setattr(run_telegram, "channels_settings", settings)
    monkeypatch.setattr(
        run_telegram,
        "configure_process_logging",
        lambda _name, _settings: None,
    )
    monkeypatch.setattr(
        run_telegram,
        "get_data_service_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        run_telegram,
        "_build_reference_reader",
        lambda candidate: reader if candidate is gateway else None,
    )
    monkeypatch.setattr(run_telegram, "_telegram_main", fake_runner)

    assert await run_telegram.main() == 0
    assert events == [
        "gateway:close-worker",
        "runner:start",
        "runner:end",
        "reader:aclose",
        "gateway:close",
    ]


@pytest.mark.asyncio
async def test_cancelled_reader_close_still_closes_gateway(monkeypatch):
    settings = _settings(_bot(enabled=True, reference_menu_enabled=True))
    events = []

    class FakeReader:
        async def aclose(self):
            events.append("reader:aclose")
            raise asyncio.CancelledError

    class FakeGateway:
        def close_thread_connection(self):
            events.append("gateway:close-worker")

        def close(self):
            events.append("gateway:close")

    reader = FakeReader()
    gateway = FakeGateway()

    async def fake_runner(*, reference_reader, configure_logging):
        assert reference_reader is reader
        assert configure_logging is False
        return 0

    monkeypatch.setattr(run_telegram, "channels_settings", settings)
    monkeypatch.setattr(
        run_telegram,
        "configure_process_logging",
        lambda _name, _settings: None,
    )
    monkeypatch.setattr(
        run_telegram,
        "get_data_service_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        run_telegram,
        "_build_reference_reader",
        lambda candidate: reader if candidate is gateway else None,
    )
    monkeypatch.setattr(run_telegram, "_telegram_main", fake_runner)

    with pytest.raises(asyncio.CancelledError):
        await run_telegram.main()
    assert events == [
        "gateway:close-worker",
        "reader:aclose",
        "gateway:close",
    ]


@pytest.mark.asyncio
async def test_main_configures_logging_once_and_disables_runner_logging(
    monkeypatch,
):
    settings = _settings()
    logging_calls = []
    runner_flags = []

    def fake_configure(name, logging_settings):
        logging_calls.append((name, logging_settings))

    async def fake_runner(*, reference_reader, configure_logging):
        assert reference_reader is None
        runner_flags.append(configure_logging)
        if configure_logging:
            fake_configure("telegram", settings.logging)
        return 0

    monkeypatch.setattr(run_telegram, "channels_settings", settings)
    monkeypatch.setattr(
        run_telegram,
        "configure_process_logging",
        fake_configure,
    )
    monkeypatch.setattr(run_telegram, "_telegram_main", fake_runner)

    assert await run_telegram.main() == 0
    assert logging_calls == [("telegram", settings.logging)]
    assert runner_flags == [False]


async def _noop_async() -> None:
    return None
