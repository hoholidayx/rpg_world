"""多渠道适配器模块——连接 RPGGameAgent 与外部即时通讯渠道。

用法::

    from channels import ChannelAdapter, TelegramAdapter, ChannelRunner
"""

from channels.base import ChannelAdapter
from channels.telegram import TelegramAdapter
from channels.runner import ChannelRunner

__all__ = ["ChannelAdapter", "TelegramAdapter", "ChannelRunner"]
