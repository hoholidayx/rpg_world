"""Shared failure classification for Story acceptance aggregation."""

from __future__ import annotations

import asyncio

from llm_client.client import LLMServiceClientError


def is_infrastructure_error(exc: BaseException) -> bool:
    """Return whether a failure comes from the external execution substrate."""

    infrastructure_names = {
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "TimeoutError",
        "ConnectionError",
    }
    return (
        isinstance(exc, (LLMServiceClientError, asyncio.TimeoutError))
        or type(exc).__name__ in infrastructure_names
    )


__all__ = ["is_infrastructure_error"]
