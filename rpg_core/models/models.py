"""Shared Pydantic models for RPG World API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CharacterData(BaseModel):
    """Character card — ``name``, ``enable``, ``content`` are fixed; extra fields allowed."""

    model_config = ConfigDict(extra="allow")

    name: str
    enable: bool = True
    content: str = ""


class CharacterDetail(BaseModel):
    """L2 character detail — deep setting for psychological profiling.

    ``name`` is the unique key within a character's details array.
    """

    model_config = ConfigDict(extra="allow")

    name: str
    enable: bool = True
    content: str = ""
    tags: list[str] = []


class LorebookEntry(BaseModel):
    """Lorebook entry — ``name``, ``enable``, ``content`` are fixed; extra fields allowed."""

    model_config = ConfigDict(extra="allow")

    name: str
    enable: bool = True
    content: str = ""


class MilestoneEntry(BaseModel):
    """Milestone entry — ``name``, ``enable``, ``content``, ``description`` are fixed; extra fields allowed."""

    model_config = ConfigDict(extra="allow")

    name: str
    enable: bool = True
    content: str = ""
    description: str = ""
