"""ChannelsSettings — channel process configuration accessors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import os

from commons.settings import ConfigDict, ProfiledYamlSettings, forgiving_int, optional_bool
from rpg_core.session import SessionManager

_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.yaml"
_TELEGRAM_BOT_NAME_RE = __import__("re").compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class TelegramBotSettings:
    """Resolved Telegram bot configuration."""

    name: str
    enabled: bool = False
    token: str = ""
    workspace_id: str = ""
    story_id: int = 0
    session_id: str = ""
    session_title: str = ""
    allow_from: list[str] | None = None
    streaming: bool = True
    proxy: str = ""
    stream_edit_interval_ms: int = 800
    stream_edit_min_chars: int = 24
    request_timeout_ms: int = 5000
    auto_pin_created_session: bool = False


@dataclass(frozen=True)
class CliChannelSettings:
    """Resolved CLI channel configuration."""

    workspace_id: str = ""
    story_id: int = 0
    session_id: str = ""
    session_title: str = "CLI"
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
    def cli_workspace_id(self) -> str:
        return self.cli_channel.workspace_id

    @property
    def cli_story_id(self) -> int:
        return self.cli_channel.story_id

    @property
    def cli_session_id(self) -> str:
        return self.cli_channel.session_id

    @property
    def cli_session_title(self) -> str:
        return self.cli_channel.session_title

    @property
    def cli_streaming(self) -> bool:
        return self.cli_channel.streaming

    @property
    def cli_channel(self) -> CliChannelSettings:
        raw = self._channel_cfg("cli")
        if "workspace" in raw:
            raise ValueError("channels.cli.workspace is no longer supported; use workspace_id")
        session_id = str(raw.get("session_id", "") or "").strip()
        if session_id:
            session_id = SessionManager.validate_session_id(session_id)
        return CliChannelSettings(
            workspace_id=str(raw.get("workspace_id", "") or ""),
            story_id=self._int(raw, "channels.cli", "story_id", 0),
            session_id=session_id,
            session_title=str(raw.get("session_title", "CLI") or "CLI"),
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
        if "workspace" in bot:
            raise ValueError(f"telegram bot config invalid: bot={name} workspace is no longer supported; use workspace_id")
        token_env = self._first_non_empty(bot.get("token_env"))
        token = self._first_non_empty(
            bot.get("bot_token"),
            os.environ.get(token_env) if token_env else None,
        ) or ""
        allow_from = bot.get("allow_from", ["*"])
        if not isinstance(allow_from, list):
            allow_from = ["*"]
        session_id = str(bot.get("session_id", "") or "").strip()
        if session_id:
            session_id = SessionManager.validate_session_id(session_id)
        return TelegramBotSettings(
            name=str(name),
            enabled=self._bool(bot, "channels.telegram.bots", "enabled", False),
            token=token,
            workspace_id=str(bot.get("workspace_id", "") or ""),
            story_id=self._int(bot, "channels.telegram.bots", "story_id", 0),
            session_id=session_id,
            session_title=str(bot.get("session_title", str(name)) or str(name)),
            allow_from=[str(item) for item in allow_from],
            streaming=self._bool(bot, "channels.telegram.bots", "streaming", True),
            proxy=str(bot.get("proxy", "") or ""),
            stream_edit_interval_ms=self._int(bot, "channels.telegram.bots", "stream_edit_interval_ms", 800),
            stream_edit_min_chars=self._int(bot, "channels.telegram.bots", "stream_edit_min_chars", 24),
            request_timeout_ms=self._int(bot, "channels.telegram.bots", "request_timeout_ms", 5000),
            auto_pin_created_session=self._bool(bot, "channels.telegram.bots", "auto_pin_created_session", False),
        )

    def _validate_settings(self) -> None:
        telegram = self._channel_cfg("telegram")
        bots = telegram.get("bots", {})
        if not isinstance(bots, dict):
            raise ValueError("telegram bot config invalid: bots must be a mapping")

        seen_names: set[str] = set()
        token_to_story: dict[str, tuple[str, str, int]] = {}
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
            if not bot.workspace_id.strip():
                raise ValueError(f"telegram bot config invalid: bot={name} missing workspace_id")
            if bot.story_id <= 0:
                raise ValueError(f"telegram bot config invalid: bot={name} missing story_id")
            if bot.token in token_to_story:
                other_name, other_workspace_id, other_story_id = token_to_story[bot.token]
                if other_workspace_id != bot.workspace_id or other_story_id != bot.story_id:
                    raise ValueError(
                        "telegram bot config invalid: token reused across workspace/story "
                        f"bot={name} conflicts_with={other_name} "
                        f"workspace_id={bot.workspace_id} story_id={bot.story_id} "
                        f"other_workspace_id={other_workspace_id} other_story_id={other_story_id}"
                    )
            token_to_story[bot.token] = (name, bot.workspace_id, bot.story_id)

        cli = self.cli_channel
        if not cli.workspace_id.strip():
            raise ValueError("channels.cli.workspace_id is required")
        if cli.story_id <= 0:
            raise ValueError("channels.cli.story_id is required")
settings = ChannelsSettings()
"""Module-level singleton."""
