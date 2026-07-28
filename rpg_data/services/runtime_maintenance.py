"""Catalog-aware maintenance for unindexed runtime directories."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from peewee import Database

from rpg_data.bootstrap import (
    _scan_unindexed_runtime_dirs,
    _workspace_roots_from_index,
)
from rpg_data.errors import DataIntegrityError
from rpg_data.model.runtime_maintenance import (
    RuntimeMaintenanceDeleteResult,
    RuntimeMaintenanceItem,
    RuntimeMaintenanceScan,
)
from rpg_data.repositories.records import bind_database

__all__ = ["RuntimeMaintenanceDataService"]

logger = logging.getLogger("rpg_data.runtime_maintenance")

_RUNTIME_DIRECTORY_CATEGORY = "runtime_directory"
_QUARANTINE_PREFIX = ".runtime-maintenance-"


class RuntimeMaintenanceDataService:
    """Scan and safely remove catalog-unindexed runtime directories."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def scan_unindexed_runtime(
        self,
        workspace_id: str,
    ) -> RuntimeMaintenanceScan | None:
        """Return a fresh immutable scan scoped to an indexed workspace."""

        workspace_id = str(workspace_id)
        workspace_roots = self._workspace_roots()
        workspace_root = workspace_roots.get(workspace_id)
        if workspace_root is None:
            return None

        items: list[RuntimeMaintenanceItem] = []
        for raw_item in _scan_unindexed_runtime_dirs(workspace_roots):
            if (
                str(raw_item.get("workspace_id", "")) != workspace_id
                or str(raw_item.get("kind", "")) == "workspace"
            ):
                continue
            item = _item_from_scan(raw_item)
            if item is None or not _is_valid_scanned_item(item, workspace_root):
                logger.warning(
                    "ignored unsafe unindexed runtime scan item "
                    "workspace_id=%s kind=%s relative_path=%s path=%s",
                    workspace_id,
                    raw_item.get("kind", ""),
                    raw_item.get("relative_path", ""),
                    raw_item.get("path", ""),
                )
                continue
            items.append(item)
        return RuntimeMaintenanceScan(items=tuple(items))

    def delete_unindexed_runtime_item(
        self,
        item: RuntimeMaintenanceItem,
    ) -> RuntimeMaintenanceDeleteResult | None:
        return self.delete_unindexed_runtime_items((item,))

    def delete_unindexed_runtime_items(
        self,
        items: Sequence[RuntimeMaintenanceItem],
    ) -> RuntimeMaintenanceDeleteResult | None:
        """Freshly validate, isolate, then purge caller-supplied targets.

        Moving every target into a same-filesystem quarantine is the commit
        point.  A staging failure restores already moved directories and
        re-raises the original exception.  Purge failures are non-destructive
        to live runtime paths and are reported as pending cleanup locations.
        """

        targets = _dedupe_items(items)
        if not targets:
            return RuntimeMaintenanceDeleteResult(matched=False)

        workspace_id = targets[0].workspace_id
        if not workspace_id or any(
            target.workspace_id != workspace_id for target in targets
        ):
            raise DataIntegrityError(
                "runtime maintenance targets must belong to one workspace"
            )

        workspace_roots = self._workspace_roots()
        workspace_root = workspace_roots.get(workspace_id)
        if workspace_root is None:
            return None

        fresh_scan = self.scan_unindexed_runtime(workspace_id)
        if fresh_scan is None:
            return None
        fresh_by_locator = {
            _locator(item): item
            for item in fresh_scan.items
        }
        matches: list[RuntimeMaintenanceItem] = []
        for target in targets:
            match = fresh_by_locator.get(_locator(target))
            if (
                match is None
                or not _is_valid_scanned_item(match, workspace_root)
                or not _same_real_target(target, match)
            ):
                return RuntimeMaintenanceDeleteResult(matched=False)
            matches.append(match)

        collapsed = _collapse_nested_items(matches)
        if not collapsed:
            return RuntimeMaintenanceDeleteResult(matched=False)

        quarantine_root = Path(
            tempfile.mkdtemp(
                prefix=_QUARANTINE_PREFIX,
                dir=str(workspace_root),
            )
        ).resolve()
        staged: list[tuple[RuntimeMaintenanceItem, Path, Path]] = []
        try:
            for index, item in enumerate(collapsed):
                source = _validated_source_path(item, workspace_root)
                if source is None:
                    _restore_staged(staged)
                    _remove_empty_quarantine(quarantine_root)
                    return RuntimeMaintenanceDeleteResult(matched=False)
                if source.stat().st_dev != quarantine_root.stat().st_dev:
                    raise OSError(
                        "runtime maintenance quarantine is not on the target filesystem"
                    )
                destination = quarantine_root / f"{index:04d}-{source.name}"
                os.replace(source, destination)
                staged.append((item, source, destination))
        except Exception:
            logger.exception(
                "failed to isolate unindexed runtime directories "
                "workspace_id=%s quarantine=%s",
                workspace_id,
                quarantine_root,
            )
            _restore_staged(staged)
            _remove_empty_quarantine(quarantine_root)
            raise

        pending: list[str] = []
        for item, _source, destination in staged:
            try:
                shutil.rmtree(destination)
            except Exception:
                pending.append(str(destination))
                logger.exception(
                    "failed to purge quarantined runtime directory; cleanup pending "
                    "workspace_id=%s kind=%s story_id=%s session_id=%s "
                    "pending_path=%s",
                    workspace_id,
                    item.kind,
                    item.story_id or "<unknown>",
                    item.session_id or "<unknown>",
                    destination,
                )
            else:
                logger.warning(
                    "removed unindexed runtime directory "
                    "workspace_id=%s kind=%s story_id=%s session_id=%s path=%s",
                    workspace_id,
                    item.kind,
                    item.story_id or "<unknown>",
                    item.session_id or "<unknown>",
                    item.path,
                )

        if not pending:
            _remove_empty_quarantine(quarantine_root)
        return RuntimeMaintenanceDeleteResult(
            matched=True,
            deleted_items=tuple(item for item, _source, _destination in staged),
            pending_cleanup_paths=tuple(pending),
        )

    def _workspace_roots(self) -> dict[str, Path]:
        bind_database(self._database)
        return _workspace_roots_from_index()


def _item_from_scan(raw_item: dict[str, str]) -> RuntimeMaintenanceItem | None:
    try:
        return RuntimeMaintenanceItem(
            category=str(
                raw_item.get("category", _RUNTIME_DIRECTORY_CATEGORY)
            ),
            kind=str(raw_item["kind"]),
            workspace_id=str(raw_item["workspace_id"]),
            story_id=str(raw_item.get("story_id", "")),
            session_id=str(raw_item.get("session_id", "")),
            relative_path=str(raw_item["relative_path"]),
            path=str(raw_item["path"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _is_valid_scanned_item(
    item: RuntimeMaintenanceItem,
    workspace_root: Path,
) -> bool:
    if (
        item.category != _RUNTIME_DIRECTORY_CATEGORY
        or not item.workspace_id
        or item.kind not in {"story", "session"}
    ):
        return False

    relative = PurePosixPath(item.relative_path)
    if (
        relative.is_absolute()
        or not item.relative_path
        or ".." in relative.parts
    ):
        return False
    if item.kind == "story":
        expected_parts = ("stories", item.story_id)
        if not item.story_id or item.session_id:
            return False
    else:
        expected_parts = ("stories", item.story_id, item.session_id)
        if not item.story_id or not item.session_id:
            return False
    if relative.parts != expected_parts:
        return False

    return _validated_source_path(item, workspace_root) is not None


def _validated_source_path(
    item: RuntimeMaintenanceItem,
    workspace_root: Path,
) -> Path | None:
    root = workspace_root.resolve()
    candidate = root.joinpath(*PurePosixPath(item.relative_path).parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, OSError, ValueError):
        return None
    if not resolved.is_dir() or str(resolved) != item.path:
        return None
    return resolved


def _same_real_target(
    requested: RuntimeMaintenanceItem,
    scanned: RuntimeMaintenanceItem,
) -> bool:
    return requested == scanned


def _locator(item: RuntimeMaintenanceItem) -> tuple[str, ...]:
    return (
        item.category,
        item.kind,
        item.workspace_id,
        item.story_id,
        item.session_id,
        item.relative_path,
        item.path,
    )


def _dedupe_items(
    items: Sequence[RuntimeMaintenanceItem],
) -> tuple[RuntimeMaintenanceItem, ...]:
    deduped: list[RuntimeMaintenanceItem] = []
    seen: set[tuple[str, ...]] = set()
    for item in items:
        locator = _locator(item)
        if locator in seen:
            continue
        seen.add(locator)
        deduped.append(item)
    return tuple(deduped)


def _collapse_nested_items(
    items: Sequence[RuntimeMaintenanceItem],
) -> tuple[RuntimeMaintenanceItem, ...]:
    collapsed: list[RuntimeMaintenanceItem] = []
    for item in sorted(
        items,
        key=lambda candidate: (
            len(PurePosixPath(candidate.relative_path).parts),
            candidate.relative_path,
        ),
    ):
        path = PurePosixPath(item.relative_path)
        if any(
            path == parent
            or parent in path.parents
            for parent in (
                PurePosixPath(existing.relative_path)
                for existing in collapsed
            )
        ):
            continue
        collapsed.append(item)
    return tuple(collapsed)


def _restore_staged(
    staged: Sequence[tuple[RuntimeMaintenanceItem, Path, Path]],
) -> None:
    for item, source, destination in reversed(staged):
        try:
            os.replace(destination, source)
        except Exception:
            logger.exception(
                "failed to restore isolated runtime directory "
                "workspace_id=%s kind=%s original_path=%s quarantine_path=%s",
                item.workspace_id,
                item.kind,
                source,
                destination,
            )


def _remove_empty_quarantine(quarantine_root: Path) -> None:
    try:
        quarantine_root.rmdir()
    except FileNotFoundError:
        return
    except OSError:
        logger.exception(
            "failed to remove runtime maintenance quarantine path=%s",
            quarantine_root,
        )
