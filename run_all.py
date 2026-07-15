"""Start the independent RPG World backend services as one foreground stack."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
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
_FORCED_PORT_RELEASE_TIMEOUT = 2.0
_RUNTIME_PROCESS_NAME = re.compile(
    r"^(?:python(?:w)?(?:\d+(?:\.\d+)*)?|uv)(?:\.exe)?$",
    re.IGNORECASE,
)


class StartupError(RuntimeError):
    """Raised when the service stack cannot be started."""


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    module: str
    listen_address: tuple[str, int]
    health_url: str | None = None
    expected_status: str | None = None


@dataclass
class RunningService:
    spec: ServiceSpec
    process: subprocess.Popen[bytes]


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    command: str
    arguments: str


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
            listen_address=(llm_settings.service.host, llm_settings.service.port),
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
            listen_address=(
                agent_settings.service.host,
                agent_settings.service.port,
            ),
            health_url=_health_url(
                agent_settings.service.host,
                agent_settings.service.port,
                agent_settings.service.api_prefix,
            ),
        ),
        ServiceSpec(
            name="media",
            module="run_media",
            listen_address=(media_settings.service.host, media_settings.service.port),
            health_url=_health_url(
                media_settings.service.host,
                media_settings.service.port,
                media_settings.service.api_prefix,
            ),
        ),
        ServiceSpec(
            name="play_api",
            module="run_play_api",
            listen_address=(play_settings.service.host, play_settings.service.port),
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


def _port_in_use(address: tuple[str, int]) -> bool:
    try:
        _probe_port(address)
    except OSError:
        return False
    return True


def _listener_pids(port: int) -> tuple[int, ...]:
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-t", f"-iTCP:{int(port)}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise StartupError(
            f"cannot inspect the process listening on port {port}: {exc}"
        ) from exc

    if result.returncode not in {0, 1}:
        detail = result.stderr.strip() or f"lsof exited with code {result.returncode}"
        raise StartupError(
            f"cannot inspect the process listening on port {port}: {detail}"
        )

    pids: set[int] = set()
    for line in result.stdout.splitlines():
        value = line.strip()
        if not value:
            continue
        try:
            pid = int(value)
        except ValueError as exc:
            raise StartupError(
                f"cannot parse listener pid for port {port}: {value!r}"
            ) from exc
        if pid > 0:
            pids.add(pid)
    return tuple(sorted(pids))


def _process_info(pid: int) -> ProcessInfo | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm=", "-o", "args="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise StartupError(f"cannot inspect process {pid}: {exc}") from exc

    line = result.stdout.strip()
    if result.returncode != 0 or not line:
        return None
    command, _, arguments = line.partition(" ")
    return ProcessInfo(
        pid=pid,
        command=command.strip(),
        arguments=arguments.strip(),
    )


def _process_executable_names(process: ProcessInfo) -> tuple[str, ...]:
    candidates = [process.command]
    if process.arguments:
        try:
            arguments = shlex.split(process.arguments, posix=os.name != "nt")
        except ValueError:
            arguments = process.arguments.split()
        if arguments:
            candidates.append(arguments[0])

    names: list[str] = []
    for candidate in candidates:
        name = candidate.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if name:
            names.append(name)
    return tuple(names)


def _is_python_or_uv_process(process: ProcessInfo) -> bool:
    return any(
        _RUNTIME_PROCESS_NAME.fullmatch(name) is not None
        for name in _process_executable_names(process)
    )


def _validated_port_owners(port: int) -> tuple[ProcessInfo, ...]:
    owners: list[ProcessInfo] = []
    rejected: list[str] = []
    for pid in _listener_pids(port):
        process = _process_info(pid)
        if process is None:
            rejected.append(f"pid={pid} (process details unavailable)")
            continue
        if pid == os.getpid():
            rejected.append(f"pid={pid} ({process.command}, current run_all process)")
            continue
        if not _is_python_or_uv_process(process):
            rejected.append(f"pid={pid} ({process.command})")
            continue
        owners.append(process)

    if rejected:
        detail = ", ".join(rejected)
        raise StartupError(
            f"port {port} is occupied by a process that is not confirmed as "
            f"Python or uv; refusing to terminate: {detail}"
        )
    return tuple(owners)


def _signal_processes(
    processes: tuple[ProcessInfo, ...],
    signum: signal.Signals,
) -> None:
    for process in processes:
        try:
            os.kill(process.pid, signum)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise StartupError(
                f"cannot signal process {process.pid} ({process.command}): {exc}"
            ) from exc


def _wait_for_port_release(
    address: tuple[str, int],
    *,
    timeout: float,
    stop_event: Event,
) -> bool:
    deadline = time.monotonic() + timeout
    while _port_in_use(address):
        if stop_event.is_set():
            raise StartupError("startup interrupted")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        stop_event.wait(min(0.1, remaining))
    return True


def _clear_occupied_port(
    spec: ServiceSpec,
    *,
    timeout: float,
    stop_event: Event,
) -> None:
    address = spec.listen_address
    host, port = address
    if not _port_in_use(address):
        return

    owners = _validated_port_owners(port)
    if not owners:
        if not _port_in_use(address):
            return
        raise StartupError(
            f"{spec.name} port {host}:{port} is occupied, but its listener "
            "could not be identified"
        )

    for owner in owners:
        print(
            f"[run_all] {spec.name} port {host}:{port} is occupied by "
            f"{owner.command} (pid={owner.pid}); terminating it",
            flush=True,
        )
    _signal_processes(owners, signal.SIGTERM)
    if _wait_for_port_release(address, timeout=timeout, stop_event=stop_event):
        print(f"[run_all] {spec.name} port {host}:{port} released", flush=True)
        return

    remaining = _validated_port_owners(port)
    if not remaining:
        if not _port_in_use(address):
            return
        raise StartupError(
            f"{spec.name} port {host}:{port} is still occupied, but its listener "
            "could not be identified"
        )
    for owner in remaining:
        print(
            f"[run_all] force killing {owner.command} (pid={owner.pid}) "
            f"on {spec.name} port {host}:{port}",
            flush=True,
        )
    _signal_processes(remaining, signal.SIGKILL)
    if not _wait_for_port_release(
        address,
        timeout=_FORCED_PORT_RELEASE_TIMEOUT,
        stop_event=stop_event,
    ):
        raise StartupError(
            f"timed out waiting for {spec.name} port {host}:{port} to be released"
        )
    print(f"[run_all] {spec.name} port {host}:{port} released", flush=True)


def _validate_service_ports(specs: tuple[ServiceSpec, ...]) -> None:
    services_by_port: dict[int, list[str]] = {}
    for spec in specs:
        services_by_port.setdefault(int(spec.listen_address[1]), []).append(spec.name)

    conflicts = [
        f"{port} ({', '.join(names)})"
        for port, names in sorted(services_by_port.items())
        if len(names) > 1
    ]
    if conflicts:
        raise StartupError(
            "services must use distinct listen ports; conflicts: " + "; ".join(conflicts)
        )


def _wait_for_ready(
    service: RunningService,
    *,
    timeout: float,
    stop_event: Event,
) -> dict[str, Any]:
    url = service.spec.health_url
    ready_address = service.spec.listen_address

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
        _validate_service_ports(specs)
        for spec in specs:
            if stop_event.is_set():
                raise StartupError("startup interrupted")
            _clear_occupied_port(
                spec,
                timeout=shutdown_timeout,
                stop_event=stop_event,
            )
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
        help=(
            "Seconds to wait for graceful port-owner and child shutdown "
            "(default: %(default)s)."
        ),
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
