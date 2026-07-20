"""Story and Session catalog creation application policy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ContextManager, Mapping, Protocol

from rpg_core.story.template import validate_story_text_template
from rpg_core.session.status import (
    SessionStatusDataPort,
    SessionStatusLifecycleService,
)
from rpg_data import models as data_models
from rpg_data.model.session import SESSION_LIFECYCLE_READY, Session


class SessionCatalogDataPort(SessionStatusDataPort, Protocol):
    def transaction(self) -> ContextManager[None]: ...

    def create_story(
        self,
        workspace_id: str,
        *,
        title: str,
        summary: str,
        story_prompt: str,
        openings: Sequence[data_models.StoryOpeningInput],
    ) -> data_models.Story | None: ...

    def update_story(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str | None,
        summary: str | None,
        story_prompt: str | None,
        openings: Sequence[data_models.StoryOpeningInput] | None,
    ) -> data_models.Story | None: ...

    def get_story(
        self,
        workspace_id: str,
        story_id: int,
    ) -> data_models.Story | None: ...

    def create_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        session_id: str | None,
        title: str,
        description: str,
        player_character_id: int | None,
        player_character_snapshot_json: str,
        story_opening_id: int | None,
        lifecycle: str,
    ) -> Session | None: ...

    def get_session(self, session_id: str) -> Session | None: ...

    def list_rp_module_catalog(self) -> list[data_models.RPModuleCatalogEntry]: ...

    def set_story_rp_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
        *,
        enabled: bool,
        config: Mapping[str, object],
    ) -> data_models.StoryRPModule | None: ...

    def list_narrative_styles(
        self,
        workspace_id: str,
    ) -> list[data_models.NarrativeStyle] | None: ...

    def mount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        style_id: int,
    ) -> data_models.StoryNarrativeStyle | None: ...


class SessionCatalogService:
    """Create catalog aggregates and apply their initial mount policies."""

    def __init__(self, data: SessionCatalogDataPort) -> None:
        self._data = data

    def create_story(
        self,
        workspace_id: str,
        *,
        title: str,
        summary: str = "",
        story_prompt: str = "",
        openings: Sequence[data_models.StoryOpeningInput] = (),
    ) -> data_models.Story | None:
        normalized_openings = normalize_story_openings(openings)
        validate_story_text_template(story_prompt)
        with self._data.transaction():
            story = self._data.create_story(
                workspace_id,
                title=title,
                summary=summary,
                story_prompt=story_prompt,
                openings=normalized_openings,
            )
            if story is None:
                return None
            for entry in self._data.list_rp_module_catalog():
                if entry.default_story_enabled:
                    mounted = self._data.set_story_rp_module(
                        workspace_id,
                        story.id,
                        entry.module_name,
                        enabled=True,
                        config={},
                    )
                    if mounted is None:
                        raise RuntimeError(
                            "new Story disappeared while mounting RP Modules: "
                            f"{story.id}"
                        )
            styles = self._data.list_narrative_styles(workspace_id) or []
            for style in styles:
                mounted_style = self._data.mount_story_style(
                    workspace_id,
                    story.id,
                    style.id,
                )
                if mounted_style is None:
                    raise RuntimeError(
                        "new Story disappeared while mounting narrative styles: "
                        f"{story.id}"
                    )
            return self._data.get_story(workspace_id, story.id)

    def update_story(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        story_prompt: str | None = None,
        openings: Sequence[data_models.StoryOpeningInput] | None = None,
    ) -> data_models.Story | None:
        if story_prompt is not None:
            validate_story_text_template(story_prompt)
        normalized_openings = (
            normalize_story_openings(openings)
            if openings is not None
            else None
        )
        return self._data.update_story(
            workspace_id,
            story_id,
            title=title,
            summary=summary,
            story_prompt=story_prompt,
            openings=normalized_openings,
        )

    def create_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        session_id: str | None = None,
        title: str = "",
        description: str = "",
        player_character_id: int | None = None,
        player_character_snapshot_json: str = "{}",
        story_opening_id: int | None = None,
        lifecycle: str = SESSION_LIFECYCLE_READY,
    ) -> Session | None:
        with self._data.transaction():
            session = self._data.create_session(
                workspace_id,
                story_id,
                session_id=session_id,
                title=title,
                description=description,
                player_character_id=player_character_id,
                player_character_snapshot_json=player_character_snapshot_json,
                story_opening_id=story_opening_id,
                lifecycle=lifecycle,
            )
            if session is None:
                return None
            SessionStatusLifecycleService(self._data).initialize(session.id)
            return self._data.get_session(session.id)


def normalize_story_openings(
    openings: Sequence[data_models.StoryOpeningInput],
) -> tuple[data_models.StoryOpeningInput, ...]:
    if len(openings) > data_models.MAX_STORY_OPENINGS:
        raise ValueError(
            f"story supports at most {data_models.MAX_STORY_OPENINGS} openings"
        )
    normalized: list[data_models.StoryOpeningInput] = []
    titles: set[str] = set()
    ids: set[int] = set()
    for item in openings:
        opening_id = item.id
        if opening_id is not None:
            if isinstance(opening_id, bool) or int(opening_id) <= 0:
                raise ValueError("story opening id must be a positive integer")
            opening_id = int(opening_id)
            if opening_id in ids:
                raise ValueError(f"duplicate story opening id: {opening_id}")
            ids.add(opening_id)
        title = str(item.title or "").strip()
        message = str(item.message or "").strip()
        if not title:
            raise ValueError("story opening title must not be empty")
        if not message:
            raise ValueError("story opening message must not be empty")
        if title in titles:
            raise ValueError(f"duplicate story opening title: {title}")
        titles.add(title)
        validate_story_text_template(message)
        normalized.append(
            data_models.StoryOpeningInput(
                id=opening_id,
                title=title,
                message=message,
            )
        )
    return tuple(normalized)


__all__ = ["SessionCatalogService", "normalize_story_openings"]
