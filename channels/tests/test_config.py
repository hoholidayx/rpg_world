"""Channel process YAML configuration tests."""

from __future__ import annotations

import pytest

from channels import config as channels_config


def _write_channels(path, *, profile_override: str = "") -> None:
    path.write_text(
        f"""
base:
  channels:
    telegram:
      bots:
        main:
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
      workspace: data/base
      session_id: cli_direct
      streaming: true
  logging:
    log_level: DEBUG
profiles:
  local: {{}}
  test:
{profile_override or "    {}"}
  prod: {{}}
""",
        encoding="utf-8",
    )


def _load(tmp_path, monkeypatch, *, profile_override: str = "", sibling_override: str = ""):
    cfg = tmp_path / "settings.yaml"
    _write_channels(cfg, profile_override=profile_override)
    if sibling_override:
        (tmp_path / "settings.test.yaml").write_text(sibling_override, encoding="utf-8")
    monkeypatch.setattr(channels_config, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")
    return channels_config.ChannelsSettings()


def test_yaml_profile_selection(monkeypatch, tmp_path):
    settings = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    channels:
      cli:
        workspace: data/custom
        session_id: custom_session
        streaming: false
""",
    )

    assert settings.profile == "test"
    assert settings.cli_workspace == "data/custom"
    assert settings.cli_session_id == "custom_session"
    assert settings.cli_streaming is False


def test_sibling_profile_file_override(monkeypatch, tmp_path):
    settings = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    channels:
      cli:
        session_id: inline_session
""",
        sibling_override="""
channels:
  telegram:
    bots:
      main:
        workspace: data/from-file
  cli:
    session_id: file_session
""",
    )

    assert settings.cli_session_id == "file_session"
    assert settings.telegram_bots[0].workspace == "data/from-file"


def test_explicit_profile_file_is_rejected(monkeypatch, tmp_path):
    cfg = tmp_path / "settings.yaml"
    _write_channels(
        cfg,
        profile_override="""
    file: settings.test.yaml
""",
    )
    monkeypatch.setattr(channels_config, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="must not declare file/required"):
        channels_config.ChannelsSettings()


def test_dict_deep_merge_keeps_base_values(monkeypatch, tmp_path):
    settings = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    channels:
      telegram:
        bots:
          main:
            workspace: data/override
""",
    )

    bot = settings.telegram_bots[0]
    assert bot.token == "base-token"
    assert bot.workspace == "data/override"


def test_telegram_bots_merge_by_mapping_key_and_append_new(monkeypatch, tmp_path):
    settings = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    channels:
      telegram:
        bots:
          main:
            enabled: false
            workspace: data/override
          prod:
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


def test_disabled_telegram_bot_can_omit_token_and_workspace(monkeypatch, tmp_path):
    settings = _load(
        tmp_path,
        monkeypatch,
        profile_override="""
    channels:
      telegram:
        bots:
          disabled:
            enabled: false
""",
    )

    bots = {bot.name: bot for bot in settings.telegram_bots}
    assert bots["disabled"].enabled is False
    assert bots["disabled"].token == ""
    assert bots["disabled"].workspace == ""


def test_enabled_telegram_bots_reject_token_reuse_across_workspaces(monkeypatch, tmp_path):
    cfg = tmp_path / "settings.yaml"
    _write_channels(
        cfg,
        profile_override="""
    channels:
      telegram:
        bots:
          main:
            enabled: true
            bot_token: shared-token
            workspace: data/first
          alt:
            enabled: true
            bot_token: shared-token
            workspace: data/second
""",
    )
    monkeypatch.setattr(channels_config, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="token reused across workspaces"):
        channels_config.ChannelsSettings()


def test_enabled_telegram_bots_reject_workspace_reuse_across_tokens(monkeypatch, tmp_path):
    cfg = tmp_path / "settings.yaml"
    _write_channels(
        cfg,
        profile_override="""
    channels:
      telegram:
        bots:
          main:
            enabled: true
            bot_token: token-a
            workspace: data/shared
          alt:
            enabled: true
            bot_token: token-b
            workspace: data/shared
""",
    )
    monkeypatch.setattr(channels_config, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="workspace reused by multiple tokens"):
        channels_config.ChannelsSettings()
