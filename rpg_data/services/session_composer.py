"""Typed persistence boundary for Session Composer data."""

from __future__ import annotations

from peewee import Database, IntegrityError

from rpg_data import models
from rpg_data.errors import DataIntegrityError
from rpg_data.model.composer import (
    NarrativeStyle,
    StoryNarrativeStyle,
    StoryQuickReply,
)
from rpg_data.model.session import Session
from rpg_data.repositories.session_composer_repo import SessionComposerRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository

__all__ = ["SessionComposerDataService"]

_NARRATIVE_STYLE_WRITE_INTEGRITY_MESSAGE = (
    "Narrative style write violated persisted constraints"
)
_STORY_NARRATIVE_STYLE_WRITE_INTEGRITY_MESSAGE = (
    "Story narrative style write violated persisted constraints"
)
_QUICK_REPLY_WRITE_INTEGRITY_MESSAGE = (
    "Quick reply write violated persisted constraints"
)


class SessionComposerDataService:
    """Store Composer rows without choosing defaults or effective presentation."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._repo = SessionComposerRepository(database)
        self._workspaces = WorkspaceRepository(database)
        self._stories = StoryRepository(database)
        self._sessions = SessionRepository(database)

    def workspace_exists(self, workspace_id: str) -> bool:
        return self._workspaces.get(str(workspace_id)) is not None

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(str(session_id))

    def list_styles(self, workspace_id: str) -> list[NarrativeStyle] | None:
        if not self.workspace_exists(workspace_id):
            return None
        return self._repo.list_styles(str(workspace_id))

    def create_style(
        self,
        workspace_id: str,
        *,
        name: str,
        prompt: str,
        sort_order: int = 0,
    ) -> NarrativeStyle | None:
        if not self.workspace_exists(workspace_id):
            return None
        try:
            with self._database.atomic():
                return self._repo.create_style(
                    str(workspace_id),
                    name=str(name),
                    prompt=str(prompt),
                    sort_order=int(sort_order),
                )
        except IntegrityError as exc:
            raise DataIntegrityError(
                _NARRATIVE_STYLE_WRITE_INTEGRITY_MESSAGE
            ) from exc

    def update_style(
        self,
        workspace_id: str,
        style_id: int,
        *,
        name: str | None = None,
        prompt: str | None = None,
        sort_order: int | None = None,
    ) -> NarrativeStyle | None:
        current = self._repo.get_style(int(style_id))
        if current is None or current.workspace_id != str(workspace_id):
            return None
        try:
            with self._database.atomic():
                return self._repo.update_style(
                    int(style_id),
                    name=str(name) if name is not None else None,
                    prompt=str(prompt) if prompt is not None else None,
                    sort_order=sort_order,
                )
        except IntegrityError as exc:
            raise DataIntegrityError(
                _NARRATIVE_STYLE_WRITE_INTEGRITY_MESSAGE
            ) from exc

    def delete_style(self, workspace_id: str, style_id: int) -> bool | None:
        current = self._repo.get_style(int(style_id))
        if current is None:
            return False
        if current.workspace_id != str(workspace_id):
            return None
        try:
            with self._database.atomic():
                return self._repo.delete_style(int(style_id))
        except IntegrityError as exc:
            raise DataIntegrityError(
                _NARRATIVE_STYLE_WRITE_INTEGRITY_MESSAGE
            ) from exc

    def list_story_styles(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryNarrativeStyle] | None:
        if self._story(workspace_id, story_id) is None:
            return None
        return self._repo.list_story_styles(int(story_id))

    def mount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        style_id: int,
    ) -> StoryNarrativeStyle | None:
        if self._story(workspace_id, story_id) is None:
            return None
        style = self._repo.get_style(int(style_id))
        if style is None or style.workspace_id != str(workspace_id):
            raise FileNotFoundError(f"narrative style not found in workspace: {style_id}")
        try:
            with self._database.atomic():
                items = self._repo.mount_story_styles(
                    str(workspace_id),
                    int(story_id),
                    [int(style_id)],
                )
        except IntegrityError as exc:
            raise DataIntegrityError(
                _STORY_NARRATIVE_STYLE_WRITE_INTEGRITY_MESSAGE
            ) from exc
        return next(item for item in items if item.narrative_style_id == int(style_id))

    def unmount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
    ) -> bool | None:
        if self._story(workspace_id, story_id) is None:
            return None
        try:
            with self._database.atomic():
                return self._repo.unmount_story_style(int(story_id), int(mount_id))
        except IntegrityError as exc:
            raise DataIntegrityError(
                _STORY_NARRATIVE_STYLE_WRITE_INTEGRITY_MESSAGE
            ) from exc

    def set_story_base_style(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int | None,
    ) -> StoryNarrativeStyle | None:
        if self._story(workspace_id, story_id) is None:
            raise FileNotFoundError("story not found in workspace")
        try:
            with self._database.atomic():
                return self._repo.set_story_base_style(int(story_id), mount_id)
        except IntegrityError as exc:
            raise DataIntegrityError(
                _STORY_NARRATIVE_STYLE_WRITE_INTEGRITY_MESSAGE
            ) from exc

    def list_quick_replies(
        self,
        workspace_id: str,
        story_id: int,
        *,
        enabled_only: bool = False,
    ) -> list[StoryQuickReply] | None:
        if self._story(workspace_id, story_id) is None:
            return None
        return self._repo.list_quick_replies(
            int(story_id),
            enabled_only=bool(enabled_only),
        )

    def create_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str,
        message: str,
        sort_order: int = 0,
        enabled: bool = True,
    ) -> StoryQuickReply | None:
        if self._story(workspace_id, story_id) is None:
            return None
        try:
            with self._database.atomic():
                return self._repo.create_quick_reply(
                    str(workspace_id),
                    int(story_id),
                    title=str(title),
                    message=str(message),
                    sort_order=int(sort_order),
                    enabled=bool(enabled),
                )
        except IntegrityError as exc:
            raise DataIntegrityError(
                _QUICK_REPLY_WRITE_INTEGRITY_MESSAGE
            ) from exc

    def update_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        reply_id: int,
        *,
        title: str | None = None,
        message: str | None = None,
        sort_order: int | None = None,
        enabled: bool | None = None,
    ) -> StoryQuickReply | None:
        current = self._repo.get_quick_reply(int(reply_id))
        if (
            current is None
            or current.workspace_id != str(workspace_id)
            or current.story_id != int(story_id)
        ):
            return None
        try:
            with self._database.atomic():
                return self._repo.update_quick_reply(
                    int(reply_id),
                    title=str(title) if title is not None else None,
                    message=str(message) if message is not None else None,
                    sort_order=sort_order,
                    enabled=enabled,
                )
        except IntegrityError as exc:
            raise DataIntegrityError(
                _QUICK_REPLY_WRITE_INTEGRITY_MESSAGE
            ) from exc

    def delete_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        reply_id: int,
    ) -> bool | None:
        current = self._repo.get_quick_reply(int(reply_id))
        if current is None:
            return False
        if (
            current.workspace_id != str(workspace_id)
            or current.story_id != int(story_id)
        ):
            return None
        try:
            with self._database.atomic():
                return self._repo.delete_quick_reply(int(reply_id))
        except IntegrityError as exc:
            raise DataIntegrityError(
                _QUICK_REPLY_WRITE_INTEGRITY_MESSAGE
            ) from exc

    def _story(self, workspace_id: str, story_id: int) -> models.Story | None:
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != str(workspace_id):
            return None
        return story
