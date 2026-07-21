"""Session Composer policy and request-scoped presentation resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rpg_core.session.modes import TurnMode, normalize_turn_mode
from rpg_data.model.composer import (
    NarrativeStyle,
    StoryNarrativeStyle,
    StoryQuickReply,
    WorkspaceTurnMode,
    WorkspaceTurnModeSeed,
)
from rpg_data.model.session import Session


DEFAULT_TURN_MODES: tuple[WorkspaceTurnModeSeed, ...] = (
    WorkspaceTurnModeSeed(
        mode=TurnMode.IC.value,
        short_name="角色内",
        prompt="将本轮输入视为玩家角色在故事内的行动或发言，保持沉浸式叙事并自然推进当前场景。",
        sort_order=10,
    ),
    WorkspaceTurnModeSeed(
        mode=TurnMode.OOC.value,
        short_name="场外",
        prompt="将本轮输入视为场外讨论：直接、清晰地回应，不推进剧情，不产生剧情裁定或状态变化。",
        sort_order=20,
    ),
    WorkspaceTurnModeSeed(
        mode=TurnMode.GM.value,
        short_name="主持",
        prompt="将本轮输入视为主持人或导演指令，在遵守既有事实的前提下执行指令，并同步已经确定的剧情状态变化。",
        sort_order=30,
    ),
)


class SessionComposerDataPort(Protocol):
    def get_session(self, session_id: str) -> Session | None: ...

    def list_modes(self, workspace_id: str) -> list[WorkspaceTurnMode] | None: ...

    def ensure_modes(
        self,
        workspace_id: str,
        seeds: tuple[WorkspaceTurnModeSeed, ...],
    ) -> list[WorkspaceTurnMode] | None: ...

    def update_mode(
        self,
        workspace_id: str,
        mode: str,
        *,
        short_name: str,
        prompt: str,
    ) -> WorkspaceTurnMode | None: ...

    def list_styles(self, workspace_id: str) -> list[NarrativeStyle] | None: ...

    def create_style(
        self,
        workspace_id: str,
        *,
        name: str,
        prompt: str,
        sort_order: int = 0,
    ) -> NarrativeStyle | None: ...

    def update_style(
        self,
        workspace_id: str,
        style_id: int,
        *,
        name: str | None = None,
        prompt: str | None = None,
        sort_order: int | None = None,
    ) -> NarrativeStyle | None: ...

    def delete_style(self, workspace_id: str, style_id: int) -> bool | None: ...

    def list_story_styles(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryNarrativeStyle] | None: ...

    def mount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        style_id: int,
    ) -> StoryNarrativeStyle | None: ...

    def unmount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
    ) -> bool | None: ...

    def set_story_base_style(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int | None,
    ) -> StoryNarrativeStyle | None: ...

    def list_quick_replies(
        self,
        workspace_id: str,
        story_id: int,
        *,
        enabled_only: bool = False,
    ) -> list[StoryQuickReply] | None: ...

    def create_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str,
        message: str,
        sort_order: int = 0,
        enabled: bool = True,
    ) -> StoryQuickReply | None: ...

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
    ) -> StoryQuickReply | None: ...

    def delete_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        reply_id: int,
    ) -> bool | None: ...


@dataclass(frozen=True)
class SessionComposerSnapshot:
    session_id: str
    workspace_id: str
    story_id: int
    modes: tuple[WorkspaceTurnMode, ...]
    narrative_styles: tuple[StoryNarrativeStyle, ...]
    base_narrative_style_id: int | None
    quick_replies: tuple[StoryQuickReply, ...]


class SessionComposerApplicationService:
    """Own Composer defaults, validation, and effective request selection."""

    def __init__(self, data: SessionComposerDataPort) -> None:
        self._data = data

    def list_modes(self, workspace_id: str) -> list[WorkspaceTurnMode] | None:
        return self._data.ensure_modes(str(workspace_id), DEFAULT_TURN_MODES)

    def get_mode(
        self,
        workspace_id: str,
        mode: TurnMode | str,
    ) -> WorkspaceTurnMode | None:
        normalized = normalize_turn_mode(mode).value
        items = self.list_modes(workspace_id)
        if items is None:
            return None
        return next((item for item in items if item.mode == normalized), None)

    def update_mode(
        self,
        workspace_id: str,
        mode: TurnMode | str,
        *,
        short_name: str,
        prompt: str,
    ) -> WorkspaceTurnMode | None:
        normalized = normalize_turn_mode(mode).value
        name = _required_text(short_name, "short_name")
        if self.list_modes(workspace_id) is None:
            return None
        return self._data.update_mode(
            str(workspace_id),
            normalized,
            short_name=name,
            prompt=str(prompt or ""),
        )

    def list_styles(self, workspace_id: str) -> list[NarrativeStyle] | None:
        return self._data.list_styles(str(workspace_id))

    def create_style(
        self,
        workspace_id: str,
        *,
        name: str,
        prompt: str,
        sort_order: int = 0,
    ) -> NarrativeStyle | None:
        return self._data.create_style(
            str(workspace_id),
            name=_required_text(name, "name"),
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
    ) -> NarrativeStyle | None:
        return self._data.update_style(
            str(workspace_id),
            int(style_id),
            name=_required_text(name, "name") if name is not None else None,
            prompt=str(prompt) if prompt is not None else None,
            sort_order=sort_order,
        )

    def delete_style(self, workspace_id: str, style_id: int) -> bool | None:
        return self._data.delete_style(str(workspace_id), int(style_id))

    def list_story_styles(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryNarrativeStyle] | None:
        return self._data.list_story_styles(str(workspace_id), int(story_id))

    def mount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        style_id: int,
    ) -> StoryNarrativeStyle | None:
        return self._data.mount_story_style(
            str(workspace_id),
            int(story_id),
            int(style_id),
        )

    def unmount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int,
    ) -> bool | None:
        return self._data.unmount_story_style(
            str(workspace_id),
            int(story_id),
            int(mount_id),
        )

    def set_story_base_style(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int | None,
    ) -> StoryNarrativeStyle | None:
        return self._data.set_story_base_style(
            str(workspace_id),
            int(story_id),
            int(mount_id) if mount_id is not None else None,
        )

    def resolve_session_style(
        self,
        session_id: str,
        request_override_style_id: int | None,
    ) -> StoryNarrativeStyle | None:
        session = self._data.get_session(str(session_id))
        if session is None:
            raise FileNotFoundError(f"session not found: {session_id}")
        items = self._data.list_story_styles(
            session.workspace_id,
            int(session.story_id),
        )
        if items is None:
            raise FileNotFoundError(f"session Story not found: {session_id}")
        if request_override_style_id is None:
            return next((item for item in items if item.is_base), None)
        selected = next(
            (
                item
                for item in items
                if item.narrative_style_id == int(request_override_style_id)
            ),
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
    ) -> list[StoryQuickReply] | None:
        return self._data.list_quick_replies(
            str(workspace_id),
            int(story_id),
            enabled_only=enabled_only,
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
        return self._data.create_quick_reply(
            str(workspace_id),
            int(story_id),
            title=_required_text(title, "title"),
            message=_required_text(message, "message"),
            sort_order=int(sort_order),
            enabled=bool(enabled),
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
    ) -> StoryQuickReply | None:
        return self._data.update_quick_reply(
            str(workspace_id),
            int(story_id),
            int(reply_id),
            title=_required_text(title, "title") if title is not None else None,
            message=(
                _required_text(message, "message") if message is not None else None
            ),
            sort_order=sort_order,
            enabled=enabled,
        )

    def delete_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        reply_id: int,
    ) -> bool | None:
        return self._data.delete_quick_reply(
            str(workspace_id),
            int(story_id),
            int(reply_id),
        )

    def get_snapshot(self, session_id: str) -> SessionComposerSnapshot | None:
        session = self._data.get_session(str(session_id))
        if session is None:
            return None
        modes = self.list_modes(session.workspace_id) or []
        styles = self.list_story_styles(session.workspace_id, session.story_id) or []
        quick_replies = self.list_quick_replies(
            session.workspace_id,
            session.story_id,
            enabled_only=True,
        ) or []
        base_style = next((item for item in styles if item.is_base), None)
        return SessionComposerSnapshot(
            session_id=session.id,
            workspace_id=session.workspace_id,
            story_id=session.story_id,
            modes=tuple(modes),
            narrative_styles=tuple(styles),
            base_narrative_style_id=(
                base_style.narrative_style_id if base_style is not None else None
            ),
            quick_replies=tuple(quick_replies),
        )


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


__all__ = [
    "DEFAULT_TURN_MODES",
    "SessionComposerApplicationService",
    "SessionComposerDataPort",
    "SessionComposerSnapshot",
]
