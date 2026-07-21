from __future__ import annotations

import pytest

from rpg_core.session.composer import SessionComposerApplicationService
from rpg_data.model.composer import (
    StoryNarrativeStyle,
    StoryQuickReply,
    WorkspaceTurnMode,
    WorkspaceTurnModeSeed,
)
from rpg_data.model.session import Session


class _ComposerData:
    def __init__(self) -> None:
        self.session = Session(id="s1", workspace_id="ws", story_id=7)
        self.modes: dict[str, WorkspaceTurnMode] = {}
        self.styles = [
            StoryNarrativeStyle(
                id=10,
                workspace_id="ws",
                story_id=7,
                narrative_style_id=100,
                name="基础",
                is_base=True,
            ),
            StoryNarrativeStyle(
                id=11,
                workspace_id="ws",
                story_id=7,
                narrative_style_id=101,
                name="请求覆盖",
            ),
        ]
        self.quick_replies = [
            StoryQuickReply(
                id=1,
                workspace_id="ws",
                story_id=7,
                title="启用",
                enabled=True,
            ),
            StoryQuickReply(
                id=2,
                workspace_id="ws",
                story_id=7,
                title="停用",
                enabled=False,
            ),
        ]

    def get_session(self, session_id: str) -> Session | None:
        return self.session if session_id == self.session.id else None

    def ensure_modes(
        self,
        workspace_id: str,
        seeds: tuple[WorkspaceTurnModeSeed, ...],
    ) -> list[WorkspaceTurnMode] | None:
        if workspace_id != "ws":
            return None
        for seed in seeds:
            self.modes.setdefault(
                seed.mode,
                WorkspaceTurnMode(
                    workspace_id=workspace_id,
                    mode=seed.mode,
                    short_name=seed.short_name,
                    prompt=seed.prompt,
                    sort_order=seed.sort_order,
                ),
            )
        return sorted(self.modes.values(), key=lambda item: item.sort_order)

    def list_story_styles(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[StoryNarrativeStyle] | None:
        if workspace_id != "ws" or story_id != 7:
            return None
        return list(self.styles)

    def list_quick_replies(
        self,
        workspace_id: str,
        story_id: int,
        *,
        enabled_only: bool = False,
    ) -> list[StoryQuickReply] | None:
        if workspace_id != "ws" or story_id != 7:
            return None
        if enabled_only:
            return [item for item in self.quick_replies if item.enabled]
        return list(self.quick_replies)


def test_composer_owns_default_modes_without_overwriting_workspace_edits() -> None:
    data = _ComposerData()
    data.modes["ooc"] = WorkspaceTurnMode(
        workspace_id="ws",
        mode="ooc",
        short_name="幕后",
        prompt="自定义场外规则",
        sort_order=20,
    )
    service = SessionComposerApplicationService(data)

    modes = service.list_modes("ws")

    assert modes is not None
    assert [item.mode for item in modes] == ["ic", "ooc", "gm"]
    assert service.get_mode("ws", " OOC ").prompt == "自定义场外规则"


def test_composer_resolves_request_override_and_session_projection() -> None:
    data = _ComposerData()
    service = SessionComposerApplicationService(data)

    assert service.resolve_session_style("s1", None).narrative_style_id == 100
    assert service.resolve_session_style("s1", 101).id == 11
    with pytest.raises(ValueError, match="not mounted"):
        service.resolve_session_style("s1", 999)
    snapshot = service.get_snapshot("s1")

    assert snapshot is not None
    assert snapshot.base_narrative_style_id == 100
    assert [item.title for item in snapshot.quick_replies] == ["启用"]
