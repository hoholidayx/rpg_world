"""Replaceable source-file selection strategies."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Protocol


class FileSelectionStrategy(Protocol):
    def select(self, candidates: tuple[Path, ...]) -> Path: ...


class RandomFileSelectionStrategy:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def select(self, candidates: tuple[Path, ...]) -> Path:
        if not candidates:
            raise ValueError("no media provider source files are available")
        return self._rng.choice(candidates)
