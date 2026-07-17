"""Deterministic identities for user- and model-authored text fields."""

from __future__ import annotations

import hashlib
import unicodedata

__all__ = ["stable_text_identity_key"]


def stable_text_identity_key(*parts: object) -> str:
    """Hash NFKC/casefold/whitespace-normalized text parts with boundaries."""

    normalized = (
        " ".join(unicodedata.normalize("NFKC", str(part)).casefold().split())
        for part in parts
    )
    return hashlib.sha256("\0".join(normalized).encode("utf-8")).hexdigest()
