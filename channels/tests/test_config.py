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
          workspace_id: base_workspace
          story_id: 1
          session_id: ""
          session_title: Main Bot
          allow_from: ["*"]
          streaming: true
          proxy: ""
          stream_edit_interval_ms: 800
          stream_edit_min_chars: 24
          request_timeout_ms: 5000
    cli:
      workspace_id: base_workspace
      story_id: 1
      session_id: ""
      session_title: CLI
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
        workspace_id: custom_workspace
        story_id: 2
        session_id: custom_session
        session_title: Custom CLI
        streaming: false
""",
    )

    assert settings.profile == "test"
    assert settings.cli_workspace_id == "custom_workspace"
    assert settings.cli_story_id == 2
    assert settings.cli_session_id == "custom_session"
    assert settings.cli_session_title == "Custom CLI"
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
        workspace_id: from_file_workspace
        story_id: 3
  cli:
    session_id: file_session
""",
    )

    assert settings.cli_session_id == "file_session"
    assert settings.telegram_bots[0].workspace_id == "from_file_workspace"
    assert settings.telegram_bots[0].story_id == 3


def test_logging_profile_override_keeps_bounded_defaults(monkeypatch, tmp_path):
    settings = _load(
        tmp_path,
        monkeypatch,
        sibling_override="""
logging:
  log_level: INFO
  rotation_size_mb: 5
  retention_count: 3
  console_enabled: false
""",
    )

    assert settings.logging.log_level == "INFO"
    assert settings.logging.directory == "logs"
    assert settings.logging.rotation_size_mb == 5
    assert settings.logging.retention_count == 3
    assert settings.logging.compression == "zip"
    assert settings.logging.console_enabled is False


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
            workspace_id: override_workspace
            story_id: 2
""",
    )

    bot = settings.telegram_bots[0]
    assert bot.token == "base-token"
    assert bot.workspace_id == "override_workspace"
    assert bot.story_id == 2


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
            workspace_id: override_workspace
            story_id: 2
          prod:
            enabled: true
            bot_token: prod-token
            workspace_id: prod_workspace
            story_id: 3
""",
    )

    bots = {bot.name: bot for bot in settings.telegram_bots}
    assert list(bots) == ["main", "prod"]
    assert bots["main"].enabled is False
    assert bots["main"].token == "base-token"
    assert bots["main"].workspace_id == "override_workspace"
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
    assert bots["disabled"].workspace_id == ""


def test_enabled_telegram_bots_reject_token_reuse_across_workspace_story(monkeypatch, tmp_path):
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
            workspace_id: first_workspace
            story_id: 1
          alt:
            enabled: true
            bot_token: shared-token
            workspace_id: second_workspace
            story_id: 1
""",
    )
    monkeypatch.setattr(channels_config, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="token reused across workspace/story"):
        channels_config.ChannelsSettings()


def test_old_workspace_field_is_rejected(monkeypatch, tmp_path):
    cfg = tmp_path / "settings.yaml"
    _write_channels(
        cfg,
        profile_override="""
    channels:
      cli:
        workspace: data/legacy
""",
    )
    monkeypatch.setattr(channels_config, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="workspace is no longer supported"):
        channels_config.ChannelsSettings()


def test_enabled_telegram_bot_requires_workspace_id_and_story_id(monkeypatch, tmp_path):
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
            workspace_id: ""
            story_id: 0
""",
    )
    monkeypatch.setattr(channels_config, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="missing workspace_id"):
        channels_config.ChannelsSettings()


def test_non_empty_session_id_is_validated(monkeypatch, tmp_path):
    cfg = tmp_path / "settings.yaml"
    _write_channels(
        cfg,
        profile_override="""
    channels:
      cli:
        session_id: bad-id
""",
    )
    monkeypatch.setattr(channels_config, "_SETTINGS_PATH", cfg)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")

    with pytest.raises(ValueError, match="session_id must match"):
        channels_config.ChannelsSettings()
