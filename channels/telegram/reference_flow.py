"""Read-only Session reference navigation for Telegram."""

from __future__ import annotations

import html
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from channels.telegram.action_registry import (
    ActionValue,
    TelegramActionRegistry,
    TelegramCallbackAction,
)
from channels.telegram.render import (
    chunk_rendered_text,
    render_markdown_to_telegram_html,
)
from rpg_core.session.reference import (
    CharacterCard,
    EvidenceReference,
    PersistentMemoryDetail,
    ReferencePage,
    SessionReferenceLocator,
    SessionReferenceNotFoundError,
    SessionReferenceReader,
    StatusTableDetail,
    StatusTableSummary,
    StoryMemoryDetail,
    SummaryDetail,
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
_REFERENCE_BODY_BUDGET = 3400
_TELEGRAM_MAX_MESSAGE_LENGTH = 4096
_ROOT_FIELD_BUDGET = 512
_LIST_HEADING_BUDGET = 240
_LIST_LABEL_BUDGET = 160
_LIST_EXCERPT_BUDGET = 160
_LIST_GROUP_BUDGET = 120
_LIST_LINE_BUDGET = 300
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

    async def render_root(
        self,
        locator: SessionReferenceLocator,
        chat_id: str,
    ) -> TelegramReferenceView:
        scope = await self._reader.get_scope(locator)
        title = scope.title.strip() or locator.session_id
        display_title = _bounded_inline_text(
            title,
            rendered_budget=_ROOT_FIELD_BUDGET,
            empty=locator.session_id,
        )
        return self._build_view(
            locator,
            chat_id,
            "\n".join(
                [
                    "## 查看资料",
                    f"当前会话：{display_title}",
                    "以下均为只读内容，截至当前已提交内容。",
                    "请选择要查看的资料：",
                ]
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
            f"## 查看资料\n{text}",
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
        lines = _list_heading("角色卡", page)
        rows: list[list[_ViewButton]] = []
        if not page.items:
            lines.append("当前故事还没有角色卡。")
        else:
            for item in page.items:
                display_name = _bounded_inline_text(
                    item.name,
                    rendered_budget=_LIST_LABEL_BUDGET,
                    empty="未命名角色",
                )
                display_description = _bounded_inline_text(
                    item.description,
                    rendered_budget=_LIST_EXCERPT_BUDGET,
                    empty="暂无简介",
                )
                marker = "（玩家）" if item.is_player else ""
                line_body = _bounded_list_body(
                    f"{display_name}{marker}：{display_description}",
                    rendered_budget=_LIST_LINE_BUDGET,
                    empty="未命名角色：暂无简介",
                )
                lines.append(f"- {line_body}")
                rows.append(
                    [
                        _button(
                            f"{'★ ' if item.is_player else ''}{display_name}",
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
        return self._build_view(locator, chat_id, "\n".join(lines), rows)

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
        lines = [
            f"## {card.name}{'（玩家角色）' if card.is_player else ''}",
            card.description.strip() or "暂无角色描述。",
            "",
            f"角色详情：{card.details_count} 项",
            "关联状态表：可从下方查看",
        ]
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
            "\n".join(lines),
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
        lines = _list_heading(f"{card.name} · 角色详情", page)
        rows: list[list[_ViewButton]] = []
        if not page.items:
            lines.append("当前角色没有可查看的二级详情。")
        else:
            for detail in page.items:
                display_title = _bounded_inline_text(
                    detail.title,
                    rendered_budget=_LIST_LABEL_BUDGET,
                    empty="未命名详情",
                )
                line_body = _bounded_list_body(
                    display_title,
                    rendered_budget=_LIST_LINE_BUDGET,
                    empty="未命名详情",
                )
                lines.append(f"- {line_body}")
                rows.append(
                    [
                        _button(
                            display_title,
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
        return self._build_view(locator, chat_id, "\n".join(lines), rows)

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
            "\n".join(
                [
                    f"## {detail.title}",
                    detail.content.strip() or "该详情暂无正文。",
                ]
            ),
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
        title = "关联状态表" if character_id is not None else "状态表"
        lines = _list_heading(title, page)
        rows: list[list[_ViewButton]] = []
        if not page.items:
            lines.append(
                "当前角色没有关联状态表。"
                if character_id is not None
                else "当前会话还没有状态表。"
            )
        else:
            current_group = ""
            for item in page.items:
                group = _bounded_inline_text(
                    _status_group_label(item),
                    rendered_budget=_LIST_GROUP_BUDGET,
                    empty="状态",
                )
                if group != current_group:
                    lines.extend(["", f"### {group}"])
                    current_group = group
                display_label = _bounded_inline_text(
                    _status_label(item),
                    rendered_budget=_LIST_LABEL_BUDGET,
                    empty="未命名状态表",
                )
                line_body = _bounded_list_body(
                    display_label,
                    rendered_budget=_LIST_LINE_BUDGET,
                    empty="未命名状态表",
                )
                lines.append(f"- {line_body}")
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
                            display_label,
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
        return self._build_view(locator, chat_id, "\n".join(lines), rows)

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
        lines = [
            f"## {_status_label(detail)}",
            detail.description.strip() or "暂无状态表描述。",
            "",
        ]
        if detail.rows:
            lines.extend(f"- **{row.key}**：{row.value}" for row in detail.rows)
        else:
            lines.append("当前状态表没有字段。")
        return self._build_detail_view(
            locator,
            chat_id,
            action,
            "\n".join(lines),
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
        lines = _list_heading("剧情归纳", page)
        rows: list[list[_ViewButton]] = []
        if not page.items:
            lines.append("当前会话还没有剧情归纳。")
        else:
            for item in page.items:
                display_title = _bounded_inline_text(
                    item.title,
                    rendered_budget=_LIST_LABEL_BUDGET,
                    empty="未命名归纳",
                )
                display_excerpt = _bounded_inline_text(
                    item.excerpt,
                    rendered_budget=_LIST_EXCERPT_BUDGET,
                    empty="暂无简介",
                )
                turn_range = _turn_range(item.turn_start, item.turn_end)
                line_body = _bounded_list_body(
                    f"{display_title}"
                    f"{f' · {turn_range}' if turn_range else ''}"
                    f"：{display_excerpt}",
                    rendered_budget=_LIST_LINE_BUDGET,
                    empty="未命名归纳：暂无简介",
                )
                lines.append(f"- {line_body}")
                rows.append(
                    [
                        _button(
                            display_title,
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
        return self._build_view(locator, chat_id, "\n".join(lines), rows)

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
        metadata = _summary_metadata(detail)
        return self._build_detail_view(
            locator,
            chat_id,
            action,
            "\n".join(
                [
                    f"## {detail.title}",
                    *metadata,
                    "",
                    detail.text.strip() or "该归纳暂无正文。",
                ]
            ),
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
        lines = _list_heading("故事记忆", page)
        rows: list[list[_ViewButton]] = []
        if not page.items:
            lines.append("当前会话还没有故事记忆。")
        else:
            for index, item in enumerate(
                page.items,
                start=(page.page - 1) * page.page_size + 1,
            ):
                display_title = _bounded_inline_text(
                    item.title,
                    rendered_budget=_LIST_LABEL_BUDGET,
                    empty="未命名故事记忆",
                )
                display_excerpt = _bounded_inline_text(
                    item.excerpt,
                    rendered_budget=_LIST_EXCERPT_BUDGET,
                    empty="暂无简介",
                )
                line_body = _bounded_list_body(
                    f"{index}. {display_title}：{display_excerpt}",
                    rendered_budget=_LIST_LINE_BUDGET,
                    empty=f"{index}. 未命名故事记忆：暂无简介",
                )
                lines.append(f"- {line_body}")
                rows.append(
                    [
                        _button(
                            f"{index}. {display_title}",
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
        return self._build_view(locator, chat_id, "\n".join(lines), rows)

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
            range_text=_turn_range(detail.turn_start, detail.turn_end),
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
        lines = _list_heading("持久记忆", page)
        rows: list[list[_ViewButton]] = []
        if not page.items:
            lines.append("当前会话还没有可见的持久记忆。")
        else:
            for index, item in enumerate(
                page.items,
                start=(page.page - 1) * page.page_size + 1,
            ):
                display_title = _bounded_inline_text(
                    item.title,
                    rendered_budget=_LIST_LABEL_BUDGET,
                    empty="未命名持久记忆",
                )
                display_excerpt = _bounded_inline_text(
                    item.excerpt,
                    rendered_budget=_LIST_EXCERPT_BUDGET,
                    empty="暂无简介",
                )
                line_body = _bounded_list_body(
                    f"{index}. {display_title}：{display_excerpt}",
                    rendered_budget=_LIST_LINE_BUDGET,
                    empty=f"{index}. 未命名持久记忆：暂无简介",
                )
                lines.append(f"- {line_body}")
                rows.append(
                    [
                        _button(
                            f"{index}. {display_title}",
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
        return self._build_view(locator, chat_id, "\n".join(lines), rows)

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
        labels = [detail.memory_kind, detail.epistemic_status]
        if range_text:
            labels.append(range_text)
        lines = [
            f"## {detail.title}",
            " · ".join(label for label in labels if label),
            "",
            detail.text.strip() or "该记忆暂无正文。",
        ]
        evidence_text = _evidence_text(detail.evidence)
        if evidence_text:
            lines.extend(["", f"来源：{evidence_text}"])
        return self._build_detail_view(
            locator,
            chat_id,
            action,
            "\n".join(lines),
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
        markdown: str,
        rows: list[list[_ViewButton]],
    ) -> TelegramReferenceView:
        rendered = render_markdown_to_telegram_html(markdown)
        try:
            pages = chunk_rendered_text(
                rendered,
                max_len=_REFERENCE_BODY_BUDGET,
            )
        except ValueError:
            # An unbounded Markdown URL can become one indivisible <a> token.
            # Preserve the complete content as escaped plain text instead of
            # making that detail permanently unreadable.
            pages = _chunk_plain_text_html(
                markdown,
                max_len=_REFERENCE_BODY_BUDGET,
            )
        if not pages:
            pages = ["暂无内容。"]
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
        markdown: str,
        rows: list[list[_ViewButton]],
    ) -> TelegramReferenceView:
        rendered = render_markdown_to_telegram_html(markdown)
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


def _list_heading(
    title: str,
    page: ReferencePage[_PageItemT],
) -> list[str]:
    display_title = _bounded_inline_text(
        title,
        rendered_budget=_LIST_HEADING_BUDGET,
        empty="资料列表",
    )
    page_label = (
        f"第 {page.page}/{page.total_pages} 页"
        if page.total_pages
        else "暂无内容"
    )
    return [
        f"## {display_title}",
        f"{page_label} · 共 {page.total} 项 · 截至当前已提交内容",
        "",
    ]


def _bounded_inline_text(
    value: str,
    *,
    rendered_budget: int,
    empty: str,
) -> str:
    """Clamp one standalone field by its final Telegram HTML length."""

    return _bounded_rendered_text(
        value,
        rendered_budget=rendered_budget,
        empty=empty,
        render_value=render_markdown_to_telegram_html,
    )


def _bounded_list_body(
    value: str,
    *,
    rendered_budget: int,
    empty: str,
) -> str:
    """Clamp a complete list body after all dynamic fields are combined."""

    return _bounded_rendered_text(
        value,
        rendered_budget=rendered_budget,
        empty=empty,
        render_value=lambda candidate: render_markdown_to_telegram_html(
            f"- {candidate}"
        ),
    )


def _bounded_rendered_text(
    value: str,
    *,
    rendered_budget: int,
    empty: str,
    render_value: Callable[[str], str],
) -> str:
    clean = " ".join(str(value or "").split())
    if not clean:
        clean = " ".join(str(empty or "").split()) or "—"
    if (
        len(clean) <= rendered_budget
        and len(render_value(clean)) <= rendered_budget
    ):
        return clean

    max_prefix = min(len(clean) - 1, rendered_budget - 1)
    for end in range(max_prefix, -1, -1):
        prefix = clean[:end].rstrip()
        candidate = f"{prefix}…" if prefix else "…"
        if len(render_value(candidate)) <= rendered_budget:
            return candidate
    return "…"


def _chunk_plain_text_html(
    value: str,
    *,
    max_len: int,
) -> list[str]:
    """Escape and split text without creating indivisible HTML tokens."""

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for character in str(value or ""):
        escaped = html.escape(character, quote=False)
        if current and current_length + len(escaped) > max_len:
            chunks.append("".join(current))
            current = []
            current_length = 0
        current.append(escaped)
        current_length += len(escaped)
    if current:
        chunks.append("".join(current))
    return chunks


def _status_label(item: StatusTableSummary | StatusTableDetail) -> str:
    if item.kind == "scene":
        return f"场景 · {item.name}"
    if item.character_id is not None:
        character_label = item.character_name or "关联角色"
        return f"{character_label} · {item.name}"
    return item.name


def _status_group_label(
    item: StatusTableSummary | StatusTableDetail,
) -> str:
    if item.kind == "scene":
        return "场景"
    if item.character_id is not None:
        return f"角色状态 · {item.character_name or '已关联角色'}"
    return "未关联状态"


def _turn_range(turn_start: int | None, turn_end: int | None) -> str:
    if turn_start is None and turn_end is None:
        return ""
    if turn_start is None:
        return f"Turn {turn_end}"
    if turn_end is None or turn_end == turn_start:
        return f"Turn {turn_start}"
    return f"Turn {turn_start}–{turn_end}"


def _summary_metadata(detail: SummaryDetail) -> list[str]:
    parts: list[str] = []
    turn_range = _turn_range(detail.turn_start, detail.turn_end)
    if turn_range:
        parts.append(turn_range)
    if detail.time:
        parts.append(f"时间：{detail.time}")
    if detail.location:
        parts.append(f"地点：{detail.location}")
    if detail.characters:
        parts.append(f"角色：{'、'.join(detail.characters)}")
    return parts


def _evidence_text(evidence: Sequence[EvidenceReference]) -> str:
    return "；".join(
        f"Turn {item.turn_id} · Msg {item.message_id}"
        for item in evidence
    )


__all__ = [
    "REFERENCE_ACTION_KINDS",
    "REFERENCE_ACTION_ROOT",
    "TelegramReferenceFlow",
    "TelegramReferenceView",
]
