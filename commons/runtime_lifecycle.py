"""Shared helpers for explicit process-runtime cleanup."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TypeAlias

from loguru import logger


CleanupResult: TypeAlias = object | Awaitable[object]
CleanupAction: TypeAlias = Callable[[], CleanupResult]
CleanupStep: TypeAlias = tuple[str, CleanupAction]


@dataclass(frozen=True, slots=True)
class RuntimeCleanupFailure:
    """One named resource failure captured during best-effort cleanup."""

    resource: str
    error: BaseException


class RuntimeCleanupError(RuntimeError):
    """Raised after every runtime cleanup step has been attempted."""

    def __init__(
        self,
        runtime_name: str,
        failures: Sequence[RuntimeCleanupFailure],
    ) -> None:
        self.runtime_name = runtime_name
        self.failures = tuple(failures)
        resources = ", ".join(failure.resource for failure in self.failures)
        super().__init__(
            f"{runtime_name} cleanup failed for {len(self.failures)} "
            f"resource(s): {resources}"
        )


async def cleanup_runtime_resources(
    runtime_name: str,
    steps: Sequence[CleanupStep],
) -> None:
    """Run every named cleanup step in order, then raise one aggregate error."""

    failures: list[RuntimeCleanupFailure] = []
    for resource, action in steps:
        try:
            result = action()
            if inspect.isawaitable(result):
                await result
        except BaseException as exc:
            logger.opt(
                exception=(type(exc), exc, exc.__traceback__),
            ).error(
                "[{}] resource cleanup failed: resource={}",
                runtime_name,
                resource,
            )
            failures.append(RuntimeCleanupFailure(resource=resource, error=exc))

    if failures:
        error = RuntimeCleanupError(runtime_name, failures)
        if len(failures) == 1:
            raise error from failures[0].error
        raise error from BaseExceptionGroup(
            f"{runtime_name} resource cleanup failures",
            [failure.error for failure in failures],
        )


__all__ = [
    "CleanupAction",
    "CleanupStep",
    "RuntimeCleanupError",
    "RuntimeCleanupFailure",
    "cleanup_runtime_resources",
]
