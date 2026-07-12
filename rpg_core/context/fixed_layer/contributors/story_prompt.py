"""Story prompt fixed-layer contributor."""

from __future__ import annotations

from typing import Protocol

from rpg_core.context.fixed_layer.models import (
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)
from rpg_data.models import Story

STORY_PROMPT_SECTION_ID = "story_prompt"
STORY_PROMPT_SOURCE = "story_prompt"


class _StoryPromptCatalog(Protocol):
    def get_session_story(self, session_id: str) -> Story | None:
        ...


class StoryPromptFixedLayerContributor(FixedLayerContributor):
    """Story-level fixed system prompt contributor."""

    name = STORY_PROMPT_SOURCE

    def __init__(
        self,
        session_id: str,
        *,
        catalog: _StoryPromptCatalog | None = None,
        content: str | None = None,
    ) -> None:
        self._session_id = session_id
        self._catalog = catalog
        self._content = content

    def get_fixed_contribution(self) -> FixedLayerContribution:
        if self._content is None:
            story = self._get_catalog().get_session_story(self._session_id)
            content = str(story.story_prompt or "").strip() if story is not None else ""
        else:
            content = str(self._content).strip()
        if not content:
            return FixedLayerContribution()
        return FixedLayerContribution(sections=[
            FixedLayerSection(
                id=STORY_PROMPT_SECTION_ID,
                title="故事固定提示词",
                content=content,
                priority=10,
                source=STORY_PROMPT_SOURCE,
                source_kind=STORY_PROMPT_SOURCE,
                item_count=1,
            )
        ])

    def _get_catalog(self) -> _StoryPromptCatalog:
        if self._catalog is not None:
            return self._catalog
        from rpg_data.services import get_data_service_gateway

        return get_data_service_gateway().catalog
