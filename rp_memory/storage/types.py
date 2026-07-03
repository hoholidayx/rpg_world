"""Shared primitives for the memory storage stack."""

from __future__ import annotations

from dataclasses import dataclass

from commons.types import Metadata


@dataclass
class ChunkRecord:
    """A single chunk stored in the memory database."""

    id: int
    text: str
    metadata: Metadata


@dataclass
class IndexedFileState:
    """Manifest entry describing the indexed state of one source file."""

    file: str
    source_id: str
    mtime_ns: int
    size: int
    content_hash: str
    chunk_count: int = 0
    indexed_at: float | None = None
    status: str = "indexed"
    last_error: str = ""


class VectorStoreError(Exception):
    """Unrecoverable memory store error."""
