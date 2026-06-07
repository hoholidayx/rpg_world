"""ChannelRunner — 多渠道运行器。

管理多个 ``ChannelAdapter`` 的生命周期，负责统一启动、关闭和信号处理。
提供 ``python -m`` 的 CLI 入口。

用法::

    # 命令行启动（从 channels.json 读取配置）
    uv run python -m rpg_world.channels.runner

    # 编程方式
    from rpg_world.rpg_core.agent import RPGGameAgent
    from rpg_world.channels import ChannelRunner, TelegramAdapter

    agent = RPGGameAgent()
    runner = ChannelRunner(agent)
    runner.register(TelegramAdapter(token="xxx"))
    await runner.run()
"""

from __future__ import annotations

import argparse
import asyncio
import signal
from typing import TYPE_CHECKING

from rpg_world.channels.config import settings as channels_settings
from rpg_world.rpg_core.agent.agent import RPGGameAgent
from rpg_world.rpg_core.settings import settings as core_settings

if TYPE_CHECKING:
    from rpg_world.channels.base import ChannelAdapter


class ChannelRunner:
    """管理多个 ChannelAdapter 的生命周期。

    Parameters
    ----------
    agent:
        绑定的 RPGGameAgent 实例。
    """

    def __init__(self, agent: RPGGameAgent) -> None:
        self._agent = agent
        self._channels: list[ChannelAdapter] = []

    def register(self, adapter: ChannelAdapter) -> None:
        """注册一个渠道适配器。"""
        adapter.bind_agent(self._agent)
        self._channels.append(adapter)

    @classmethod
    def from_config(cls, agent: RPGGameAgent) -> ChannelRunner:
        """从 ``channels.json`` 读取配置，自动注册已启用的渠道。"""
        runner = cls(agent)
        cfg = channels_settings

        if cfg.is_enabled("telegram"):
            from rpg_world.channels.telegram import TelegramAdapter

            t_cfg = cfg.get_channel_config("telegram")
            runner.register(TelegramAdapter(
                token=t_cfg["token"],
                streaming=t_cfg.get("streaming", True),
            ))

        return runner

    async def run(self) -> None:
        """启动所有渠道，等待退出信号，然后优雅关闭。"""
        await self._agent._ensure_initialized()
        if not self._channels:
            print("没有注册任何渠道，退出。")
            return

        tasks = [asyncio.create_task(ch.start()) for ch in self._channels]
        print(f"已启动 {len(self._channels)} 个渠道: {[ch.name for ch in self._channels]}")

        # 等待 SIGINT/SIGTERM
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                # Windows 不支持 add_signal_handler
                pass

        await stop_event.wait()
        print("\n正在关闭渠道...")

        for ch in self._channels:
            await ch.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        print("已关闭所有渠道。")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG World 多渠道运行器")
    parser.add_argument(
        "--telegram-token",
        default=None,
        help="Telegram Bot Token（覆盖 channels.json 中的配置）",
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        default=None,
        help="启用流式输出",
    )
    parser.add_argument(
        "--non-streaming",
        action="store_true",
        default=None,
        help="禁用流式输出（优先级高于 --streaming）",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()

    agent = RPGGameAgent(
        model=core_settings.agent_model,
        api_key=core_settings.agent_api_key,
        base_url=core_settings.agent_base_url or None,
        max_tokens=core_settings.agent_max_tokens,
        temperature=core_settings.agent_temperature,
    )

    runner = ChannelRunner.from_config(agent)

    # 命令行参数覆盖
    if args.telegram_token:
        from rpg_world.channels.telegram import TelegramAdapter

        streaming = True
        if args.non_streaming:
            streaming = False
        elif args.streaming:
            streaming = True

        runner.register(TelegramAdapter(
            token=args.telegram_token,
            streaming=streaming,
        ))

    await runner.run()


if __name__ == "__main__":
    asyncio.run(_main())
