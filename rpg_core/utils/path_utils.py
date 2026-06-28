"""Small path-adjacent helpers for RPG World core."""

from __future__ import annotations

from pathlib import Path


__all__ = [
    "PACKAGE_ROOT",
]

# Project root used for resolving settings-relative paths.
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
