from __future__ import annotations

from pathlib import Path

import pytest

from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider
from rpg_world.rpg_core import settings as settings_module


def _write_settings(path: Path, *, agent_extra: str = "", profiles: str = "  local: {}\n") -> None:
    path.write_text(
        f"""
base:
  agent:
    model: test-model
    api_key: null
    api_key_env: TEST_OPENAI_KEY
{agent_extra}
  data:
    character_path: character
    lorebook_path: lorebook
  memory:
    enabled: false
  modules:
    telegram:
      enabled: false
      bots: []
profiles:
{profiles}
""",
        encoding="utf-8",
    )


def test_get_openai_api_key_priority(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg, agent_extra="    api_key: yaml-key\n")
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")
    monkeypatch.setenv("TEST_OPENAI_KEY", "env-key")

    local_settings = settings_module.Settings()

    assert local_settings.get_openai_api_key("explicit-key") == "explicit-key"
    assert local_settings.get_openai_api_key(None) == "yaml-key"


def test_get_openai_api_key_reads_configured_env(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")
    monkeypatch.setenv("TEST_OPENAI_KEY", "env-key")
    monkeypatch.setenv("OPENAI_API_KEY", "ignored-key")

    local_settings = settings_module.Settings()

    assert local_settings.get_openai_api_key(None) == "env-key"


def test_profile_must_be_set_before_settings_construction(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        profiles="""
  local:
    agent:
      model: local-model
  prod:
    agent:
      model: prod-model
""",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")
    local_settings = settings_module.Settings()

    monkeypatch.setenv("RPG_WORLD_PROFILE", "prod")

    assert local_settings.agent_model == "local-model"
    assert settings_module.Settings().agent_model == "prod-model"


def test_missing_profile_raises_value_error(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "missing")

    with pytest.raises(ValueError, match="missing"):
        settings_module.Settings()


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
