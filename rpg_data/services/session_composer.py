"""Domain services for Session Composer configuration."""

from __future__ import annotations

from peewee import Database

from rpg_data import models
from rpg_data.repositories.session_composer_repo import SessionComposerRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository

__all__ = ["SessionComposerService"]


class SessionComposerService:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._repo = SessionComposerRepository(database)
        self._workspaces = WorkspaceRepository(database)
        self._stories = StoryRepository(database)
        self._sessions = SessionRepository(database)

    def list_modes(self, workspace_id: str) -> list[models.WorkspaceTurnMode] | None:
        if self._workspaces.get(workspace_id) is None:
            return None
        with self._database.atomic():
            return self._repo.ensure_workspace_modes(workspace_id)

    def get_mode(self, workspace_id: str, mode: str) -> models.WorkspaceTurnMode | None:
        items = self.list_modes(workspace_id)
        if items is None:
            return None
        normalized = normalize_turn_mode(mode)
        return next((item for item in items if item.mode == normalized), None)

    def update_mode(
        self,
        workspace_id: str,
        mode: str,
        *,
        short_name: str,
        prompt: str,
    ) -> models.WorkspaceTurnMode | None:
        if self.list_modes(workspace_id) is None:
            return None
        normalized = normalize_turn_mode(mode)
        name = str(short_name or "").strip()
        if not name:
            raise ValueError("short_name must not be empty")
        with self._database.atomic():
            return self._repo.update_workspace_mode(
                workspace_id,
                normalized,
                short_name=name,
                prompt=str(prompt or ""),
            )

    def list_styles(self, workspace_id: str) -> list[models.NarrativeStyle] | None:
        if self._workspaces.get(workspace_id) is None:
            return None
        return self._repo.list_styles(workspace_id)

    def create_style(
        self,
        workspace_id: str,
        *,
        name: str,
        prompt: str,
        sort_order: int = 0,
    ) -> models.NarrativeStyle | None:
        if self._workspaces.get(workspace_id) is None:
            return None
        normalized_name = _required_text(name, "name")
        with self._database.atomic():
            return self._repo.create_style(
                workspace_id,
                name=normalized_name,
                prompt=str(prompt or ""),
                sort_order=int(sort_order),
            )

    def update_style(
        self,
        workspace_id: str,
        style_id: int,
        *,
        name: str | None = None,
        prompt: str | None = None,
        sort_order: int | None = None,
    ) -> models.NarrativeStyle | None:
        current = self._repo.get_style(style_id)
        if current is None or current.workspace_id != workspace_id:
            return None
        with self._database.atomic():
            return self._repo.update_style(
                style_id,
                name=_required_text(name, "name") if name is not None else None,
                prompt=str(prompt) if prompt is not None else None,
                sort_order=sort_order,
            )

    def delete_style(self, workspace_id: str, style_id: int) -> bool | None:
        current = self._repo.get_style(style_id)
        if current is None:
            return False
        if current.workspace_id != workspace_id:
            return None
        with self._database.atomic():
            return self._repo.delete_style(style_id)

    def list_story_styles(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[models.StoryNarrativeStyle] | None:
        if self._story(workspace_id, story_id) is None:
            return None
        return self._repo.list_story_styles(story_id)

    def mount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        style_id: int,
    ) -> models.StoryNarrativeStyle | None:
        if self._story(workspace_id, story_id) is None:
            return None
        style = self._repo.get_style(style_id)
        if style is None or style.workspace_id != workspace_id:
            raise FileNotFoundError(f"narrative style not found in workspace: {style_id}")
        with self._database.atomic():
            items = self._repo.mount_story_styles(workspace_id, story_id, [style_id])
        return next(item for item in items if item.narrative_style_id == int(style_id))

    def unmount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
    ) -> bool | None:
        if self._story(workspace_id, story_id) is None:
            return None
        with self._database.atomic():
            return self._repo.unmount_story_style(story_id, mount_id)

    def set_story_base_style(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int | None,
    ) -> models.StoryNarrativeStyle | None:
        if self._story(workspace_id, story_id) is None:
            raise FileNotFoundError("story not found in workspace")
        with self._database.atomic():
            return self._repo.set_story_base_style(story_id, mount_id)

    def resolve_session_style(
        self,
        session_id: str,
        override_style_id: int | None,
    ) -> models.StoryNarrativeStyle | None:
        session = self._sessions.get(session_id)
        if session is None:
            raise FileNotFoundError(f"session not found: {session_id}")
        items = self._repo.list_story_styles(int(session.story_id))
        if override_style_id is None:
            return next((item for item in items if item.is_base), None)
        selected = next(
            (item for item in items if item.narrative_style_id == int(override_style_id)),
            None,
        )
        if selected is None:
            raise ValueError("narrative style is not mounted on the session story")
        return selected

    def list_quick_replies(
        self,
        workspace_id: str,
        story_id: int,
        *,
        enabled_only: bool = False,
    ) -> list[models.StoryQuickReply] | None:
        if self._story(workspace_id, story_id) is None:
            return None
        return self._repo.list_quick_replies(story_id, enabled_only=enabled_only)

    def create_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str,
        message: str,
        sort_order: int = 0,
        enabled: bool = True,
    ) -> models.StoryQuickReply | None:
        if self._story(workspace_id, story_id) is None:
            return None
        with self._database.atomic():
            return self._repo.create_quick_reply(
                workspace_id,
                story_id,
                title=_required_text(title, "title"),
                message=_required_text(message, "message"),
                sort_order=sort_order,
                enabled=enabled,
            )

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
    ) -> models.StoryQuickReply | None:
        current = self._repo.get_quick_reply(reply_id)
        if current is None or current.workspace_id != workspace_id or current.story_id != int(story_id):
            return None
        with self._database.atomic():
            return self._repo.update_quick_reply(
                reply_id,
                title=_required_text(title, "title") if title is not None else None,
                message=_required_text(message, "message") if message is not None else None,
                sort_order=sort_order,
                enabled=enabled,
            )

    def delete_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        reply_id: int,
    ) -> bool | None:
        current = self._repo.get_quick_reply(reply_id)
        if current is None:
            return False
        if current.workspace_id != workspace_id or current.story_id != int(story_id):
            return None
        with self._database.atomic():
            return self._repo.delete_quick_reply(reply_id)

    def mount_all_workspace_styles(self, workspace_id: str, story_id: int) -> None:
        self._repo.mount_all_workspace_styles(workspace_id, story_id)

    def _story(self, workspace_id: str, story_id: int) -> models.Story | None:
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != workspace_id:
            return None
        return story


def normalize_turn_mode(value: object) -> str:
    normalized = str(value or "").strip().lower() or models.TURN_MODE_IC
    if normalized not in models.TURN_MODES:
        raise ValueError(f"invalid turn mode: {normalized}")
    return normalized


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text
