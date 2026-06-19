"""Unified settings.yaml channel configuration tests."""

from __future__ import annotations

import pytest

from rpg_world.channels import config as channels_config
from rpg_world.rpg_core import settings as settings_module


def _write_settings(path, *, profile_override: str = "") -> None:
    path.write_text(
        f"""
base:
  agent:
    model: base-model
    api_key_env: TEST_OPENAI_KEY
  data:
    character_path: character
    lorebook_path: lorebook
  modules:
    api:
      enabled: false
      host: 127.0.0.1
      port: 8000
      reload: false
    telegram:
      enabled: true
      bots:
        - name: main
          enabled: true
          bot_token: base-token
          workspace: data/base
          allow_from: ["*"]
          streaming: true
          proxy: ""
          stream_edit_interval_ms: 800
          stream_edit_min_chars: 24
          request_timeout_ms: 5000
    cli:
      enabled: false
      workspace: data/base
  memory:
    enabled: false
profiles:
  local: {{}}
  test:
{profile_override or "    {}"}
""",
        encoding="utf-8",
    )


def _load(tmp_path, monkeypatch, *, profile: str = "test", profile_override: str = ""):
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg, profile_override=profile_override)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", profile)
    loaded = settings_module.Settings()
    monkeypatch.setattr(channels_config, "core_settings", loaded)
    return loaded, channels_config.ChannelsSettings()


def test_yaml_profile_selection(monkeypatch, tmp_path):
    settings, channels = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    agent:
      model: profile-model
    modules:
      api:
        enabled: true
""",
    )

    assert settings.profile == "test"
    assert settings.agent_model == "profile-model"
    assert channels.api_enabled is True
    assert channels.enabled_module_names == ["api", "telegram"]


def test_profile_file_override(monkeypatch, tmp_path):
    profile_path = tmp_path / "settings.test.yaml"
    profile_path.write_text(
        """
agent:
  model: file-model
modules:
  api:
    enabled: true
  telegram:
    bots:
      - name: main
        workspace: data/from-file
""",
        encoding="utf-8",
    )

    settings, channels = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    file: settings.test.yaml
    agent:
      model: inline-model
""",
    )

    assert settings.agent_model == "file-model"
    assert channels.api_enabled is True
    assert settings.telegram_bots[0].workspace == "data/from-file"


def test_missing_optional_profile_file_is_empty_override(monkeypatch, tmp_path):
    settings, _channels = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    file: missing.yaml
""",
    )

    assert settings.agent_model == "base-model"


def test_missing_required_profile_file_raises(monkeypatch, tmp_path):
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        profile_override="""
    file: missing.yaml
    required: true
""",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="profile=test"):
        settings_module.Settings()


def test_dict_deep_merge_keeps_base_values(monkeypatch, tmp_path):
    settings, channels = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    modules:
      api:
        port: 9000
""",
    )

    assert channels.api_host == "127.0.0.1"
    assert channels.api_port == 9000
    assert settings.agent_model == "base-model"


def test_normal_lists_are_replaced(monkeypatch, tmp_path):
    settings, _channels = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    modules:
      telegram:
        bots:
          - name: main
            allow_from: ["42"]
""",
    )

    assert settings.telegram_bots[0].allow_from == ["42"]


def test_telegram_bots_merge_by_name_and_append_new(monkeypatch, tmp_path):
    settings, _channels = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    modules:
      telegram:
        bots:
          - name: main
            enabled: false
            workspace: data/override
          - name: prod
            enabled: true
            bot_token: prod-token
            workspace: data/prod
""",
    )

    bots = {bot.name: bot for bot in settings.telegram_bots}
    assert list(bots) == ["main", "prod"]
    assert bots["main"].enabled is False
    assert bots["main"].token == "base-token"
    assert bots["main"].workspace == "data/override"
    assert bots["prod"].token == "prod-token"


def test_telegram_enabled_requires_module_and_enabled_bot(monkeypatch, tmp_path):
    _settings, channels = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    modules:
      telegram:
        enabled: false
""",
    )
    assert channels.telegram_enabled is False
    assert channels.enabled_module_names == []


def test_disabled_telegram_bot_can_omit_token_and_workspace(monkeypatch, tmp_path):
    settings, channels = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    modules:
      telegram:
        bots:
          - name: disabled
            enabled: false
""",
    )

    bots = {bot.name: bot for bot in settings.telegram_bots}
    assert bots["disabled"].enabled is False
    assert bots["disabled"].token == ""
    assert bots["disabled"].workspace == ""
    assert channels.telegram_enabled is True


def test_enabled_telegram_bots_reject_token_reuse_across_workspaces(monkeypatch, tmp_path):
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        profile_override="""
    modules:
      telegram:
        bots:
          - name: main
            enabled: true
            bot_token: shared-token
            workspace: data/first
          - name: alt
            enabled: true
            bot_token: shared-token
            workspace: data/second
""",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="token reused across workspaces"):
        settings_module.Settings()


def test_enabled_telegram_bots_reject_workspace_reuse_across_tokens(monkeypatch, tmp_path):
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        profile_override="""
    modules:
      telegram:
        bots:
          - name: main
            enabled: true
            bot_token: token-a
            workspace: data/shared
          - name: alt
            enabled: true
            bot_token: token-b
            workspace: data/shared
""",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="workspace reused by multiple tokens"):
        settings_module.Settings()

    _settings, channels = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    modules:
      telegram:
        bots:
          - name: main
            enabled: false
""",
    )
    assert channels.telegram_enabled is False
