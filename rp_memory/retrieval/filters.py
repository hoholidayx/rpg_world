"""Shared eligibility rules for every memory retrieval path."""

from __future__ import annotations

from collections.abc import Mapping


def excluded_from_recall(metadata: Mapping[str, object]) -> bool:
    """Return whether a derived aggregate must never enter recall results."""
    if str(metadata.get("type", "")).strip().lower() == "overall":
        return True
    file_path = str(metadata.get("file", "") or metadata.get("file_path", ""))
    return file_path.replace("\\", "/").rsplit("/", 1)[-1].lower() == "overall.md"
