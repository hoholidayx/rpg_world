"""Shared primitives for the memory storage stack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ChunkRecord:
    """A single chunk stored in the memory database."""

    id: int
    text: str
    metadata: dict[str, Any]


class VectorStoreError(Exception):
    """Unrecoverable memory store error."""
