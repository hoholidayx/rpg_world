"""Read-only Session reference navigation for Telegram."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from channels.telegram.action_registry import (
    ActionValue,
    TelegramActionRegistry,
    TelegramCallbackAction,
)
from channels.telegram.reference_presenter import (
    ReferenceDocument,
    TelegramReferencePresenter,
    status_label,
    turn_range,
)
from channels.telegram.reference_renderer import TelegramReferenceRenderer
from rpg_core.session.reference import (
    PersistentMemoryDetail,
    ReferencePage,
    SessionReferenceLocator,
    SessionReferenceNotFoundError,
    SessionReferenceReader,
    StoryMemoryDetail,
)

REFERENCE_ACTION_ROOT = "reference_root"
REFERENCE_ACTION_CHARACTER_LIST = "reference_character_list"
REFERENCE_ACTION_CHARACTER_CARD = "reference_character_card"
REFERENCE_ACTION_CHARACTER_DETAIL_LIST = "reference_character_detail_list"
REFERENCE_ACTION_CHARACTER_DETAIL = "reference_character_detail"
REFERENCE_ACTION_STATUS_LIST = "reference_status_list"
REFERENCE_ACTION_STATUS_DETAIL = "reference_status_detail"
REFERENCE_ACTION_SUMMARY_LIST = "reference_summary_list"
REFERENCE_ACTION_SUMMARY_DETAIL = "reference_summary_detail"
REFERENCE_ACTION_STORY_MEMORY_LIST = "reference_story_memory_list"
REFERENCE_ACTION_STORY_MEMORY_DETAIL = "reference_story_memory_detail"
REFERENCE_ACTION_PERSISTENT_MEMORY_LIST = "reference_persistent_memory_list"
REFERENCE_ACTION_PERSISTENT_MEMORY_DETAIL = "reference_persistent_memory_detail"

REFERENCE_ACTION_KINDS = frozenset(
    {
        REFERENCE_ACTION_ROOT,
        REFERENCE_ACTION_CHARACTER_LIST,
        REFERENCE_ACTION_CHARACTER_CARD,
        REFERENCE_ACTION_CHARACTER_DETAIL_LIST,
        REFERENCE_ACTION_CHARACTER_DETAIL,
        REFERENCE_ACTION_STATUS_LIST,
        REFERENCE_ACTION_STATUS_DETAIL,
        REFERENCE_ACTION_SUMMARY_LIST,
        REFERENCE_ACTION_SUMMARY_DETAIL,
        REFERENCE_ACTION_STORY_MEMORY_LIST,
        REFERENCE_ACTION_STORY_MEMORY_DETAIL,
        REFERENCE_ACTION_PERSISTENT_MEMORY_LIST,
        REFERENCE_ACTION_PERSISTENT_MEMORY_DETAIL,
    }
)

_REFERENCE_PAGE_SIZE = 8
_TELEGRAM_MAX_MESSAGE_LENGTH = 4096
_PageItemT = TypeVar("_PageItemT")


@dataclass(frozen=True)
class TelegramReferenceView:
    """One rendered reference page and its server-owned callback group."""

    html: str
    reply_markup: InlineKeyboardMarkup
    view_group_id: str


@dataclass(frozen=True)
class _ViewButton:
    text: str
    kind: str
    payload: Mapping[str, ActionValue]


class TelegramReferenceFlow:
    """Render multi-stage menus against the channel-neutral reference reader."""

    def __init__(
        self,
        action_registry: TelegramActionRegistry,
        reader: SessionReferenceReader,
    ) -> None:
        self._action_registry = action_registry
        self._reader = reader
        self._presenter = TelegramReferencePresenter()
        self._renderer = TelegramReferenceRenderer()

    async def render_root(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
    ) -> TelegramReferenceView:
        scope = await self._reader.get_scope(locator)
        title = scope.title.strip() or locator.session_id
        return self._build_view(
            locator,
            chat_id,
            self._presenter.root(
                session_title=title,
                session_id=locator.session_id,
            ),
            [
                [
                    _button("角色卡", REFERENCE_ACTION_CHARACTER_LIST),
                    _button("状态表", REFERENCE_ACTION_STATUS_LIST),
                ],
                [_button("剧情归纳", REFERENCE_ACTION_SUMMARY_LIST)],
                [
                    _button("故事记忆", REFERENCE_ACTION_STORY_MEMORY_LIST),
                    _button(
                        "持久记忆",
                        REFERENCE_ACTION_PERSISTENT_MEMORY_LIST,
                    ),
                ],
            ],
        )

    async def render_action(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        kind = action.kind
        if kind == REFERENCE_ACTION_ROOT:
            return await self.render_root(locator, chat_id)
        if kind == REFERENCE_ACTION_CHARACTER_LIST:
            return await self._render_character_list(locator, chat_id, action)
        if kind == REFERENCE_ACTION_CHARACTER_CARD:
            return await self._render_character_card(locator, chat_id, action)
        if kind == REFERENCE_ACTION_CHARACTER_DETAIL_LIST:
            return await self._render_character_detail_list(
                locator,
                chat_id,
                action,
            )
        if kind == REFERENCE_ACTION_CHARACTER_DETAIL:
            return await self._render_character_detail(locator, chat_id, action)
        if kind == REFERENCE_ACTION_STATUS_LIST:
            return await self._render_status_list(locator, chat_id, action)
        if kind == REFERENCE_ACTION_STATUS_DETAIL:
            return await self._render_status_detail(locator, chat_id, action)
        if kind == REFERENCE_ACTION_SUMMARY_LIST:
            return await self._render_summary_list(locator, chat_id, action)
        if kind == REFERENCE_ACTION_SUMMARY_DETAIL:
            return await self._render_summary_detail(locator, chat_id, action)
        if kind == REFERENCE_ACTION_STORY_MEMORY_LIST:
            return await self._render_story_memory_list(locator, chat_id, action)
        if kind == REFERENCE_ACTION_STORY_MEMORY_DETAIL:
            return await self._render_story_memory_detail(
                locator,
                chat_id,
                action,
            )
        if kind == REFERENCE_ACTION_PERSISTENT_MEMORY_LIST:
            return await self._render_persistent_memory_list(
                locator,
                chat_id,
                action,
            )
        if kind == REFERENCE_ACTION_PERSISTENT_MEMORY_DETAIL:
            return await self._render_persistent_memory_detail(
                locator,
                chat_id,
                action,
            )
        raise ValueError(f"unsupported Telegram reference action: {kind}")

    def render_failure(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
        *,
        text: str,
        content_changed: bool = False,
    ) -> TelegramReferenceView:
        retry_kind = action.kind
        retry_payload = dict(action.payload)
        retry_label = "重试"
        if content_changed:
            retry_kind, retry_payload = self._parent_action(action)
            retry_label = "刷新列表"
        rows = [
            [
                _button(
                    retry_label,
                    retry_kind,
                    retry_payload,
                ),
                _button("返回资料", REFERENCE_ACTION_ROOT),
            ]
        ]
        return self._build_view(
            locator,
            chat_id,
            self._presenter.failure(text),
            rows,
        )

    async def _render_character_list(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        requested_page = _payload_page(action.payload)
        page = await self._reader.list_characters(
            locator,
            page=requested_page,
            page_size=_REFERENCE_PAGE_SIZE,
        )
        rows: list[list[_ViewButton]] = []
        for item in page.items:
            rows.append(
                [
                    _button(
                        f"{'★ ' if item.is_player else ''}"
                        f"{_display_value(item.name, '未命名角色')}",
                        REFERENCE_ACTION_CHARACTER_CARD,
                        {
                            "character_id": item.id,
                            "list_page": page.page,
                            "character_version": item.version,
                        },
                    )
                ]
            )
        rows.extend(
            self._list_navigation(
                page,
                list_kind=REFERENCE_ACTION_CHARACTER_LIST,
                back_kind=REFERENCE_ACTION_ROOT,
            )
        )
        return self._build_view(
            locator,
            chat_id,
            self._presenter.character_list(page),
            rows,
        )

    async def _render_character_card(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        character_id = _payload_positive_int(action.payload, "character_id")
        card = await self._reader.get_character(locator, character_id)
        _require_expected_int(
            action.payload,
            "character_version",
            card.version,
        )
        list_page = _payload_page(action.payload, "list_page")
        rows: list[list[_ViewButton]] = []
        if card.details_count:
            rows.append(
                [
                    _button(
                        f"查看角色详情 ({card.details_count})",
                        REFERENCE_ACTION_CHARACTER_DETAIL_LIST,
                        {
                            "character_id": card.id,
                            "page": 1,
                            "character_list_page": list_page,
                            "character_version": card.version,
                        },
                    )
                ]
            )
        rows.append(
            [
                _button(
                    "查看关联状态",
                    REFERENCE_ACTION_STATUS_LIST,
                    {
                        "character_id": card.id,
                        "page": 1,
                        "character_list_page": list_page,
                        "character_version": card.version,
                    },
                )
            ]
        )
        rows.append(
            [
                _button(
                    "返回角色列表",
                    REFERENCE_ACTION_CHARACTER_LIST,
                    {"page": list_page},
                ),
                _button("返回资料", REFERENCE_ACTION_ROOT),
            ]
        )
        return self._build_detail_view(
            locator,
            chat_id,
            action,
            self._presenter.character_card(card),
            rows,
        )

    async def _render_character_detail_list(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        character_id = _payload_positive_int(action.payload, "character_id")
        card = await self._reader.get_character(locator, character_id)
        _require_expected_int(
            action.payload,
            "character_version",
            card.version,
        )
        page_number = _payload_page(action.payload)
        page = await self._reader.list_character_details(
            locator,
            character_id,
            page=page_number,
            page_size=_REFERENCE_PAGE_SIZE,
        )
        character_list_page = _payload_page(
            action.payload,
            "character_list_page",
        )
        rows: list[list[_ViewButton]] = []
        for detail in page.items:
            rows.append(
                [
                    _button(
                        _display_value(detail.title, "未命名详情"),
                        REFERENCE_ACTION_CHARACTER_DETAIL,
                        {
                            "character_id": character_id,
                            "detail_id": detail.id,
                            "detail_list_page": page.page,
                            "character_list_page": character_list_page,
                            "character_version": card.version,
                            "detail_version": detail.version,
                        },
                    )
                ]
            )
        rows.extend(
            self._list_navigation(
                page,
                list_kind=REFERENCE_ACTION_CHARACTER_DETAIL_LIST,
                list_payload={
                    "character_id": character_id,
                    "character_list_page": character_list_page,
                    "character_version": card.version,
                },
                back_kind=REFERENCE_ACTION_CHARACTER_CARD,
                back_payload={
                    "character_id": character_id,
                    "list_page": character_list_page,
                    "character_version": card.version,
                },
                back_label="返回角色卡",
            )
        )
        return self._build_view(
            locator,
            chat_id,
            self._presenter.character_detail_list(card, page),
            rows,
        )

    async def _render_character_detail(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        character_id = _payload_positive_int(action.payload, "character_id")
        detail_id = _payload_positive_int(action.payload, "detail_id")
        detail = await self._reader.get_character_detail(
            locator,
            character_id,
            detail_id,
        )
        _require_expected_int(
            action.payload,
            "detail_version",
            detail.version,
        )
        detail_list_page = _payload_page(action.payload, "detail_list_page")
        character_list_page = _payload_page(
            action.payload,
            "character_list_page",
        )
        return self._build_detail_view(
            locator,
            chat_id,
            action,
            self._presenter.character_detail(detail),
            [
                [
                    _button(
                        "返回详情列表",
                        REFERENCE_ACTION_CHARACTER_DETAIL_LIST,
                        {
                            "character_id": character_id,
                            "page": detail_list_page,
                            "character_list_page": character_list_page,
                            "character_version": _payload_optional_int(
                                action.payload,
                                "character_version",
                            ),
                        },
                    ),
                    _button(
                        "返回角色卡",
                        REFERENCE_ACTION_CHARACTER_CARD,
                        {
                            "character_id": character_id,
                            "list_page": character_list_page,
                            "character_version": _payload_optional_int(
                                action.payload,
                                "character_version",
                            ),
                        },
                    ),
                ]
            ],
        )

    async def _render_status_list(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        page_number = _payload_page(action.payload)
        character_id = _payload_optional_positive_int(
            action.payload,
            "character_id",
        )
        page = await self._reader.list_status_tables(
            locator,
            page=page_number,
            page_size=_REFERENCE_PAGE_SIZE,
            character_id=character_id,
        )
        rows: list[list[_ViewButton]] = []
        for item in page.items:
            payload: dict[str, ActionValue] = {
                "table_id": item.id,
                "list_page": page.page,
                "status_version": item.version,
            }
            if character_id is not None:
                payload["character_id"] = character_id
                payload["character_list_page"] = _payload_page(
                    action.payload,
                    "character_list_page",
                )
            rows.append(
                [
                    _button(
                        status_label(item),
                        REFERENCE_ACTION_STATUS_DETAIL,
                        payload,
                    )
                ]
            )
        list_payload: dict[str, ActionValue] = {}
        if character_id is not None:
            list_payload["character_id"] = character_id
            list_payload["character_list_page"] = _payload_page(
                action.payload,
                "character_list_page",
            )
        character_list_page = _payload_page(
            action.payload,
            "character_list_page",
        )
        if character_id is None:
            back_kind = REFERENCE_ACTION_ROOT
            back_payload: Mapping[str, ActionValue] = {}
            back_label = "返回资料"
        else:
            back_kind = REFERENCE_ACTION_CHARACTER_CARD
            back_payload = {
                "character_id": character_id,
                "list_page": character_list_page,
            }
            back_label = "返回角色卡"
        rows.extend(
            self._list_navigation(
                page,
                list_kind=REFERENCE_ACTION_STATUS_LIST,
                list_payload=list_payload,
                back_kind=back_kind,
                back_payload=back_payload,
                back_label=back_label,
            )
        )
        return self._build_view(
            locator,
            chat_id,
            self._presenter.status_list(
                page,
                character_id=character_id,
            ),
            rows,
        )

    async def _render_status_detail(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        table_id = _payload_positive_int(action.payload, "table_id")
        detail = await self._reader.get_status_table(locator, table_id)
        _require_expected_int(
            action.payload,
            "status_version",
            detail.version,
        )
        character_id = _payload_optional_positive_int(
            action.payload,
            "character_id",
        )
        list_payload: dict[str, ActionValue] = {
            "page": _payload_page(action.payload, "list_page"),
        }
        if character_id is not None:
            list_payload["character_id"] = character_id
            list_payload["character_list_page"] = _payload_page(
                action.payload,
                "character_list_page",
            )
        return self._build_detail_view(
            locator,
            chat_id,
            action,
            self._presenter.status_detail(detail),
            [
                [
                    _button(
                        "返回状态列表",
                        REFERENCE_ACTION_STATUS_LIST,
                        list_payload,
                    ),
                    _button("返回资料", REFERENCE_ACTION_ROOT),
                ]
            ],
        )

    async def _render_summary_list(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        page = await self._reader.list_summaries(
            locator,
            page=_payload_page(action.payload),
            page_size=_REFERENCE_PAGE_SIZE,
        )
        rows: list[list[_ViewButton]] = []
        for item in page.items:
            rows.append(
                [
                    _button(
                        _display_value(item.title, "未命名归纳"),
                        REFERENCE_ACTION_SUMMARY_DETAIL,
                        {
                            "summary_id": item.id,
                            "list_page": page.page,
                            **(
                                {"summary_updated_at": item.updated_at}
                                if item.updated_at
                                else {}
                            ),
                        },
                    )
                ]
            )
        rows.extend(
            self._list_navigation(
                page,
                list_kind=REFERENCE_ACTION_SUMMARY_LIST,
                back_kind=REFERENCE_ACTION_ROOT,
            )
        )
        return self._build_view(
            locator,
            chat_id,
            self._presenter.summary_list(page),
            rows,
        )

    async def _render_summary_detail(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        summary_id = _payload_str(action.payload, "summary_id")
        detail = await self._reader.get_summary(locator, summary_id)
        _require_expected_str(
            action.payload,
            "summary_updated_at",
            detail.updated_at,
        )
        return self._build_detail_view(
            locator,
            chat_id,
            action,
            self._presenter.summary_detail(detail),
            [
                [
                    _button(
                        "返回归纳列表",
                        REFERENCE_ACTION_SUMMARY_LIST,
                        {"page": _payload_page(action.payload, "list_page")},
                    ),
                    _button("返回资料", REFERENCE_ACTION_ROOT),
                ]
            ],
        )

    async def _render_story_memory_list(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        page = await self._reader.list_story_memories(
            locator,
            page=_payload_page(action.payload),
            page_size=_REFERENCE_PAGE_SIZE,
        )
        rows: list[list[_ViewButton]] = []
        for index, item in enumerate(
            page.items,
            start=(page.page - 1) * page.page_size + 1,
        ):
            rows.append(
                [
                    _button(
                        f"{index}. "
                        f"{_display_value(item.title, '未命名故事记忆')}",
                        REFERENCE_ACTION_STORY_MEMORY_DETAIL,
                        {
                            "memory_id": item.id,
                            "list_page": page.page,
                            "memory_version": item.version,
                        },
                    )
                ]
            )
        rows.extend(
            self._list_navigation(
                page,
                list_kind=REFERENCE_ACTION_STORY_MEMORY_LIST,
                back_kind=REFERENCE_ACTION_ROOT,
            )
        )
        return self._build_view(
            locator,
            chat_id,
            self._presenter.story_memory_list(page),
            rows,
        )

    async def _render_story_memory_detail(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        memory_id = _payload_positive_int(action.payload, "memory_id")
        detail = await self._reader.get_story_memory(locator, memory_id)
        _require_expected_int(
            action.payload,
            "memory_version",
            detail.version,
        )
        return self._build_memory_detail_view(
            locator,
            chat_id,
            action,
            detail,
            range_text=turn_range(detail.turn_start, detail.turn_end),
            back_kind=REFERENCE_ACTION_STORY_MEMORY_LIST,
            back_label="返回故事记忆",
        )

    async def _render_persistent_memory_list(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        page = await self._reader.list_persistent_memories(
            locator,
            page=_payload_page(action.payload),
            page_size=_REFERENCE_PAGE_SIZE,
        )
        rows: list[list[_ViewButton]] = []
        for index, item in enumerate(
            page.items,
            start=(page.page - 1) * page.page_size + 1,
        ):
            rows.append(
                [
                    _button(
                        f"{index}. "
                        f"{_display_value(item.title, '未命名持久记忆')}",
                        REFERENCE_ACTION_PERSISTENT_MEMORY_DETAIL,
                        {
                            "memory_id": item.id,
                            "list_page": page.page,
                            "memory_revision": item.revision_number,
                        },
                    )
                ]
            )
        rows.extend(
            self._list_navigation(
                page,
                list_kind=REFERENCE_ACTION_PERSISTENT_MEMORY_LIST,
                back_kind=REFERENCE_ACTION_ROOT,
            )
        )
        return self._build_view(
            locator,
            chat_id,
            self._presenter.persistent_memory_list(page),
            rows,
        )

    async def _render_persistent_memory_detail(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
    ) -> TelegramReferenceView:
        memory_id = _payload_str(action.payload, "memory_id")
        detail = await self._reader.get_persistent_memory(locator, memory_id)
        _require_expected_int(
            action.payload,
            "memory_revision",
            detail.revision_number,
        )
        return self._build_memory_detail_view(
            locator,
            chat_id,
            action,
            detail,
            range_text="",
            back_kind=REFERENCE_ACTION_PERSISTENT_MEMORY_LIST,
            back_label="返回持久记忆",
        )

    def _build_memory_detail_view(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
        detail: StoryMemoryDetail | PersistentMemoryDetail,
        *,
        range_text: str,
        back_kind: str,
        back_label: str,
    ) -> TelegramReferenceView:
        return self._build_detail_view(
            locator,
            chat_id,
            action,
            self._presenter.memory_detail(
                detail,
                range_text=range_text,
            ),
            [
                [
                    _button(
                        back_label,
                        back_kind,
                        {"page": _payload_page(action.payload, "list_page")},
                    ),
                    _button("返回资料", REFERENCE_ACTION_ROOT),
                ]
            ],
        )

    def _build_detail_view(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        action: TelegramCallbackAction,
        document: ReferenceDocument,
        rows: list[list[_ViewButton]],
    ) -> TelegramReferenceView:
        pages = self._renderer.render_detail_pages(document)
        requested_page = _payload_page(action.payload, "body_page")
        body_page = min(requested_page, len(pages))
        if len(pages) > 1:
            nav: list[_ViewButton] = []
            base_payload = dict(action.payload)
            if body_page > 1:
                nav.append(
                    _button(
                        "‹ 上一段",
                        action.kind,
                        {**base_payload, "body_page": body_page - 1},
                    )
                )
            if body_page < len(pages):
                nav.append(
                    _button(
                        "下一段 ›",
                        action.kind,
                        {**base_payload, "body_page": body_page + 1},
                    )
                )
            if nav:
                rows = [nav, *rows]
        page_marker = (
            f"\n\n<i>正文 {body_page}/{len(pages)}</i>"
            if len(pages) > 1
            else ""
        )
        return self._build_html_view(
            locator,
            chat_id,
            f"{pages[body_page - 1]}{page_marker}",
            rows,
        )

    def _build_view(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        document: ReferenceDocument,
        rows: list[list[_ViewButton]],
    ) -> TelegramReferenceView:
        rendered = self._renderer.render_menu(document)
        return self._build_html_view(locator, chat_id, rendered, rows)

    def _build_html_view(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
        rendered: str,
        rows: list[list[_ViewButton]],
    ) -> TelegramReferenceView:
        if len(rendered) > _TELEGRAM_MAX_MESSAGE_LENGTH:
            raise AssertionError("rendered Telegram reference view exceeds 4096 chars")
        view_group_id = self._action_registry.create_view_group()
        keyboard_rows: list[list[InlineKeyboardButton]] = []
        for row in rows:
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=_button_text(button.text),
                        callback_data=self._action_registry.add(
                            kind=button.kind,
                            chat_id=chat_id,
                            session_id=locator.session_id,
                            payload=button.payload,
                            view_group_id=view_group_id,
                        ),
                    )
                    for button in row
                ]
            )
        return TelegramReferenceView(
            html=rendered,
            reply_markup=InlineKeyboardMarkup(keyboard_rows),
            view_group_id=view_group_id,
        )

    @staticmethod
    def _list_navigation(
        page: ReferencePage[_PageItemT],
        *,
        list_kind: str,
        back_kind: str,
        list_payload: Mapping[str, ActionValue] | None = None,
        back_payload: Mapping[str, ActionValue] | None = None,
        back_label: str = "返回资料",
    ) -> list[list[_ViewButton]]:
        base_payload = dict(list_payload or {})
        pagination: list[_ViewButton] = []
        if page.page > 1:
            pagination.append(
                _button(
                    "‹ 上一页",
                    list_kind,
                    {**base_payload, "page": page.page - 1},
                )
            )
        if page.page < page.total_pages:
            pagination.append(
                _button(
                    "下一页 ›",
                    list_kind,
                    {**base_payload, "page": page.page + 1},
                )
            )
        rows = [pagination] if pagination else []
        rows.append([_button(back_label, back_kind, back_payload)])
        return rows

    @staticmethod
    def _parent_action(
        action: TelegramCallbackAction,
    ) -> tuple[str, dict[str, ActionValue]]:
        payload = action.payload
        if action.kind == REFERENCE_ACTION_CHARACTER_CARD:
            return (
                REFERENCE_ACTION_CHARACTER_LIST,
                {"page": _payload_page(payload, "list_page")},
            )
        if action.kind == REFERENCE_ACTION_CHARACTER_DETAIL:
            return (
                REFERENCE_ACTION_CHARACTER_DETAIL_LIST,
                {
                    "character_id": _payload_positive_int(
                        payload,
                        "character_id",
                    ),
                    "page": _payload_page(payload, "detail_list_page"),
                    "character_list_page": _payload_page(
                        payload,
                        "character_list_page",
                    ),
                },
            )
        if action.kind == REFERENCE_ACTION_STATUS_DETAIL:
            parent: dict[str, ActionValue] = {
                "page": _payload_page(payload, "list_page"),
            }
            character_id = _payload_optional_positive_int(
                payload,
                "character_id",
            )
            if character_id is not None:
                parent["character_id"] = character_id
                parent["character_list_page"] = _payload_page(
                    payload,
                    "character_list_page",
                )
            return REFERENCE_ACTION_STATUS_LIST, parent
        if action.kind == REFERENCE_ACTION_SUMMARY_DETAIL:
            return (
                REFERENCE_ACTION_SUMMARY_LIST,
                {"page": _payload_page(payload, "list_page")},
            )
        if action.kind == REFERENCE_ACTION_STORY_MEMORY_DETAIL:
            return (
                REFERENCE_ACTION_STORY_MEMORY_LIST,
                {"page": _payload_page(payload, "list_page")},
            )
        if action.kind == REFERENCE_ACTION_PERSISTENT_MEMORY_DETAIL:
            return (
                REFERENCE_ACTION_PERSISTENT_MEMORY_LIST,
                {"page": _payload_page(payload, "list_page")},
            )
        return REFERENCE_ACTION_ROOT, {}


def _button(
    text: str,
    kind: str,
    payload: Mapping[str, ActionValue] | None = None,
) -> _ViewButton:
    return _ViewButton(text=text, kind=kind, payload=dict(payload or {}))


def _button_text(value: str) -> str:
    text = " ".join(str(value or "").split())
    return (text or "查看")[:48]


def _payload_page(
    payload: Mapping[str, ActionValue],
    key: str = "page",
) -> int:
    raw = payload.get(key, 1)
    if isinstance(raw, bool):
        return 1
    try:
        page = int(raw or 1)
    except (TypeError, ValueError):
        return 1
    return max(1, page)


def _payload_positive_int(
    payload: Mapping[str, ActionValue],
    key: str,
) -> int:
    raw = payload.get(key)
    if isinstance(raw, bool):
        raise ValueError(f"invalid {key}")
    try:
        value = int(raw or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {key}") from exc
    if value <= 0:
        raise ValueError(f"invalid {key}")
    return value


def _payload_optional_positive_int(
    payload: Mapping[str, ActionValue],
    key: str,
) -> int | None:
    raw = payload.get(key)
    if raw is None or raw == "":
        return None
    return _payload_positive_int(payload, key)


def _payload_optional_int(
    payload: Mapping[str, ActionValue],
    key: str,
) -> int | None:
    raw = payload.get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise ValueError(f"invalid {key}")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {key}") from exc


def _payload_str(
    payload: Mapping[str, ActionValue],
    key: str,
) -> str:
    raw = payload.get(key)
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"invalid {key}")
    return value


def _require_expected_int(
    payload: Mapping[str, ActionValue],
    key: str,
    actual: int,
) -> None:
    if key not in payload:
        return
    expected = _payload_optional_int(payload, key)
    if expected is None:
        return
    if expected != int(actual):
        raise SessionReferenceNotFoundError(
            "reference item changed after the menu was rendered"
        )


def _require_expected_str(
    payload: Mapping[str, ActionValue],
    key: str,
    actual: str | None,
) -> None:
    if key not in payload:
        return
    expected = str(payload.get(key) or "")
    if not expected:
        return
    if expected != str(actual or ""):
        raise SessionReferenceNotFoundError(
            "reference item changed after the menu was rendered"
        )


def _display_value(value: str, empty: str) -> str:
    return " ".join(str(value or "").split()) or empty


__all__ = [
    "REFERENCE_ACTION_KINDS",
    "REFERENCE_ACTION_ROOT",
    "TelegramReferenceFlow",
    "TelegramReferenceView",
]
