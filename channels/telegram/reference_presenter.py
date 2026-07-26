"""Pure presentation model for Telegram Session references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias, TypeVar

from rpg_core.session.reference import (
    CharacterCard,
    CharacterDetail,
    CharacterDetailSummary,
    CharacterSummary,
    EvidenceReference,
    PersistentMemoryDetail,
    PersistentMemorySummary,
    ReferencePage,
    StatusTableDetail,
    StatusTableSummary,
    StoryMemoryDetail,
    StoryMemorySummary,
    SummaryDetail,
    SummarySummary,
)

_PageItemT = TypeVar("_PageItemT")
_MemorySummaryT = TypeVar(
    "_MemorySummaryT",
    StoryMemorySummary,
    PersistentMemorySummary,
)


@dataclass(frozen=True)
class PlainHeading:
    text: str
    empty: str = "资料"


@dataclass(frozen=True)
class PlainParagraph:
    text: str
    empty: str = "—"


@dataclass(frozen=True)
class PlainGroup:
    text: str
    empty: str = "状态"


@dataclass(frozen=True)
class PlainBullet:
    """One fully composed list row; the renderer bounds it as one unit."""

    text: str
    empty: str = "—"


@dataclass(frozen=True)
class PlainKeyValue:
    key: str
    value: str


@dataclass(frozen=True)
class EvidenceBlock:
    items: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class MarkdownBody:
    text: str
    empty: str


ReferenceBlock: TypeAlias = (
    PlainHeading
    | PlainParagraph
    | PlainGroup
    | PlainBullet
    | PlainKeyValue
    | EvidenceBlock
    | MarkdownBody
)


@dataclass(frozen=True)
class ReferenceDocument:
    blocks: tuple[ReferenceBlock, ...]

    def __post_init__(self) -> None:
        body_count = sum(
            isinstance(block, MarkdownBody) for block in self.blocks
        )
        if body_count > 1:
            raise ValueError(
                "ReferenceDocument supports at most one Markdown body"
            )


class TelegramReferencePresenter:
    """Convert player-facing Reference DTOs into controlled documents."""

    def root(self, *, session_title: str, session_id: str) -> ReferenceDocument:
        return ReferenceDocument(
            (
                PlainHeading("查看资料"),
                PlainParagraph(
                    f"当前会话：{session_title}",
                    empty=f"当前会话：{session_id}",
                ),
                PlainParagraph(
                    "以下均为只读内容，截至当前已提交内容。"
                ),
                PlainParagraph("请选择要查看的资料："),
            )
        )

    def failure(self, text: str) -> ReferenceDocument:
        return ReferenceDocument(
            (
                PlainHeading("查看资料"),
                PlainParagraph(text, empty="暂时无法读取。"),
            )
        )

    def character_list(
        self,
        page: ReferencePage[CharacterSummary],
    ) -> ReferenceDocument:
        blocks = self._list_header("角色卡", page)
        if not page.items:
            blocks.append(PlainParagraph("当前故事还没有角色卡。"))
        else:
            blocks.extend(
                PlainBullet(
                    f"{_or(item.name, '未命名角色')}"
                    f"{'（玩家）' if item.is_player else ''}："
                    f"{_or(item.description, '暂无简介')}",
                    empty="未命名角色：暂无简介",
                )
                for item in page.items
            )
        return ReferenceDocument(tuple(blocks))

    def character_card(self, card: CharacterCard) -> ReferenceDocument:
        return ReferenceDocument(
            (
                PlainHeading(
                    f"{_or(card.name, '未命名角色')}"
                    f"{'（玩家角色）' if card.is_player else ''}"
                ),
                MarkdownBody(
                    card.description,
                    empty="暂无角色描述。",
                ),
                PlainParagraph(f"角色详情：{card.details_count} 项"),
                PlainParagraph("关联状态表：可从下方查看"),
            )
        )

    def character_detail_list(
        self,
        card: CharacterCard,
        page: ReferencePage[CharacterDetailSummary],
    ) -> ReferenceDocument:
        blocks = self._list_header(
            f"{_or(card.name, '未命名角色')} · 角色详情",
            page,
        )
        if not page.items:
            blocks.append(
                PlainParagraph("当前角色没有可查看的二级详情。")
            )
        else:
            blocks.extend(
                PlainBullet(
                    detail.title,
                    empty="未命名详情",
                )
                for detail in page.items
            )
        return ReferenceDocument(tuple(blocks))

    def character_detail(
        self,
        detail: CharacterDetail,
    ) -> ReferenceDocument:
        return ReferenceDocument(
            (
                PlainHeading(detail.title, empty="未命名详情"),
                MarkdownBody(detail.content, empty="该详情暂无正文。"),
            )
        )

    def status_list(
        self,
        page: ReferencePage[StatusTableSummary],
        *,
        character_id: int | None,
    ) -> ReferenceDocument:
        title = "关联状态表" if character_id is not None else "状态表"
        blocks = self._list_header(title, page)
        if not page.items:
            blocks.append(
                PlainParagraph(
                    "当前角色没有关联状态表。"
                    if character_id is not None
                    else "当前会话还没有状态表。"
                )
            )
            return ReferenceDocument(tuple(blocks))

        current_group: str | None = None
        for item in page.items:
            group = _status_group_label(item)
            if group != current_group:
                blocks.append(PlainGroup(group))
                current_group = group
            blocks.append(
                PlainBullet(
                    _status_label(item),
                    empty="未命名状态表",
                )
            )
        return ReferenceDocument(tuple(blocks))

    def status_detail(
        self,
        detail: StatusTableDetail,
    ) -> ReferenceDocument:
        blocks: list[ReferenceBlock] = [
            PlainHeading(
                _status_label(detail),
                empty="未命名状态表",
            ),
            MarkdownBody(
                detail.description,
                empty="暂无状态表描述。",
            ),
        ]
        if detail.rows:
            blocks.extend(
                PlainKeyValue(row.key, row.value) for row in detail.rows
            )
        else:
            blocks.append(PlainParagraph("当前状态表没有字段。"))
        return ReferenceDocument(tuple(blocks))

    def summary_list(
        self,
        page: ReferencePage[SummarySummary],
    ) -> ReferenceDocument:
        blocks = self._list_header("剧情归纳", page)
        if not page.items:
            blocks.append(PlainParagraph("当前会话还没有剧情归纳。"))
        else:
            for item in page.items:
                turn_range = _turn_range(item.turn_start, item.turn_end)
                blocks.append(
                    PlainBullet(
                        f"{_or(item.title, '未命名归纳')}"
                        f"{f' · {turn_range}' if turn_range else ''}："
                        f"{_or(item.excerpt, '暂无简介')}",
                        empty="未命名归纳：暂无简介",
                    )
                )
        return ReferenceDocument(tuple(blocks))

    def summary_detail(self, detail: SummaryDetail) -> ReferenceDocument:
        blocks: list[ReferenceBlock] = [
            PlainHeading(detail.title, empty="未命名归纳"),
        ]
        metadata = _summary_metadata(detail)
        if metadata:
            blocks.append(PlainParagraph(" · ".join(metadata)))
        blocks.append(
            MarkdownBody(detail.text, empty="该归纳暂无正文。")
        )
        return ReferenceDocument(tuple(blocks))

    def story_memory_list(
        self,
        page: ReferencePage[StoryMemorySummary],
    ) -> ReferenceDocument:
        return self._memory_list(
            title="故事记忆",
            empty="当前会话还没有故事记忆。",
            page=page,
        )

    def persistent_memory_list(
        self,
        page: ReferencePage[PersistentMemorySummary],
    ) -> ReferenceDocument:
        return self._memory_list(
            title="持久记忆",
            empty="当前会话还没有可见的持久记忆。",
            page=page,
        )

    def memory_detail(
        self,
        detail: StoryMemoryDetail | PersistentMemoryDetail,
        *,
        range_text: str,
    ) -> ReferenceDocument:
        labels = [detail.memory_kind, detail.epistemic_status]
        if range_text:
            labels.append(range_text)
        blocks: list[ReferenceBlock] = [
            PlainHeading(detail.title, empty="未命名记忆"),
            PlainParagraph(
                " · ".join(label for label in labels if label),
                empty="记忆",
            ),
            MarkdownBody(detail.text, empty="该记忆暂无正文。"),
        ]
        if detail.evidence:
            blocks.append(EvidenceBlock(detail.evidence))
        return ReferenceDocument(tuple(blocks))

    @staticmethod
    def _list_header(
        title: str,
        page: ReferencePage[_PageItemT],
    ) -> list[ReferenceBlock]:
        page_label = (
            f"第 {page.page}/{page.total_pages} 页"
            if page.total_pages
            else "暂无内容"
        )
        return [
            PlainHeading(title, empty="资料列表"),
            PlainParagraph(
                f"{page_label} · 共 {page.total} 项 · 截至当前已提交内容"
            ),
        ]

    def _memory_list(
        self,
        *,
        title: str,
        empty: str,
        page: ReferencePage[_MemorySummaryT],
    ) -> ReferenceDocument:
        blocks = self._list_header(title, page)
        if not page.items:
            blocks.append(PlainParagraph(empty))
        else:
            start = (page.page - 1) * page.page_size + 1
            for index, item in enumerate(page.items, start=start):
                blocks.append(
                    PlainBullet(
                        f"{index}. {_or(item.title, '未命名记忆')}："
                        f"{_or(item.excerpt, '暂无简介')}",
                        empty=f"{index}. 未命名记忆：暂无简介",
                    )
                )
        return ReferenceDocument(tuple(blocks))


def _or(value: str, empty: str) -> str:
    return str(value or "").strip() or empty


def status_label(
    item: StatusTableSummary | StatusTableDetail,
) -> str:
    """Plain button label matching the status document presentation."""

    return _status_label(item)


def turn_range(turn_start: int | None, turn_end: int | None) -> str:
    return _turn_range(turn_start, turn_end)


def _status_label(
    item: StatusTableSummary | StatusTableDetail,
) -> str:
    name = _or(item.name, "未命名状态表")
    if item.kind == "scene":
        return f"场景 · {name}"
    if item.character_id is not None:
        character_label = item.character_name or "关联角色"
        return f"{character_label} · {name}"
    return name


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
    range_text = _turn_range(detail.turn_start, detail.turn_end)
    if range_text:
        parts.append(range_text)
    if detail.time:
        parts.append(f"时间：{detail.time}")
    if detail.location:
        parts.append(f"地点：{detail.location}")
    if detail.characters:
        parts.append(f"角色：{'、'.join(detail.characters)}")
    return parts


__all__ = [
    "EvidenceBlock",
    "MarkdownBody",
    "PlainBullet",
    "PlainGroup",
    "PlainHeading",
    "PlainKeyValue",
    "PlainParagraph",
    "ReferenceDocument",
    "TelegramReferencePresenter",
    "status_label",
    "turn_range",
]
