"""ChannelsSettings — channel process configuration accessors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import os

from commons.settings import ConfigDict, ProfiledYamlSettings, forgiving_int, optional_bool

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"
_TELEGRAM_BOT_NAME_RE = __import__("re").compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class TelegramBotSettings:
    """Resolved Telegram bot configuration."""

    name: str
    enabled: bool = False
    token: str = ""
    workspace: str = ""
    allow_from: list[str] | None = None
    streaming: bool = True
    proxy: str = ""
    stream_edit_interval_ms: int = 800
    stream_edit_min_chars: int = 24
    request_timeout_ms: int = 5000


@dataclass(frozen=True)
class CliChannelSettings:
    """Resolved CLI channel configuration."""

    workspace: str = ""
    session_id: str = "cli_direct"
    streaming: bool = True


@dataclass(frozen=True)
class ChannelLoggingSettings:
    log_level: str = "DEBUG"
    watcher_log_level: str = "DEBUG"
    vector_index_log_level: str = "DEBUG"


class ChannelsSettings(ProfiledYamlSettings):
    """Process and channel configuration accessor."""

    def __init__(self) -> None:
        self.settings_path = _SETTINGS_PATH
        self.label = "channels/settings.yaml"
        super().__init__()
        self._validate_settings()

    def _channel_cfg(self, name: str) -> dict:
        channels = self._mapping("channels")
        mod = channels.get(name, {}) if isinstance(channels, dict) else {}
        return mod if isinstance(mod, dict) else {}

    def _bool(self, cfg: dict, label: str, key: str, default: bool) -> bool:
        return optional_bool(cfg.get(key, default), default)

    def _int(self, cfg: dict, label: str, key: str, default: int) -> int:
        return forgiving_int(cfg.get(key, default), default)

    # ── Telegram channel config ─────────────────────────────────────────

    @property
    def telegram_bots(self) -> list[TelegramBotSettings]:
        telegram = self._channel_cfg("telegram")
        bots = telegram.get("bots", {})
        if not isinstance(bots, dict):
            return []
        return [
            self._build_telegram_bot(name, bot)
            for name, bot in bots.items()
            if isinstance(bot, dict)
        ]

    # ── CLI channel config ──────────────────────────────────────────────

    @property
    def cli_workspace(self) -> str:
        """CLI channel workspace."""
        from rpg_core.utils.path_utils import default_workspace_name

        configured = self.cli_channel.workspace
        return configured if configured else default_workspace_name("cli")

    @property
    def cli_session_id(self) -> str:
        return self.cli_channel.session_id

    @property
    def cli_streaming(self) -> bool:
        return self.cli_channel.streaming

    @property
    def cli_channel(self) -> CliChannelSettings:
        raw = self._channel_cfg("cli")
        return CliChannelSettings(
            workspace=str(raw.get("workspace", "") or ""),
            session_id=str(raw.get("session_id", "cli_direct") or "cli_direct"),
            streaming=self._bool(raw, "channels.cli", "streaming", True),
        )

    @property
    def logging(self) -> ChannelLoggingSettings:
        raw = self._mapping("logging")
        return ChannelLoggingSettings(
            log_level=str(raw.get("log_level", "DEBUG") or "DEBUG"),
            watcher_log_level=str(raw.get("watcher_log_level", raw.get("log_level", "DEBUG")) or "DEBUG"),
            vector_index_log_level=str(raw.get("vector_index_log_level", raw.get("log_level", "DEBUG")) or "DEBUG"),
        )

    @staticmethod
    def _first_non_empty(*values: str | None) -> str | None:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _build_telegram_bot(self, name: str, bot: ConfigDict) -> TelegramBotSettings:
        token_env = self._first_non_empty(bot.get("token_env"))
        token = self._first_non_empty(
            bot.get("bot_token"),
            os.environ.get(token_env) if token_env else None,
        ) or ""
        allow_from = bot.get("allow_from", ["*"])
        if not isinstance(allow_from, list):
            allow_from = ["*"]
        return TelegramBotSettings(
            name=str(name),
            enabled=self._bool(bot, "channels.telegram.bots", "enabled", False),
            token=token,
            workspace=str(bot.get("workspace", "") or ""),
            allow_from=[str(item) for item in allow_from],
            streaming=self._bool(bot, "channels.telegram.bots", "streaming", True),
            proxy=str(bot.get("proxy", "") or ""),
            stream_edit_interval_ms=self._int(bot, "channels.telegram.bots", "stream_edit_interval_ms", 800),
            stream_edit_min_chars=self._int(bot, "channels.telegram.bots", "stream_edit_min_chars", 24),
            request_timeout_ms=self._int(bot, "channels.telegram.bots", "request_timeout_ms", 5000),
        )

    def _validate_settings(self) -> None:
        telegram = self._channel_cfg("telegram")
        bots = telegram.get("bots", {})
        if not isinstance(bots, dict):
            raise ValueError("telegram bot config invalid: bots must be a mapping")

        seen_names: set[str] = set()
        token_to_workspace: dict[str, tuple[str, str]] = {}
        workspace_to_token: dict[str, tuple[str, str]] = {}
        for name, raw_bot in bots.items():
            if not isinstance(raw_bot, dict):
                raise ValueError("telegram bot config invalid: bot entry must be a mapping")
            name = str(name or "")
            if not name or not _TELEGRAM_BOT_NAME_RE.fullmatch(name):
                raise ValueError(f"telegram bot config invalid: bot={name or '<missing>'} invalid name")
            if name in seen_names:
                raise ValueError(f"telegram bot config invalid: bot={name} duplicate name")
            seen_names.add(name)
            bot = self._build_telegram_bot(name, raw_bot)
            if not bot.enabled:
                continue
            if not bot.token:
                raise ValueError(f"telegram bot config invalid: bot={name} missing token")
            if not bot.workspace.strip():
                raise ValueError(f"telegram bot config invalid: bot={name} missing workspace")
            if bot.token in token_to_workspace:
                other_name, other_workspace = token_to_workspace[bot.token]
                if other_workspace != bot.workspace:
                    raise ValueError(
                        "telegram bot config invalid: token reused across workspaces "
                        f"bot={name} conflicts_with={other_name} "
                        f"workspace={bot.workspace} other_workspace={other_workspace}"
                    )
            token_to_workspace[bot.token] = (name, bot.workspace)
            if bot.workspace in workspace_to_token:
                other_name, other_token = workspace_to_token[bot.workspace]
                if other_token != bot.token:
                    raise ValueError(
                        "telegram bot config invalid: workspace reused by multiple tokens "
                        f"bot={name} conflicts_with={other_name} workspace={bot.workspace}"
                    )
            workspace_to_token[bot.workspace] = (name, bot.token)
settings = ChannelsSettings()
"""Module-level singleton."""
