from __future__ import annotations

import asyncio
import signal
from threading import Event

import pytest

import run_all
import run_agent
import run_cli
import run_dream
import run_llm
import run_media
import run_play_api
import run_telegram
import run_tts


def _run_all_spec(*, name: str = "agent", port: int = 8010) -> run_all.ServiceSpec:
    return run_all.ServiceSpec(
        name=name,
        module=f"run_{name}",
        listen_address=("127.0.0.1", port),
    )


def test_run_all_uses_distinct_ports_for_every_service():
    specs = run_all._service_specs()

    assert [spec.name for spec in specs] == [
        "llm",
        "agent",
        "dream",
        "media",
        "tts",
        "play_api",
    ]
    assert len({spec.listen_address[1] for spec in specs}) == len(specs)
    run_all._validate_service_ports(specs)


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("/opt/project/.venv/bin/python3.13", "python3.13 -m run_agent"),
        ("Python", "/opt/project/.venv/bin/python -m run_media"),
        ("/usr/local/bin/uv", "uv run python -m run_llm"),
    ],
)
def test_run_all_recognizes_python_and_uv_processes(command, arguments):
    process = run_all.ProcessInfo(pid=123, command=command, arguments=arguments)

    assert run_all._is_python_or_uv_process(process) is True


def test_run_all_rejects_duplicate_service_ports():
    specs = (
        _run_all_spec(name="agent", port=8010),
        _run_all_spec(name="media", port=8010),
    )

    with pytest.raises(run_all.StartupError, match="distinct listen ports"):
        run_all._validate_service_ports(specs)


def test_run_all_terminates_python_listener_before_start(monkeypatch):
    spec = _run_all_spec()
    port_states = iter([True, False])
    signals: list[tuple[int, signal.Signals]] = []
    process = run_all.ProcessInfo(
        pid=321,
        command="python3.13",
        arguments="python3.13 -m run_agent",
    )

    monkeypatch.setattr(run_all, "_port_in_use", lambda _address: next(port_states))
    monkeypatch.setattr(run_all, "_listener_pids", lambda _port: (process.pid,))
    monkeypatch.setattr(run_all, "_process_info", lambda _pid: process)
    monkeypatch.setattr(
        run_all.os,
        "kill",
        lambda pid, signum: signals.append((pid, signum)),
    )

    run_all._clear_occupied_port(spec, timeout=1.0, stop_event=Event())

    assert signals == [(process.pid, signal.SIGTERM)]


def test_run_all_force_kills_python_listener_after_timeout(monkeypatch):
    spec = _run_all_spec()
    releases = iter([False, True])
    signals: list[tuple[int, signal.Signals]] = []
    process = run_all.ProcessInfo(
        pid=654,
        command="Python",
        arguments="/opt/project/.venv/bin/python -m run_agent",
    )

    monkeypatch.setattr(run_all, "_port_in_use", lambda _address: True)
    monkeypatch.setattr(run_all, "_listener_pids", lambda _port: (process.pid,))
    monkeypatch.setattr(run_all, "_process_info", lambda _pid: process)
    monkeypatch.setattr(
        run_all,
        "_wait_for_port_release",
        lambda *_args, **_kwargs: next(releases),
    )
    monkeypatch.setattr(
        run_all.os,
        "kill",
        lambda pid, signum: signals.append((pid, signum)),
    )

    run_all._clear_occupied_port(spec, timeout=1.0, stop_event=Event())

    assert signals == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]


def test_run_all_refuses_to_terminate_other_listener(monkeypatch):
    spec = _run_all_spec()
    process = run_all.ProcessInfo(
        pid=987,
        command="node",
        arguments="node server.js",
    )

    monkeypatch.setattr(run_all, "_port_in_use", lambda _address: True)
    monkeypatch.setattr(run_all, "_listener_pids", lambda _port: (process.pid,))
    monkeypatch.setattr(run_all, "_process_info", lambda _pid: process)
    monkeypatch.setattr(
        run_all.os,
        "kill",
        lambda *_args: pytest.fail("non-Python/uv listener must not be signalled"),
    )

    with pytest.raises(run_all.StartupError, match="not confirmed as Python or uv"):
        run_all._clear_occupied_port(spec, timeout=1.0, stop_event=Event())


def test_run_play_api_main_invokes_uvicorn(monkeypatch):
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    configured: list[tuple[str, object]] = []
    uvicorn_log_config = object()

    def _fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(run_play_api.uvicorn, "run", _fake_run)
    monkeypatch.setattr(
        run_play_api,
        "configure_process_logging",
        lambda name, settings: configured.append((name, settings)),
    )
    monkeypatch.setattr(
        run_play_api,
        "build_uvicorn_log_config",
        lambda _name, _settings: uvicorn_log_config,
    )

    assert run_play_api.main() is None
    assert configured == [("play_api", run_play_api.play_settings.logging)]
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("play_api.main:app",)
    assert kwargs["host"] == run_play_api.play_settings.service.host
    assert kwargs["port"] == run_play_api.play_settings.service.port
    assert kwargs["reload"] == run_play_api.play_settings.service.reload
    assert kwargs["log_level"] == run_play_api.play_settings.logging.log_level.lower()
    assert kwargs["log_config"] is uvicorn_log_config


def test_run_agent_main_invokes_uvicorn(monkeypatch):
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    configured: list[tuple[str, object]] = []
    uvicorn_log_config = object()

    def _fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(run_agent.uvicorn, "run", _fake_run)
    monkeypatch.setattr(
        run_agent,
        "configure_process_logging",
        lambda name, settings: configured.append((name, settings)),
    )
    monkeypatch.setattr(
        run_agent,
        "build_uvicorn_log_config",
        lambda _name, _settings: uvicorn_log_config,
    )

    assert run_agent.main() is None
    assert configured == [("agent", run_agent.agent_service_settings.logging)]
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("agent_service.main:app",)
    assert kwargs["host"] == run_agent.agent_service_settings.service.host
    assert kwargs["port"] == run_agent.agent_service_settings.service.port
    assert kwargs["log_config"] is uvicorn_log_config


@pytest.mark.parametrize(
    ("module", "process_name", "app_path"),
    [
        (run_llm, "llm", "llm_service.main:app"),
        (run_dream, "dream", "dream_service.main:app"),
        (run_media, "media", "media_service.main:app"),
        (run_tts, "tts", "tts_service.main:app"),
    ],
)
def test_service_entrypoint_configures_process_logging_before_uvicorn(
    monkeypatch,
    module,
    process_name,
    app_path,
):
    events: list[tuple[str, object]] = []
    uvicorn_log_config = object()

    monkeypatch.setattr(
        module,
        "configure_process_logging",
        lambda name, settings: events.append(("logging", (name, settings))),
    )
    monkeypatch.setattr(
        module,
        "build_uvicorn_log_config",
        lambda _name, _settings: uvicorn_log_config,
    )
    monkeypatch.setattr(
        module.uvicorn,
        "run",
        lambda *args, **kwargs: events.append(("uvicorn", (args, kwargs))),
    )

    assert module.main() is None
    assert events[0] == ("logging", (process_name, module.settings.logging))
    args, kwargs = events[1][1]
    assert args == (app_path,)
    assert kwargs["log_config"] is uvicorn_log_config


def test_run_telegram_main_forwards(monkeypatch):
    called = False

    async def _fake_main() -> int:
        nonlocal called
        called = True
        return 7

    monkeypatch.setattr(run_telegram, "_telegram_main", _fake_main)

    assert asyncio.run(run_telegram.main()) == 7
    assert called is True


def test_run_cli_main_forwards(monkeypatch):
    called = False

    async def _fake_main() -> int:
        nonlocal called
        called = True
        return 3

    monkeypatch.setattr(run_cli, "_cli_main", _fake_main)

    assert asyncio.run(run_cli.main()) == 3
    assert called is True
