from __future__ import annotations

from types import MappingProxyType

import pytest

from rpg_core.rp_modules.constants import RP_MODULE_MESSAGE_MODE_NAME
from rpg_core.rp_modules.models import (
    RPModuleSelection,
    RPModuleSelectionSnapshot,
)
from rpg_core.session.composer import SessionComposerApplicationService
from rpg_data.model.composer import (
    StoryNarrativeStyle,
    StoryQuickReply,
)
from rpg_data.model.session import Session


class _ComposerData:
    def __init__(self) -> None:
        self.session = Session(id="s1", workspace_id="ws", story_id=7)
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


class _RPModules:
    def __init__(self, *, message_mode_enabled: bool) -> None:
        self._message_mode_enabled = message_mode_enabled

    def resolve_snapshot(self, session_id: str) -> RPModuleSelectionSnapshot:
        return RPModuleSelectionSnapshot(
            session_id=session_id,
            story_id=7,
            global_enabled=True,
            modules=(
                RPModuleSelection(
                    name=RP_MODULE_MESSAGE_MODE_NAME,
                    display_name="消息模式",
                    description="",
                    sort_order=5,
                    system_enabled=True,
                    story_mounted=True,
                    story_enabled=True,
                    session_enabled_override=None,
                    effective_enabled=self._message_mode_enabled,
                    system_config=MappingProxyType({}),
                    story_config=MappingProxyType({}),
                    session_config=MappingProxyType({}),
                    effective_config=MappingProxyType({}),
                    config_sources=MappingProxyType({}),
                ),
            ),
        )


def test_composer_exposes_builtin_modes_only_when_message_mode_is_enabled() -> None:
    enabled = SessionComposerApplicationService(
        _ComposerData(),
        _RPModules(message_mode_enabled=True),
    )
    disabled = SessionComposerApplicationService(
        _ComposerData(),
        _RPModules(message_mode_enabled=False),
    )

    enabled_snapshot = enabled.get_snapshot("s1")
    disabled_snapshot = disabled.get_snapshot("s1")

    assert enabled_snapshot is not None
    assert [item.mode.value for item in enabled_snapshot.modes] == [
        "neutral",
        "ic",
        "ooc",
        "gm",
    ]
    assert disabled_snapshot is not None
    assert disabled_snapshot.modes == ()


def test_composer_resolves_request_override_and_session_projection() -> None:
    data = _ComposerData()
    service = SessionComposerApplicationService(
        data,
        _RPModules(message_mode_enabled=True),
    )

    assert service.resolve_session_style("s1", None).narrative_style_id == 100
    assert service.resolve_session_style("s1", 101).id == 11
    with pytest.raises(ValueError, match="not mounted"):
        service.resolve_session_style("s1", 999)
    snapshot = service.get_snapshot("s1")

    assert snapshot is not None
    assert snapshot.base_narrative_style_id == 100
    assert [item.title for item in snapshot.quick_replies] == ["启用"]
