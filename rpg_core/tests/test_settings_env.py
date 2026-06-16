from __future__ import annotations

from pathlib import Path

from rpg_world.channels.config import ChannelsSettings
from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider
from rpg_world.rpg_core import settings as settings_module


def test_settings_reads_env_local_and_legacy_aliases(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / "env.local"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "export OPENAI_API_KEY='primary-key'",
                "telegram_bot_token=legacy-telegram-token",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_ENV_LOCAL_PATH", env_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    local_settings = settings_module.Settings()

    assert local_settings.get_openai_api_key() == "primary-key"
    assert local_settings.get_telegram_bot_token() == "legacy-telegram-token"


def test_settings_exported_env_overrides_env_local(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / "env.local"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=file-key",
                "TELEGRAM_BOT_TOKEN=file-telegram-token",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_ENV_LOCAL_PATH", env_path)
    monkeypatch.setenv("OPENAI_API_KEY", "exported-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "exported-telegram-token")

    local_settings = settings_module.Settings()

    assert local_settings.get_openai_api_key() == "exported-key"
    assert local_settings.get_telegram_bot_token() == "exported-telegram-token"
    assert local_settings.get_openai_api_key("explicit-key") == "explicit-key"
    assert local_settings.get_openai_api_key(None) == "exported-key"


def test_channels_settings_prefers_configured_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "rpg_world.channels.config.core_settings.get_telegram_bot_token",
        lambda: "env-token",
    )
    cfg = ChannelsSettings()
    cfg._data = {"modules": {"telegram": {"bot_token": "config-token"}}}

    assert cfg.telegram_token == "config-token"


def test_channels_settings_falls_back_to_env_for_placeholder_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "rpg_world.channels.config.core_settings.get_telegram_bot_token",
        lambda: "env-token",
    )
    cfg = ChannelsSettings()
    cfg._data = {"modules": {"telegram": {"bot_token": "YOUR_BOT_TOKEN"}}}

    assert cfg.telegram_token == "env-token"


def test_openai_provider_uses_settings_api_key(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    class DummyClient:
        def __init__(self, *, api_key=None, base_url=None, http_client=None) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["http_client"] = http_client

    monkeypatch.setattr("rpg_world.rpg_core.agent.openai_provider.AsyncOpenAI", DummyClient)
    monkeypatch.setattr(
        "rpg_world.rpg_core.agent.openai_provider.settings.get_openai_api_key",
        lambda explicit=None: explicit or "resolved-from-settings",
    )

    OpenAIProvider(model="test-model")
    assert captured["api_key"] == "resolved-from-settings"

    OpenAIProvider(model="test-model", api_key="explicit-key")
    assert captured["api_key"] == "explicit-key"
