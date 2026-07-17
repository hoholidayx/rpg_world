from __future__ import annotations

import pytest

from dream_service.settings import _loopback_host, settings


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("localhost", "localhost"),
        ("127.0.0.1", "127.0.0.1"),
        ("::1", "::1"),
        ("[::1]", "::1"),
    ],
)
def test_dream_service_accepts_only_explicit_loopback_hosts(
    configured: str,
    expected: str,
) -> None:
    assert _loopback_host(configured) == expected


@pytest.mark.parametrize("configured", ["0.0.0.0", "::", "dream.internal"])
def test_dream_service_rejects_non_loopback_bind(configured: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        _loopback_host(configured)


def test_default_dream_service_bind_is_loopback() -> None:
    assert _loopback_host(settings.service.host) == settings.service.host
