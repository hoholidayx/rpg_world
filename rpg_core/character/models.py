"""Pydantic schemas for character cards and details."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class CharacterData(BaseModel):
    """Character card data.

    ``name``, ``enable``, and ``content`` are fixed fields; extra fields are
    preserved for compatibility with existing character card files.
    """

    model_config = ConfigDict(extra="allow")

    name: str
    enable: bool = True
    content: str = ""


class CharacterDetail(BaseModel):
    """L2 character detail for deeper character settings."""

    model_config = ConfigDict(extra="allow")

    name: str
    enable: bool = True
    content: str = ""
    tags: Annotated[list[str], Field(default_factory=list)]
