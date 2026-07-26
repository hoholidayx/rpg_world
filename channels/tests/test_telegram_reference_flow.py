from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from channels.telegram.action_registry import CallbackResolutionStatus
from channels.telegram.adapter import TelegramAdapter
from channels.telegram.reference_flow import (
    REFERENCE_ACTION_CHARACTER_CARD,
    REFERENCE_ACTION_CHARACTER_DETAIL,
    REFERENCE_ACTION_CHARACTER_DETAIL_LIST,
    REFERENCE_ACTION_CHARACTER_LIST,
    REFERENCE_ACTION_PERSISTENT_MEMORY_LIST,
    REFERENCE_ACTION_STATUS_LIST,
    REFERENCE_ACTION_STORY_MEMORY_LIST,
    REFERENCE_ACTION_STORY_MEMORY_DETAIL,
    REFERENCE_ACTION_SUMMARY_LIST,
    TelegramReferenceFlow,
)
from channels.tests.conftest import FakeAgent
from rpg_core.session.reference import (
    CharacterCard,
    CharacterDetail,
    CharacterDetailSummary,
    CharacterSummary,
    EvidenceReference,
    PersistentMemoryDetail,
    PersistentMemorySummary,
    ReferencePage,
    SessionReferenceLocator,
    SessionReferenceNotFoundError,
    SessionReferenceScope,
    SessionReferenceUnavailableError,
    StatusRow,
    StatusTableDetail,
    StatusTableSummary,
    StoryMemoryDetail,
    StoryMemorySummary,
    SummaryDetail,
    SummarySummary,
)


_LOCATOR = SessionReferenceLocator(
    session_id="tg_default",
    workspace_id="tg_workspace",
    story_id=1,
)


def _page(items, page: int, page_size: int):
    total = len(items)
    start = (page - 1) * page_size
    return ReferencePage(
        items=tuple(items[start : start + page_size]),
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


class _ReferenceReader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.characters = [
            CharacterSummary(
                id=index,
                name=f"角色 {index}",
                description=f"角色 {index} 的简介",
                is_player=index == 1,
                details_count=9 if index == 1 else 0,
                version=1,
                updated_at="2026-07-26",
            )
            for index in range(1, 10)
        ]
        self.character_details = [
            CharacterDetailSummary(
                id=index,
                title=f"详情 {index}",
                version=1,
                updated_at="2026-07-26",
            )
            for index in range(1, 10)
        ]
        self.character_card_version = 1
        self.character_detail_version = 1
        self.status_detail_version = 1
        self.summary_detail_updated_at = "2026-07-26"
        self.story_memory_detail_version = 1
        self.persistent_memory_detail_revision = 1
        self.status = StatusTableSummary(
            id=10,
            name="当前场景",
            description="场景公开描述",
            kind="scene",
            character_id=None,
            character_name=None,
            version=1,
            updated_at="2026-07-26",
        )
        self.status_items = [self.status]
        self.summary = SummarySummary(
            id="overall",
            title="整体归纳",
            excerpt="一段剧情归纳",
            kind="overall",
            turn_start=1,
            turn_end=5,
            time="夜晚",
            location="旧城",
            characters=("艾达",),
            updated_at="2026-07-26",
        )
        self.story_memory = StoryMemorySummary(
            id=20,
            title="失落的钥匙",
            excerpt="钥匙被藏在钟楼。",
            memory_kind="world_fact",
            epistemic_status="confirmed",
            salience=0.8,
            turn_start=2,
            turn_end=3,
            evidence=(EvidenceReference(turn_id=2, message_id=12),),
            version=1,
            updated_at="2026-07-26",
        )
        self.persistent_memory = PersistentMemorySummary(
            id="memory-1",
            title="守门人的承诺",
            excerpt="守门人答应午夜放行。",
            memory_kind="commitment",
            epistemic_status="confirmed",
            salience=0.9,
            evidence=(EvidenceReference(turn_id=4, message_id=21),),
            revision_number=1,
            updated_at="2026-07-26",
        )
        self.fail_character_detail = False

    async def get_scope(self, locator):
        self.calls.append(("get_scope", locator))
        return SessionReferenceScope(
            locator=locator,
            title="Telegram",
            lifecycle="ready",
            player_character_id=1,
            version=1,
            updated_at="2026-07-26",
        )

    async def list_characters(self, locator, *, page=1, page_size=8):
        self.calls.append(("list_characters", (locator, page, page_size)))
        return _page(self.characters, page, page_size)

    async def get_character(self, locator, character_id):
        self.calls.append(("get_character", (locator, character_id)))
        return CharacterCard(
            id=character_id,
            name=f"角色 {character_id}",
            description="完整角色卡描述",
            is_player=character_id == 1,
            details_count=len(self.character_details),
            version=self.character_card_version,
            updated_at="2026-07-26",
        )

    async def list_character_details(
        self,
        locator,
        character_id,
        *,
        page=1,
        page_size=8,
    ):
        self.calls.append(
            (
                "list_character_details",
                (locator, character_id, page, page_size),
            )
        )
        return _page(self.character_details, page, page_size)

    async def get_character_detail(self, locator, character_id, detail_id):
        self.calls.append(
            ("get_character_detail", (locator, character_id, detail_id))
        )
        if self.fail_character_detail:
            raise SessionReferenceNotFoundError("gone")
        return CharacterDetail(
            id=detail_id,
            character_id=character_id,
            title="性格",
            content="勇敢但谨慎。",
            version=self.character_detail_version,
            updated_at="2026-07-26",
        )

    async def list_status_tables(
        self,
        locator,
        *,
        page=1,
        page_size=8,
        character_id=None,
    ):
        self.calls.append(
            (
                "list_status_tables",
                (locator, page, page_size, character_id),
            )
        )
        return _page(self.status_items, page, page_size)

    async def get_status_table(self, locator, table_id):
        self.calls.append(("get_status_table", (locator, table_id)))
        return StatusTableDetail(
            id=table_id,
            name=self.status.name,
            description=self.status.description,
            kind=self.status.kind,
            character_id=None,
            character_name=None,
            rows=(
                StatusRow(key="地点", value="钟楼"),
                StatusRow(key="时间", value="午夜"),
            ),
            version=self.status_detail_version,
            updated_at="2026-07-26",
        )

    async def list_summaries(self, locator, *, page=1, page_size=8):
        self.calls.append(("list_summaries", (locator, page, page_size)))
        return _page([self.summary], page, page_size)

    async def get_summary(self, locator, summary_id):
        self.calls.append(("get_summary", (locator, summary_id)))
        return SummaryDetail(
            **{
                **self.summary.__dict__,
                "updated_at": self.summary_detail_updated_at,
            },
            text="玩家抵达旧城，并找到了钟楼。",
        )

    async def list_story_memories(self, locator, *, page=1, page_size=8):
        self.calls.append(("list_story_memories", (locator, page, page_size)))
        return _page([self.story_memory], page, page_size)

    async def get_story_memory(self, locator, memory_id):
        self.calls.append(("get_story_memory", (locator, memory_id)))
        return StoryMemoryDetail(
            **{
                **self.story_memory.__dict__,
                "version": self.story_memory_detail_version,
            },
            text="钥匙被藏在钟楼顶层的铜钟后方。",
        )

    async def list_persistent_memories(
        self,
        locator,
        *,
        page=1,
        page_size=8,
    ):
        self.calls.append(
            ("list_persistent_memories", (locator, page, page_size))
        )
        return _page([self.persistent_memory], page, page_size)

    async def get_persistent_memory(self, locator, memory_id):
        self.calls.append(("get_persistent_memory", (locator, memory_id)))
        return PersistentMemoryDetail(
            **{
                **self.persistent_memory.__dict__,
                "revision_number": self.persistent_memory_detail_revision,
            },
            text="守门人答应在午夜钟响后打开北门。",
        )


def _action(flow: TelegramReferenceFlow, registry, kind: str, **payload):
    del flow
    return registry.create(
        kind=kind,
        chat_id="123",
        session_id=_LOCATOR.session_id,
        payload=payload,
    )


def _button_texts(view) -> list[str]:
    return [
        button.text
        for row in view.reply_markup.inline_keyboard
        for button in row
    ]


def _button_action(registry, view, text: str):
    callback_data = next(
        button.callback_data
        for row in view.reply_markup.inline_keyboard
        for button in row
        if button.text == text
    )
    resolution = registry.resolve(
        callback_data,
        chat_id="123",
        current_session_id=_LOCATOR.session_id,
    )
    assert resolution.action is not None
    return resolution.action


async def test_root_exposes_all_five_reference_categories() -> None:
    from channels.telegram.action_registry import TelegramActionRegistry

    registry = TelegramActionRegistry()
    reader = _ReferenceReader()
    flow = TelegramReferenceFlow(registry, reader)

    view = await flow.render_root(_LOCATOR, "123")

    assert _button_texts(view) == [
        "角色卡",
        "状态表",
        "剧情归纳",
        "故事记忆",
        "持久记忆",
    ]
    assert "截至当前已提交内容" in view.html


async def test_character_and_character_detail_lists_are_eight_per_page() -> None:
    from channels.telegram.action_registry import TelegramActionRegistry

    registry = TelegramActionRegistry()
    reader = _ReferenceReader()
    flow = TelegramReferenceFlow(registry, reader)

    character_view = await flow.render_action(
        _LOCATOR,
        "123",
        _action(flow, registry, REFERENCE_ACTION_CHARACTER_LIST, page=1),
    )

    assert len([text for text in _button_texts(character_view) if "角色 " in text]) == 8
    assert "下一页 ›" in _button_texts(character_view)
    assert reader.calls[-1][1][2] == 8

    detail_list_action = registry.create(
        kind="reference_character_detail_list",
        chat_id="123",
        session_id=_LOCATOR.session_id,
        payload={
            "character_id": 1,
            "page": 2,
            "character_list_page": 1,
        },
    )
    detail_view = await flow.render_action(
        _LOCATOR,
        "123",
        detail_list_action,
    )

    assert "详情 9" in _button_texts(detail_view)
    assert "详情 1" not in _button_texts(detail_view)
    assert (
        "list_character_details",
        (_LOCATOR, 1, 2, 8),
    ) in reader.calls


async def test_long_character_detail_uses_safe_body_pages() -> None:
    from channels.telegram.action_registry import TelegramActionRegistry

    registry = TelegramActionRegistry()
    reader = _ReferenceReader()

    async def long_detail(locator, character_id, detail_id):
        return CharacterDetail(
            id=detail_id,
            character_id=character_id,
            title="完整背景",
            content="很长的故事。\n" * 900,
            version=1,
            updated_at="2026-07-26",
        )

    reader.get_character_detail = long_detail
    flow = TelegramReferenceFlow(registry, reader)
    action = _action(
        flow,
        registry,
        REFERENCE_ACTION_CHARACTER_DETAIL,
        character_id=1,
        detail_id=1,
        detail_list_page=1,
        character_list_page=1,
        detail_version=1,
    )

    first = await flow.render_action(_LOCATOR, "123", action)

    assert len(first.html) <= 4096
    assert "正文 1/" in first.html
    assert "下一段 ›" in _button_texts(first)
    next_data = next(
        button.callback_data
        for row in first.reply_markup.inline_keyboard
        for button in row
        if button.text == "下一段 ›"
    )
    resolution = registry.resolve(
        next_data,
        chat_id="123",
        current_session_id=_LOCATOR.session_id,
    )
    assert resolution.action is not None
    assert resolution.action.payload["detail_version"] == 1
    second = await flow.render_action(
        _LOCATOR,
        "123",
        resolution.action,
    )
    assert len(second.html) <= 4096
    assert "正文 2/" in second.html


async def test_atomic_long_markdown_link_falls_back_to_plain_text_pages() -> None:
    from channels.telegram.action_registry import TelegramActionRegistry

    registry = TelegramActionRegistry()
    reader = _ReferenceReader()
    reader.get_character_detail = AsyncMock(
        return_value=CharacterDetail(
            id=1,
            character_id=1,
            title="链接资料",
            content="[x](" + "a" * 4_000 + ")",
            version=1,
            updated_at="2026-07-26",
        )
    )
    flow = TelegramReferenceFlow(registry, reader)

    view = await flow.render_action(
        _LOCATOR,
        "123",
        _action(
            flow,
            registry,
            REFERENCE_ACTION_CHARACTER_DETAIL,
            character_id=1,
            detail_id=1,
            detail_list_page=1,
            character_list_page=1,
            detail_version=1,
        ),
    )

    assert len(view.html) <= 4096
    assert "正文 1/" in view.html
    assert "[x](" in view.html
    assert "<a " not in view.html
    assert "下一段 ›" in _button_texts(view)


async def test_detail_callbacks_reject_changed_versions() -> None:
    from channels.telegram.action_registry import TelegramActionRegistry

    registry = TelegramActionRegistry()
    reader = _ReferenceReader()
    flow = TelegramReferenceFlow(registry, reader)

    character_list = await flow.render_action(
        _LOCATOR,
        "123",
        _action(flow, registry, REFERENCE_ACTION_CHARACTER_LIST, page=1),
    )
    character_action = _button_action(
        registry,
        character_list,
        "★ 角色 1",
    )
    assert character_action.payload["character_version"] == 1
    reader.character_card_version = 2
    with pytest.raises(SessionReferenceNotFoundError):
        await flow.render_action(_LOCATOR, "123", character_action)
    reader.character_card_version = 1

    detail_list = await flow.render_action(
        _LOCATOR,
        "123",
        _action(
            flow,
            registry,
            REFERENCE_ACTION_CHARACTER_DETAIL_LIST,
            character_id=1,
            page=1,
            character_list_page=1,
            character_version=1,
        ),
    )
    detail_action = _button_action(registry, detail_list, "详情 1")
    assert detail_action.payload["detail_version"] == 1
    reader.character_detail_version = 2
    with pytest.raises(SessionReferenceNotFoundError):
        await flow.render_action(_LOCATOR, "123", detail_action)

    mismatch_cases = [
        (
            REFERENCE_ACTION_STATUS_LIST,
            "场景 · 当前场景",
            "status_version",
            "status_detail_version",
            2,
        ),
        (
            REFERENCE_ACTION_SUMMARY_LIST,
            "整体归纳",
            "summary_updated_at",
            "summary_detail_updated_at",
            "2026-07-27",
        ),
        (
            REFERENCE_ACTION_STORY_MEMORY_LIST,
            "1. 失落的钥匙",
            "memory_version",
            "story_memory_detail_version",
            2,
        ),
        (
            REFERENCE_ACTION_PERSISTENT_MEMORY_LIST,
            "1. 守门人的承诺",
            "memory_revision",
            "persistent_memory_detail_revision",
            2,
        ),
    ]
    for list_kind, label, payload_key, reader_attr, changed_value in mismatch_cases:
        list_view = await flow.render_action(
            _LOCATOR,
            "123",
            _action(flow, registry, list_kind, page=1),
        )
        detail_action = _button_action(registry, list_view, label)
        assert payload_key in detail_action.payload
        setattr(reader, reader_attr, changed_value)
        with pytest.raises(SessionReferenceNotFoundError):
            await flow.render_action(_LOCATOR, "123", detail_action)


async def test_memory_lists_number_duplicate_titles_without_exposing_ids() -> None:
    from channels.telegram.action_registry import TelegramActionRegistry

    registry = TelegramActionRegistry()
    reader = _ReferenceReader()
    duplicate_story = StoryMemorySummary(
        **{
            **reader.story_memory.__dict__,
            "id": 21,
            "excerpt": "另一条同轮次、同类型的故事事实。",
        }
    )
    duplicate_persistent = PersistentMemorySummary(
        **{
            **reader.persistent_memory.__dict__,
            "id": "memory-secret-2",
            "excerpt": "另一条同类型、同 revision 的长期事实。",
        }
    )
    reader.list_story_memories = AsyncMock(
        return_value=_page(
            [reader.story_memory, duplicate_story],
            1,
            8,
        )
    )
    reader.list_persistent_memories = AsyncMock(
        return_value=_page(
            [reader.persistent_memory, duplicate_persistent],
            1,
            8,
        )
    )
    flow = TelegramReferenceFlow(registry, reader)

    story_view = await flow.render_action(
        _LOCATOR,
        "123",
        _action(flow, registry, REFERENCE_ACTION_STORY_MEMORY_LIST, page=1),
    )
    persistent_view = await flow.render_action(
        _LOCATOR,
        "123",
        _action(
            flow,
            registry,
            REFERENCE_ACTION_PERSISTENT_MEMORY_LIST,
            page=1,
        ),
    )

    assert _button_texts(story_view)[:2] == [
        "1. 失落的钥匙",
        "2. 失落的钥匙",
    ]
    assert _button_texts(persistent_view)[:2] == [
        "1. 守门人的承诺",
        "2. 守门人的承诺",
    ]
    assert "memory-secret-2" not in persistent_view.html


async def test_root_and_resource_lists_clamp_unbounded_dynamic_fields() -> None:
    from channels.telegram.action_registry import TelegramActionRegistry

    registry = TelegramActionRegistry()
    reader = _ReferenceReader()
    long_value = "&<" * 3_000
    reader.get_scope = AsyncMock(
        return_value=SessionReferenceScope(
            locator=_LOCATOR,
            title=long_value,
            lifecycle="ready",
            player_character_id=1,
            version=1,
            updated_at="2026-07-26",
        )
    )
    reader.characters = [
        CharacterSummary(
            id=index,
            name=long_value,
            description=long_value,
            is_player=index == 1,
            details_count=8,
            version=1,
            updated_at="2026-07-26",
        )
        for index in range(1, 9)
    ]
    reader.character_details = [
        CharacterDetailSummary(
            id=index,
            title=long_value,
            version=1,
            updated_at="2026-07-26",
        )
        for index in range(1, 9)
    ]
    reader.get_character = AsyncMock(
        return_value=CharacterCard(
            id=1,
            name=long_value,
            description=long_value,
            is_player=True,
            details_count=8,
            version=1,
            updated_at="2026-07-26",
        )
    )
    reader.status_items = [
        StatusTableSummary(
            id=index,
            name=long_value,
            description=long_value,
            kind="normal",
            character_id=index,
            character_name=long_value,
            version=1,
            updated_at="2026-07-26",
        )
        for index in range(1, 9)
    ]
    reader.list_summaries = AsyncMock(
        return_value=_page(
            [
                SummarySummary(
                    **{
                        **reader.summary.__dict__,
                        "id": str(index),
                        "title": long_value,
                        "excerpt": long_value,
                    }
                )
                for index in range(1, 9)
            ],
            1,
            8,
        )
    )
    reader.list_story_memories = AsyncMock(
        return_value=_page(
            [
                StoryMemorySummary(
                    **{
                        **reader.story_memory.__dict__,
                        "id": index,
                        "title": long_value,
                        "excerpt": long_value,
                    }
                )
                for index in range(1, 9)
            ],
            1,
            8,
        )
    )
    reader.list_persistent_memories = AsyncMock(
        return_value=_page(
            [
                PersistentMemorySummary(
                    **{
                        **reader.persistent_memory.__dict__,
                        "id": f"memory-{index}",
                        "title": long_value,
                        "excerpt": long_value,
                    }
                )
                for index in range(1, 9)
            ],
            1,
            8,
        )
    )
    flow = TelegramReferenceFlow(registry, reader)

    views = [
        await flow.render_root(_LOCATOR, "123"),
        await flow.render_action(
            _LOCATOR,
            "123",
            _action(flow, registry, REFERENCE_ACTION_CHARACTER_LIST, page=1),
        ),
        await flow.render_action(
            _LOCATOR,
            "123",
            _action(
                flow,
                registry,
                REFERENCE_ACTION_CHARACTER_DETAIL_LIST,
                character_id=1,
                page=1,
                character_list_page=1,
                character_version=1,
            ),
        ),
        await flow.render_action(
            _LOCATOR,
            "123",
            _action(flow, registry, REFERENCE_ACTION_STATUS_LIST, page=1),
        ),
        await flow.render_action(
            _LOCATOR,
            "123",
            _action(flow, registry, REFERENCE_ACTION_SUMMARY_LIST, page=1),
        ),
        await flow.render_action(
            _LOCATOR,
            "123",
            _action(
                flow,
                registry,
                REFERENCE_ACTION_STORY_MEMORY_LIST,
                page=1,
            ),
        ),
        await flow.render_action(
            _LOCATOR,
            "123",
            _action(
                flow,
                registry,
                REFERENCE_ACTION_PERSISTENT_MEMORY_LIST,
                page=1,
            ),
        ),
    ]

    assert all(len(view.html) <= 4096 for view in views)
    assert all("…" in view.html for view in views)
    assert all(
        len(button.text) <= 48
        for view in views
        for row in view.reply_markup.inline_keyboard
        for button in row
    )

    cross_field_name = f"[{'N' * 150}"
    cross_field_description = "](" + '"' * 150 + ")"
    reader.characters = [
        CharacterSummary(
            id=index,
            name=cross_field_name,
            description=cross_field_description,
            is_player=False,
            details_count=0,
            version=1,
            updated_at="2026-07-26",
        )
        for index in range(1, 9)
    ]
    cross_field_view = await flow.render_action(
        _LOCATOR,
        "123",
        _action(flow, registry, REFERENCE_ACTION_CHARACTER_LIST, page=1),
    )
    assert len(cross_field_view.html) <= 4096
    assert "…" in cross_field_view.html


async def test_status_list_renders_stable_group_headings() -> None:
    from channels.telegram.action_registry import TelegramActionRegistry

    registry = TelegramActionRegistry()
    reader = _ReferenceReader()
    reader.status_items = [
        reader.status,
        StatusTableSummary(
            id=11,
            name="关系",
            description="",
            kind="normal",
            character_id=1,
            character_name="艾达",
            version=1,
            updated_at="2026-07-26",
        ),
        StatusTableSummary(
            id=12,
            name="装备",
            description="",
            kind="normal",
            character_id=1,
            character_name="艾达",
            version=1,
            updated_at="2026-07-26",
        ),
        StatusTableSummary(
            id=13,
            name="旧角色线索",
            description="",
            kind="normal",
            character_id=99,
            character_name=None,
            version=1,
            updated_at="2026-07-26",
        ),
        StatusTableSummary(
            id=14,
            name="世界事件",
            description="",
            kind="normal",
            character_id=None,
            character_name=None,
            version=1,
            updated_at="2026-07-26",
        ),
    ]
    flow = TelegramReferenceFlow(registry, reader)

    view = await flow.render_action(
        _LOCATOR,
        "123",
        _action(flow, registry, REFERENCE_ACTION_STATUS_LIST, page=1),
    )

    scene_index = view.html.index("场景")
    character_index = view.html.index("角色状态 · 艾达")
    stale_character_index = view.html.index("角色状态 · 已关联角色")
    unbound_index = view.html.index("未关联状态")
    assert (
        scene_index
        < character_index
        < stale_character_index
        < unbound_index
    )
    assert view.html.count("角色状态 · 艾达") == 1


async def test_story_memory_evidence_is_reference_only() -> None:
    from channels.telegram.action_registry import TelegramActionRegistry

    registry = TelegramActionRegistry()
    reader = _ReferenceReader()
    flow = TelegramReferenceFlow(registry, reader)
    action = _action(
        flow,
        registry,
        REFERENCE_ACTION_STORY_MEMORY_DETAIL,
        memory_id=20,
        list_page=1,
    )

    view = await flow.render_action(_LOCATOR, "123", action)

    assert "Turn 2 · Msg 12" in view.html
    assert "钥匙被藏在钟楼顶层" in view.html
    assert "<a " not in view.html


def _adapter_app(*, edit_result=True):
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock(
        return_value=MagicMock(message_id=100)
    )
    app.bot.edit_message_text = AsyncMock(return_value=edit_result)
    return app


def _command_update(text: str):
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.effective_chat.id = 123
    update.effective_user.id = 456
    return update


def _callback_update(callback_data: str, *, message_id: int = 100):
    update = MagicMock()
    query = MagicMock()
    query.data = callback_data
    query.message = MagicMock()
    query.message.chat.id = 123
    query.message.message_id = message_id
    query.answer = AsyncMock()
    update.callback_query = query
    return update


async def test_info_and_reference_callbacks_are_allowed_while_turn_is_busy() -> None:
    reader = _ReferenceReader()
    adapter = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        reference_menu_enabled=True,
        reference_reader=reader,
    )
    adapter._app = _adapter_app()
    reservation = adapter._turn_flow.reserve("123", "tg_default")
    assert reservation.accepted and reservation.active is not None

    await adapter._on_command(_command_update("/info"), object())
    root_markup = adapter._app.bot.send_message.await_args.kwargs[
        "reply_markup"
    ]
    character_data = root_markup.inline_keyboard[0][0].callback_data
    adapter._app.bot.send_message.reset_mock()

    await adapter._on_callback_query(
        _callback_update(character_data),
        object(),
    )

    assert any(call[0] == "list_characters" for call in reader.calls)
    adapter._app.bot.edit_message_text.assert_awaited_once()
    assert isinstance(
        adapter._app.bot.edit_message_text.await_args.kwargs["reply_markup"],
        type(root_markup),
    )
    adapter._turn_flow.release(reservation.active)


async def test_reference_edit_failure_sends_new_message_and_invalidates_old_view() -> None:
    reader = _ReferenceReader()
    adapter = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        reference_menu_enabled=True,
        reference_reader=reader,
    )
    adapter._app = _adapter_app(edit_result=None)

    await adapter._send_reference_root("123")
    root_markup = adapter._app.bot.send_message.await_args.kwargs[
        "reply_markup"
    ]
    character_data = root_markup.inline_keyboard[0][0].callback_data
    stale_status_data = root_markup.inline_keyboard[0][1].callback_data
    adapter._app.bot.send_message.reset_mock()

    await adapter._on_callback_query(
        _callback_update(character_data),
        object(),
    )

    adapter._app.bot.edit_message_text.assert_awaited_once()
    adapter._app.bot.send_message.assert_awaited_once()
    assert not adapter._action_registry.resolve(
        stale_status_data,
        chat_id="123",
        current_session_id="tg_default",
    ).resolved


async def test_reference_click_invalidates_siblings_before_read_completes() -> None:
    reader = _ReferenceReader()
    adapter = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        reference_menu_enabled=True,
        reference_reader=reader,
    )
    adapter._app = _adapter_app()
    await adapter._send_reference_root("123")
    root_markup = adapter._app.bot.send_message.await_args.kwargs[
        "reply_markup"
    ]
    character_data = root_markup.inline_keyboard[0][0].callback_data
    sibling_status_data = root_markup.inline_keyboard[0][1].callback_data
    started = asyncio.Event()
    release = asyncio.Event()
    original_list = reader.list_characters

    async def blocked_list(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        started.set()
        await release.wait()
        return await original_list(*args, **kwargs)

    reader.list_characters = blocked_list
    task = asyncio.create_task(
        adapter._on_callback_query(
            _callback_update(character_data),
            object(),
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not adapter._action_registry.resolve(
            sibling_status_data,
            chat_id="123",
            current_session_id="tg_default",
        ).resolved
    finally:
        release.set()
        await task


async def test_deleted_detail_and_empty_list_have_distinct_states() -> None:
    reader = _ReferenceReader()
    reader.characters = []
    adapter = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        reference_menu_enabled=True,
        reference_reader=reader,
    )
    adapter._app = _adapter_app()
    flow = adapter._reference_flow
    assert flow is not None

    empty = await flow.render_action(
        _LOCATOR,
        "123",
        adapter._action_registry.create(
            kind=REFERENCE_ACTION_CHARACTER_LIST,
            chat_id="123",
            session_id="tg_default",
        ),
    )
    assert "还没有角色卡" in empty.html
    assert "暂时无法读取" not in empty.html

    reader.fail_character_detail = True
    detail_callback = adapter._action_registry.add(
        kind=REFERENCE_ACTION_CHARACTER_DETAIL,
        chat_id="123",
        session_id="tg_default",
        payload={
            "character_id": 1,
            "detail_id": 1,
            "detail_list_page": 1,
            "character_list_page": 1,
        },
    )
    await adapter._on_callback_query(
        _callback_update(detail_callback),
        object(),
    )
    assert (
        "内容已变化或不存在"
        in adapter._app.bot.edit_message_text.await_args.kwargs["text"]
    )


async def test_start_entry_only_shows_reference_button_when_enabled() -> None:
    reader = _ReferenceReader()
    adapter = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        reference_menu_enabled=True,
        reference_reader=reader,
    )
    adapter._app = _adapter_app()
    adapter.bind_agent_client(FakeAgent())
    adapter.send_text = AsyncMock()

    await adapter._send_entry_card("123")

    markup = adapter.send_text.await_args.kwargs["reply_markup"]
    assert "查看资料" in [
        button.text
        for row in markup.inline_keyboard
        for button in row
    ]


async def test_info_disabled_and_missing_reader_degrade_without_agent_reads() -> None:
    disabled = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
    )
    disabled.send_text = AsyncMock()

    await disabled._on_command(_command_update("/info"), object())

    disabled.send_text.assert_awaited_once_with("123", "资料菜单未启用。")

    missing_reader = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        reference_menu_enabled=True,
    )
    missing_reader.send_text = AsyncMock()

    await missing_reader._on_command(_command_update("/info"), object())

    missing_reader.send_text.assert_awaited_once_with(
        "123",
        "资料读取暂不可用，聊天功能不受影响。",
    )


async def test_info_unavailable_session_opens_recovery_picker() -> None:
    reader = _ReferenceReader()
    reader.get_scope = AsyncMock(
        side_effect=SessionReferenceUnavailableError("deleted")
    )
    agent = FakeAgent()
    agent.list_sessions = AsyncMock(return_value={"sessions": []})
    adapter = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        reference_menu_enabled=True,
        reference_reader=reader,
    )
    adapter._app = _adapter_app()
    adapter.bind_agent_client(agent)

    await adapter._on_command(_command_update("/info"), object())

    sent = adapter._app.bot.send_message.await_args.kwargs
    assert "当前会话已删除或暂不可用" in sent["text"]
    assert sent["reply_markup"].inline_keyboard[-1][0].text == "新建并进入"


async def test_reference_provider_failure_shows_retry_and_back_actions() -> None:
    reader = _ReferenceReader()
    adapter = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        reference_menu_enabled=True,
        reference_reader=reader,
    )
    adapter._app = _adapter_app()
    await adapter._send_reference_root("123")
    root_markup = adapter._app.bot.send_message.await_args.kwargs[
        "reply_markup"
    ]
    character_data = root_markup.inline_keyboard[0][0].callback_data
    reader.list_characters = AsyncMock(side_effect=RuntimeError("offline"))

    await adapter._on_callback_query(
        _callback_update(character_data),
        object(),
    )

    edited = adapter._app.bot.edit_message_text.await_args.kwargs
    assert "暂时无法读取" in edited["text"]
    assert [
        button.text
        for row in edited["reply_markup"].inline_keyboard
        for button in row
    ] == ["重试", "返回资料"]


async def test_successful_session_switch_invalidates_old_reference_callbacks() -> None:
    reader = _ReferenceReader()
    agent = FakeAgent()
    adapter = TelegramAdapter(
        token="fake:token",
        workspace_id="tg_workspace",
        story_id=1,
        session_id="tg_default",
        reference_menu_enabled=True,
        reference_reader=reader,
    )
    adapter._app = _adapter_app()
    adapter.bind_agent_client(agent)
    await adapter._send_reference_root("123")
    old_callback = adapter._app.bot.send_message.await_args.kwargs[
        "reply_markup"
    ].inline_keyboard[0][0].callback_data

    active = await adapter._switch_chat_session("123", "session_b")

    assert active == "session_b"
    resolution = adapter._action_registry.resolve(
        old_callback,
        chat_id="123",
        current_session_id="session_b",
    )
    assert resolution.status == CallbackResolutionStatus.INVALID
