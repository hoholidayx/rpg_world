"""RPG World supervisor 入口。

按 ``settings.yaml`` 配置，在独立子进程中启动指定模块。
父进程只负责 supervisor、信号转发和子进程回收，不再直接承载
Dashboard API / Telegram / CLI 的运行时状态。

用法::

    # 读取 settings.yaml 按配置启动
    uv run python -m run

    # 仅启动 Dashboard API
    MODULES=dashboard_api uv run python -m run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# tiktoken 首次加载需要从网络下载编码文件。
# 设置缓存目录为项目 data/，避免因 /tmp 被清理导致启动卡死。
os.environ.setdefault(
    "TIKTOKEN_CACHE_DIR",
    str(Path(__file__).resolve().parent / "data"),
)

from loguru import logger as _loguru_logger

from launcher import ProcessSpec, build_process_spec, resolve_modules


# ── 日志配置（supervisor 自身 INFO+ 输出到 stderr） ───────────────────
_loguru_logger.remove()
_loguru_logger.add(
    sink=lambda msg: __import__("sys").stderr.write(msg),
    format="{time:HH:mm:ss} | {level:<7} | {name}:{line} - {message}",
    level="INFO",
    colorize=False,
)


@dataclass
class RunningProcess:
    """已经拉起的子进程及其等待任务。"""

    spec: ProcessSpec
    process: asyncio.subprocess.Process
    wait_task: asyncio.Task[int]


_STOP_GRACE_PERIOD_SECONDS: Final[float] = 5.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG World 统一启动器")
    parser.add_argument(
        "--modules",
        default=None,
        help="要启动的模块列表，逗号分隔，如 'api,telegram'。"
             "默认从 settings.yaml 读取",
    )
    return parser.parse_args()

async def _spawn_process(spec: ProcessSpec) -> RunningProcess:
    _loguru_logger.info("启动子进程: {} -> {}", spec.name, " ".join(spec.argv))
    process = await asyncio.create_subprocess_exec(*spec.argv)
    wait_task = asyncio.create_task(process.wait(), name=f"{spec.name}:wait")
    return RunningProcess(spec=spec, process=process, wait_task=wait_task)


async def _stop_process(running: RunningProcess, timeout_seconds: float = _STOP_GRACE_PERIOD_SECONDS) -> None:
    process = running.process
    if process.returncode is not None:
        return

    _loguru_logger.info("停止子进程: {}", running.spec.name)
    try:
        process.terminate()
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(running.wait_task, timeout=timeout_seconds)
    except TimeoutError:
        _loguru_logger.warning("子进程停止超时，强制终止: {}", running.spec.name)
        try:
            process.kill()
        except ProcessLookupError:
            return
        await running.wait_task


async def _stop_all_processes(children: list[RunningProcess]) -> None:
    if not children:
        return
    for child in children:
        if child.process.returncode is None:
            try:
                child.process.terminate()
            except ProcessLookupError:
                pass

    stop_tasks = [child.wait_task for child in children]
    try:
        await asyncio.wait_for(asyncio.gather(*stop_tasks, return_exceptions=True), timeout=_STOP_GRACE_PERIOD_SECONDS)
    except TimeoutError:
        for child in children:
            if child.process.returncode is None:
                try:
                    child.process.kill()
                except ProcessLookupError:
                    pass
        await asyncio.gather(*stop_tasks, return_exceptions=True)


async def _launch_children(modules: list[str]) -> list[RunningProcess]:
    children: list[RunningProcess] = []
    for module in modules:
        spec = build_process_spec(module)
        if spec is None:
            continue
        try:
            child = await _spawn_process(spec)
        except Exception:
            _loguru_logger.exception("子进程启动失败: {}", module)
            await _stop_all_processes(children)
            raise
        children.append(child)
    return children


def _install_stop_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass


async def main() -> int:
    enabled_modules = resolve_modules(_parse_args())

    if not enabled_modules:
        _loguru_logger.warning("未启用任何模块（在 settings.yaml 中设置 modules.{name}.enabled=true）")
        _loguru_logger.warning("或通过 MODULES=dashboard_api,telegram uv run python -m run 指定")
        return 0

    _loguru_logger.info("启动模块: {}", ", ".join(enabled_modules))

    children: list[RunningProcess] = []
    stop_event = asyncio.Event()
    signal_task: asyncio.Task[bool] | None = None

    try:
        try:
            children = await _launch_children(enabled_modules)
        except ValueError as exc:
            _loguru_logger.error("启动配置错误: {}", exc)
            return 2
        if not children:
            _loguru_logger.warning("请求启动的模块都未实际拉起，进程退出。")
            return 0

        _install_stop_handlers(stop_event)
        signal_task = asyncio.create_task(stop_event.wait(), name="supervisor-stop")
        child_tasks: set[asyncio.Task[int]] = {child.wait_task for child in children}
        wait_set: set[asyncio.Task[object]] = set(child_tasks) | {signal_task}

        _loguru_logger.info("已启动 {} 个子进程，按 Ctrl+C 停止", len(children))

        done, _pending = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

        if signal_task in done:
            _loguru_logger.info("收到停止信号，准备关闭所有子进程")
            await _stop_all_processes(children)
            return 0

        finished_child_task = next(task for task in done if task is not signal_task)
        exit_code = finished_child_task.result()
        finished_child = next(child for child in children if child.wait_task is finished_child_task)
        if exit_code == 0:
            _loguru_logger.warning("子进程正常退出但 supervisor 仍在运行: {}", finished_child.spec.name)
        else:
            _loguru_logger.error(
                "子进程异常退出: {} exit_code={}",
                finished_child.spec.name,
                exit_code,
            )
        await _stop_all_processes([child for child in children if child is not finished_child])
        return exit_code or 1
    finally:
        if signal_task is not None:
            signal_task.cancel()
            await asyncio.gather(signal_task, return_exceptions=True)
        await _stop_all_processes(children)
        _loguru_logger.info("已关闭。")


def cli() -> int:
    """Console script wrapper for the async supervisor entrypoint."""
    return asyncio.run(main())


if __name__ == "__main__":
    raise SystemExit(cli())
