"""Typed persistence contracts for Session Composer storage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceTurnModeSeed:
    """Caller-specified values used to initialize one workspace mode row."""

    mode: str
    short_name: str
    prompt: str = ""
    sort_order: int = 0


@dataclass(frozen=True)
class WorkspaceTurnMode:
    workspace_id: str
    mode: str
    short_name: str
    prompt: str = ""
    sort_order: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class NarrativeStyle:
    id: int
    workspace_id: str
    name: str
    prompt: str = ""
    sort_order: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryNarrativeStyle:
    id: int
    workspace_id: str
    story_id: int
    narrative_style_id: int
    name: str
    prompt: str = ""
    is_base: bool = False
    sort_order: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryQuickReply:
    id: int
    workspace_id: str
    story_id: int
    title: str
    message: str = ""
    sort_order: int = 0
    enabled: bool = True
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


__all__ = [
    "NarrativeStyle",
    "StoryNarrativeStyle",
    "StoryQuickReply",
    "WorkspaceTurnMode",
    "WorkspaceTurnModeSeed",
]
