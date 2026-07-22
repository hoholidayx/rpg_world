"""Repository-wide pytest configuration."""

from __future__ import annotations

import os


# Pytest is a dedicated test process. Select the test profile before any
# production module-level settings singletons are imported during collection.
os.environ["RPG_WORLD_PROFILE"] = "test"

pytest_plugins = ("tests.support.integration_fixtures",)


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
    live_provider_enabled = any(
        os.environ.get(name) == "1"
        for name in ("LIVE_LLM_TEST", "DREAM_LIVE_TEST")
    )
    if not live_provider_enabled:
        os.environ.setdefault("OPENAI_API_KEY", "test")
