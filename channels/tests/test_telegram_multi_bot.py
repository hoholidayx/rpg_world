"""Multi Telegram bot configuration and startup tests."""

from __future__ import annotations

import pytest

from rpg_world.channels.telegram.adapter import TelegramAdapter
from rpg_world.rpg_core import settings as settings_module
from rpg_world.rpg_core.settings import TelegramBotSettings


def _write_settings(path, telegram_yaml: str) -> None:
    path.write_text(
        f"""
base:
  agent: {{}}
  data:
    character_path: character
    lorebook_path: lorebook
  memory:
    enabled: false
  modules:
    telegram:
{telegram_yaml}
profiles:
  local: {{}}
""",
        encoding="utf-8",
    )


def _load_settings(tmp_path, monkeypatch, telegram_yaml: str):
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg, telegram_yaml)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")
    return settings_module.Settings()


async def test_start_telegram_creates_one_task_per_enabled_bot(monkeypatch):
    import rpg_world.run as run_module
    import rpg_world.channels.telegram as telegram_pkg

    created_adapters = []
    agent_calls = []

    class FakeChannelsSettings:
        telegram_bots = [
            TelegramBotSettings(
                name="main",
                enabled=True,
                token="token-main",
                workspace="data/main",
                streaming=True,
                proxy="http://proxy-main",
                stream_edit_interval_ms=2500,
                stream_edit_min_chars=64,
                request_timeout_ms=5000,
            ),
            TelegramBotSettings(
                name="prod",
                enabled=True,
                token="token-prod",
                workspace="data/prod",
                streaming=False,
                proxy="",
                stream_edit_interval_ms=1200,
                stream_edit_min_chars=32,
                request_timeout_ms=7000,
            ),
            TelegramBotSettings(name="off", enabled=False, token="", workspace=""),
        ]

    class FakeAgentManager:
        @staticmethod
        def get_or_create(*, workspace, session_id):  # noqa: ANN001
            agent_calls.append({"workspace": workspace, "session_id": session_id})
            return object()

    class FakeTelegramAdapter:
        def __init__(self, **kwargs):  # noqa: ANN003
            created_adapters.append(kwargs)

        async def start(self):
            return None

    monkeypatch.setattr(run_module, "channels_settings", FakeChannelsSettings())
    monkeypatch.setattr(run_module, "AgentManager", FakeAgentManager)
    monkeypatch.setattr(telegram_pkg, "TelegramAdapter", FakeTelegramAdapter)

    tasks = []
    await run_module._start_telegram(tasks)
    await __import__("asyncio").gather(*tasks)

    assert [task.get_name() for task in tasks] == ["telegram:main", "telegram:prod"]
    assert agent_calls == [
        {"workspace": "data/main", "session_id": "telegram_main_default"},
        {"workspace": "data/prod", "session_id": "telegram_prod_default"},
    ]
    assert created_adapters[0]["bot_name"] == "main"
    assert created_adapters[0]["token"] == "token-main"
    assert created_adapters[0]["proxy"] == "http://proxy-main"
    assert created_adapters[0]["streaming"] is True
    assert created_adapters[0]["stream_edit_interval_ms"] == 2500
    assert created_adapters[0]["stream_edit_min_chars"] == 64
    assert created_adapters[0]["request_timeout_ms"] == 5000
    assert created_adapters[1]["bot_name"] == "prod"
    assert created_adapters[1]["token"] == "token-prod"
    assert created_adapters[1]["streaming"] is False


def test_adapter_session_id_includes_bot_name():
    adapter = TelegramAdapter(bot_name="main", token="fake:token")
    assert adapter.name == "telegram_main"
    assert adapter.get_session_id("123") == "telegram_main_123"


@pytest.mark.parametrize(
    ("telegram_yaml", "message"),
    [
        (
            """
      enabled: true
      bots:
        - name: main
          enabled: true
          bot_token: same-token
          workspace: data/a
        - name: prod
          enabled: true
          bot_token: same-token
          workspace: data/b
""",
            "token reused across workspaces",
        ),
        (
            """
      enabled: true
      bots:
        - name: main
          enabled: true
          bot_token: token-a
          workspace: data/a
        - name: prod
          enabled: true
          bot_token: token-b
          workspace: data/a
""",
            "workspace reused by multiple tokens",
        ),
        (
            """
      enabled: true
      bots:
        - name: main
          enabled: false
        - name: main
          enabled: false
""",
            "duplicate name",
        ),
        (
            """
      enabled: true
      bots:
        - name: main
          enabled: true
          workspace: data/a
""",
            "missing token",
        ),
        (
            """
      enabled: true
      bots:
        - name: main
          enabled: true
          bot_token: token-a
""",
            "missing workspace",
        ),
    ],
)
def test_invalid_enabled_bot_configs_raise(tmp_path, monkeypatch, telegram_yaml, message):
    with pytest.raises(ValueError, match=message):
        _load_settings(tmp_path, monkeypatch, telegram_yaml)


def test_disabled_bot_can_omit_token_and_workspace(tmp_path, monkeypatch):
    settings = _load_settings(
        tmp_path,
        monkeypatch,
        """
      enabled: true
      bots:
        - name: main
          enabled: false
""",
    )

    assert settings.telegram_bots[0].enabled is False
    assert settings.telegram_bots[0].token == ""
    assert settings.telegram_bots[0].workspace == ""
