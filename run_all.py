"""Start the independent RPG World backend services as one foreground stack."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from agent_service.settings import settings as agent_settings
from llm_service.settings import settings as llm_settings
from media_service.settings import settings as media_settings
from play_api.settings import play_settings


_PROJECT_ROOT = Path(__file__).resolve().parent
_DEFAULT_STARTUP_TIMEOUT = 30.0
_DEFAULT_SHUTDOWN_TIMEOUT = 10.0


class StartupError(RuntimeError):
    """Raised when the service stack cannot be started."""


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    module: str
    health_url: str | None = None
    expected_status: str | None = None
    ready_address: tuple[str, int] | None = None


@dataclass
class RunningService:
    spec: ServiceSpec
    process: subprocess.Popen[bytes]


def _authority(host: str, port: int) -> str:
    normalized = host.strip().strip("[]")
    if ":" in normalized:
        normalized = f"[{normalized}]"
    return f"{normalized}:{int(port)}"


def _health_url(host: str, port: int, api_prefix: str) -> str:
    prefix = "/" + api_prefix.strip("/")
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{_authority(probe_host, port)}{prefix}/health"


def _service_specs() -> tuple[ServiceSpec, ...]:
    return (
        ServiceSpec(
            name="llm",
            module="run_llm",
            health_url=_health_url(
                llm_settings.service.host,
                llm_settings.service.port,
                llm_settings.service.api_prefix,
            ),
            expected_status="ok",
        ),
        ServiceSpec(
            name="agent",
            module="run_agent",
            health_url=_health_url(
                agent_settings.service.host,
                agent_settings.service.port,
                agent_settings.service.api_prefix,
            ),
        ),
        ServiceSpec(
            name="media",
            module="run_media",
            health_url=_health_url(
                media_settings.service.host,
                media_settings.service.port,
                media_settings.service.api_prefix,
            ),
        ),
        ServiceSpec(
            name="play_api",
            module="run_play_api",
            ready_address=(play_settings.service.host, play_settings.service.port),
        ),
    )


def _command(spec: ServiceSpec) -> list[str]:
    return [sys.executable, "-m", spec.module]


def _start(spec: ServiceSpec) -> RunningService:
    print(f"[run_all] starting {spec.name}: {' '.join(_command(spec))}", flush=True)
    process = subprocess.Popen(
        _command(spec),
        cwd=_PROJECT_ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        start_new_session=(os.name == "posix"),
    )
    return RunningService(spec=spec, process=process)


def _probe_health(url: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=1.5) as response:
        raw = response.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return response.status, payload if isinstance(payload, dict) else {}


def _probe_port(address: tuple[str, int]) -> None:
    host, port = address
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    with socket.create_connection((probe_host, int(port)), timeout=1.0):
        return


def _wait_for_ready(
    service: RunningService,
    *,
    timeout: float,
    stop_event: Event,
) -> dict[str, Any]:
    url = service.spec.health_url
    ready_address = service.spec.ready_address
    if url is None and ready_address is None:
        return {}

    deadline = time.monotonic() + timeout
    last_error = "not reachable"
    while time.monotonic() < deadline:
        if stop_event.is_set():
            raise StartupError("startup interrupted")
        return_code = service.process.poll()
        if return_code is not None:
            raise StartupError(
                f"{service.spec.name} exited before health check (code={return_code})"
            )
        try:
            if url is not None:
                status_code, payload = _probe_health(url)
                expected = service.spec.expected_status
                ready = status_code < 400 and (
                    expected is None or payload.get("status") == expected
                )
                detail = f"{url} {payload or status_code}"
            else:
                assert ready_address is not None
                _probe_port(ready_address)
                payload = {}
                ready = True
                detail = f"{ready_address[0]}:{ready_address[1]}"
            if ready:
                print(
                    f"[run_all] {service.spec.name} ready: {detail}",
                    flush=True,
                )
                return payload
            last_error = detail
        except (OSError, ValueError) as exc:
            last_error = str(exc)
        stop_event.wait(0.25)

    target = url or f"{ready_address[0]}:{ready_address[1]}"
    raise StartupError(
        f"timed out waiting for {service.spec.name} readiness at "
        f"{target}: {last_error}"
    )


def _send_signal(process: subprocess.Popen[bytes], signum: signal.Signals) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signum)
            return
        except ProcessLookupError:
            return
    process.send_signal(signum)


def _stop_services(
    services: list[RunningService],
    *,
    timeout: float,
) -> None:
    active = [service for service in services if service.process.poll() is None]
    if not active:
        return
    print("[run_all] stopping services...", flush=True)
    for service in reversed(active):
        _send_signal(service.process, signal.SIGINT)

    deadline = time.monotonic() + timeout
    while active and time.monotonic() < deadline:
        active = [service for service in active if service.process.poll() is None]
        if active:
            time.sleep(0.1)

    for service in active:
        print(
            f"[run_all] force terminating {service.spec.name} (pid={service.process.pid})",
            flush=True,
        )
        _send_signal(service.process, signal.SIGTERM)
    for service in active:
        try:
            service.process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            service.process.kill()


def run_stack(*, startup_timeout: float, shutdown_timeout: float) -> int:
    specs = _service_specs()
    services: list[RunningService] = []
    stop_event = Event()
    received_signal: int | None = None

    def _handle_signal(signum: int, _frame: object) -> None:
        nonlocal received_signal
        received_signal = signum
        stop_event.set()

    previous_handlers: dict[int, Any] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, _handle_signal)

    try:
        for spec in specs:
            service = _start(spec)
            services.append(service)
            _wait_for_ready(
                service,
                timeout=startup_timeout,
                stop_event=stop_event,
            )
        print("[run_all] all services started; press Ctrl-C to stop", flush=True)

        while not stop_event.wait(0.5):
            for service in services:
                return_code = service.process.poll()
                if return_code is not None:
                    raise StartupError(
                        f"{service.spec.name} exited unexpectedly (code={return_code})"
                    )
    except (OSError, StartupError) as exc:
        print(f"[run_all] {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        _stop_services(services, timeout=shutdown_timeout)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)

    if received_signal is not None and received_signal != signal.SIGINT:
        return 128 + received_signal
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start LLM, Agent, Media and Play API as independent child processes."
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=_DEFAULT_STARTUP_TIMEOUT,
        help="Seconds to wait for each service readiness check (default: %(default)s).",
    )
    parser.add_argument(
        "--shutdown-timeout",
        type=float,
        default=_DEFAULT_SHUTDOWN_TIMEOUT,
        help="Seconds to wait for graceful child shutdown (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    if args.startup_timeout <= 0 or args.shutdown_timeout <= 0:
        parser.error("timeouts must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return run_stack(
            startup_timeout=args.startup_timeout,
            shutdown_timeout=args.shutdown_timeout,
        )
    except StartupError as exc:
        print(f"[run_all] {exc}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
