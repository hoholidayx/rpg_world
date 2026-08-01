"""Repository-wide pytest configuration."""

from __future__ import annotations

import os

import pytest


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


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register opt-in Story Pack acceptance options.

    These options live at the repository root so the reusable acceptance
    harness can be invoked from any test package without importing production
    settings during collection.
    """

    group = parser.getgroup("story-acceptance")
    group.addoption(
        "--story-project",
        default=None,
        help="DesignProject root whose current full Story Pack should be tested.",
    )
    group.addoption(
        "--story-pack",
        default=None,
        help="Explicit Story Pack JSON path to test instead of a DesignProject.",
    )
    group.addoption(
        "--story-profile",
        default=None,
        help="Optional story-acceptance/1.0 sidecar JSON path.",
    )
    group.addoption(
        "--story-player-ref",
        default=None,
        help="Player Character stableId used when no sidecar is supplied.",
    )
    group.addoption(
        "--story-suite",
        choices=("smoke", "full"),
        default="smoke",
        help="Real-LLM Story acceptance suite size (default: smoke).",
    )
    group.addoption(
        "--story-report-dir",
        default="logs/story-acceptance",
        help="Ignored local directory for acceptance logs and reports.",
    )
    group.addoption(
        "--story-llm-timeout-seconds",
        type=int,
        default=60,
        help="Per-request LLM Service client timeout in seconds (default: 60).",
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
