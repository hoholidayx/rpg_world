"""Pydantic schemas for lorebook entries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LorebookEntry(BaseModel):
    """Lorebook entry data.

    ``name``, ``enable``, ``content``, and ``description`` are fixed fields;
    extra fields are preserved for compatibility with existing lorebook files.
    """

    model_config = ConfigDict(extra="allow")

    name: str
    enable: bool = True
    content: str = ""
    description: str = ""
