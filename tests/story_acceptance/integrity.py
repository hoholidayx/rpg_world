"""Read-only byte-integrity evidence for isolated Story acceptance runs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from tests.story_acceptance.loader import LoadedStoryPack


def protected_paths(
    loaded: LoadedStoryPack,
    *,
    repository_root: str | Path,
) -> tuple[Path, ...]:
    """Return DesignProject and formal runtime files that must stay untouched."""

    root = Path(repository_root).resolve()
    values: list[Path] = [
        root / "data" / "rpg_world.sqlite3",
        root / "data" / "rpg_world.sqlite3-wal",
        root / "data" / "rpg_world.sqlite3-shm",
        root / "data" / "rpg_world.sqlite3-journal",
    ]
    if loaded.project_root is not None:
        project = loaded.project_root
        values.extend([
            project / "design-project.json",
            project / "design" / "current.json",
            project
            / "design"
            / "revisions"
            / f"{loaded.pack.source_revision}.json",
            project / "integrations" / "rpg-world.json",
        ])
        for pattern in (
            "design/revisions/*.json",
            "design/checkpoints/*.json",
            "artifacts/story-packs/*.json",
            "artifacts/snapshots/*.json",
        ):
            values.extend(sorted(project.glob(pattern)))
    values.append(loaded.path)
    return tuple(dict.fromkeys(path.resolve() for path in values))


def fingerprint_files(paths: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
    """Hash existing files and retain absence as an explicit state."""

    result: dict[str, dict[str, Any]] = {}
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_file():
            content = path.read_bytes()
            result[str(path)] = {
                "exists": True,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        else:
            result[str(path)] = {
                "exists": False,
                "size": None,
                "sha256": None,
            }
    return result


def changed_fingerprints(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> list[str]:
    """Return exact paths whose existence, size, or bytes changed."""

    return sorted(
        path
        for path in set(before).union(after)
        if before.get(path) != after.get(path)
    )


__all__ = ["changed_fingerprints", "fingerprint_files", "protected_paths"]
