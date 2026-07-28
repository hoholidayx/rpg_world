"""Typed persistence contracts for runtime-directory maintenance."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceItem:
    """A freshly scanned catalog-unindexed runtime directory."""

    category: str
    kind: str
    workspace_id: str
    story_id: str
    session_id: str
    relative_path: str
    path: str


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceScan:
    """Immutable workspace-scoped maintenance scan."""

    items: tuple[RuntimeMaintenanceItem, ...]


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceDeleteResult:
    """Result of staging and purging freshly validated runtime directories.

    ``matched`` is false when at least one caller-supplied locator was stale or
    forged.  Matched targets are first moved out of their runtime locations;
    a purge failure therefore leaves only the returned quarantine paths for a
    later cleanup attempt.
    """

    matched: bool
    deleted_items: tuple[RuntimeMaintenanceItem, ...] = ()
    pending_cleanup_paths: tuple[str, ...] = ()

    @property
    def cleanup_pending(self) -> bool:
        return bool(self.pending_cleanup_paths)


__all__ = [
    "RuntimeMaintenanceDeleteResult",
    "RuntimeMaintenanceItem",
    "RuntimeMaintenanceScan",
]
