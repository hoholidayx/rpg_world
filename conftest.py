"""Repository-wide pytest configuration."""

from __future__ import annotations

import os


_PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def pytest_configure() -> None:
    """Keep unit tests isolated from shell-level proxy configuration."""
    if os.environ.get("PYTEST_KEEP_PROXY") == "1":
        return
    for name in _PROXY_ENV_VARS:
        os.environ.pop(name, None)
