"""ChannelsSettings 配置健壮性测试。"""

from __future__ import annotations

import json

from rpg_world.channels import config as channels_config


def test_invalid_int_and_bool_fallback(monkeypatch, tmp_path):
    cfg_path = tmp_path / "channels.json"
    cfg_path.write_text(
        json.dumps(
            {
                "modules": {
                    "api": {"enabled": "maybe", "port": "oops"},
                    "telegram": {
                        "enabled": "true",
                        "streaming": "no",
                        "stream_edit_interval_ms": "bad",
                        "stream_edit_min_chars": None,
                        "request_timeout_ms": "500",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(channels_config, "_CONFIG_PATH", cfg_path)

    settings = channels_config.ChannelsSettings()

    assert settings.api_enabled is False
    assert settings.api_port == 8000
    assert settings.telegram_enabled is True
    assert settings.telegram_streaming is False
    assert settings.telegram_stream_edit_interval_ms == 800
    assert settings.telegram_stream_edit_min_chars == 24
    assert settings.telegram_request_timeout_ms == 500
    assert settings.enabled_module_names == ["telegram"]
