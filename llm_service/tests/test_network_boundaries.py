from __future__ import annotations

from collections.abc import Callable

import pytest

from agent_service.settings import AgentServiceSettings
from dream_service.settings import DreamServiceSettings
from llm_service.settings import LLMServiceSettings
from media_service.settings import MediaServiceSettings
from tts_service.settings import TTSServiceSettings

SettingsFactory = Callable[[], object]

INTERNAL_SERVICE_SETTINGS: tuple[tuple[SettingsFactory, str], ...] = (
    (AgentServiceSettings, "agent_service.service.host"),
    (MediaServiceSettings, "media_service.service.host"),
    (TTSServiceSettings, "tts_service.service.host"),
    (DreamServiceSettings, "dream_service.service.host"),
    (LLMServiceSettings, "llm_service.service.host"),
)


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("localhost", "localhost"),
        ("LOCALHOST", "localhost"),
        ("127.0.0.1", "127.0.0.1"),
        ("127.255.255.254", "127.255.255.254"),
        ("::1", "::1"),
        ("[::1]", "::1"),
    ],
)
@pytest.mark.parametrize(("settings_factory", "_label"), INTERNAL_SERVICE_SETTINGS)
def test_internal_service_settings_accept_only_loopback_hosts(
    settings_factory: SettingsFactory,
    _label: str,
    configured: str,
    expected: str,
) -> None:
    configured_settings = settings_factory()
    configured_settings._raw["service"]["host"] = configured  # type: ignore[attr-defined]

    assert configured_settings.service.host == expected  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "configured",
    [
        "0.0.0.0",
        "::",
        "192.168.1.20",
        "10.0.0.5",
        "agent.internal",
    ],
)
@pytest.mark.parametrize(("settings_factory", "label"), INTERNAL_SERVICE_SETTINGS)
def test_internal_service_settings_reject_non_loopback_hosts(
    settings_factory: SettingsFactory,
    label: str,
    configured: str,
) -> None:
    configured_settings = settings_factory()
    configured_settings._raw["service"]["host"] = configured  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match=label):
        _ = configured_settings.service  # type: ignore[attr-defined]
