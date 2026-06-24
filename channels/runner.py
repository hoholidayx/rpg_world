"""ChannelRunner — 多渠道运行器（注入模式）。

管理多个 ``ChannelAdapter`` 的生命周期，负责统一启动、关闭和信号处理。
不再自行创建 ``RPGGameAgent``，而是接受外部注入，由 ``Launcher``
或调用方统一管理 agent 生命周期。

用法::

    from channels import ChannelRunner, TelegramAdapter

    runner = ChannelRunner()
    runner.register(TelegramAdapter(token="xxx"))
    await runner.run()
"""

from __future__ import annotations

import asyncio
import signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from channels.base import ChannelAdapter


class ChannelRunner:
    """管理多个 ChannelAdapter 的生命周期。

    不再自建 agent，由外部注入。所有 adapter 共享同一 agent。
    """

    def __init__(self) -> None:
        self._channels: list[ChannelAdapter] = []

    def register(self, adapter: ChannelAdapter) -> None:
        """注册一个渠道适配器。"""
        self._channels.append(adapter)

    async def start_all(self) -> None:
        """启动所有渠道。返回后调用方负责保持进程运行。"""
        for ch in self._channels:
            await ch.start()

    async def stop_all(self) -> None:
        """关闭所有渠道。"""
        for ch in self._channels:
            await ch.stop()

    async def run(self) -> None:
        """启动所有渠道，等待退出信号，优雅关闭。

        适用于独立使用（非 launcher 模式）。
        """
        if not self._channels:
            print("没有注册任何渠道。")
            return

        tasks = [asyncio.create_task(ch.start()) for ch in self._channels]
        print(f"已启动 {len(self._channels)} 个渠道")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass

        await stop_event.wait()
        print("\n正在关闭渠道...")
        for ch in self._channels:
            await ch.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        print("已关闭所有渠道。")
