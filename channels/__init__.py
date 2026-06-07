"""多渠道适配器模块——连接 RPGGameAgent 与外部即时通讯渠道。

用法::

    from rpg_world.channels import ChannelAdapter, TelegramAdapter, ChannelRunner
"""

from rpg_world.channels.base import ChannelAdapter
from rpg_world.channels.telegram import TelegramAdapter
from rpg_world.channels.runner import ChannelRunner

__all__ = ["ChannelAdapter", "TelegramAdapter", "ChannelRunner"]
