"""Safe HTML rendering and pagination for Telegram Reference documents."""

from __future__ import annotations

import html
from dataclasses import dataclass

from channels.telegram.reference_presenter import (
    EvidenceBlock,
    MarkdownBody,
    PlainBullet,
    PlainGroup,
    PlainHeading,
    PlainKeyValue,
    PlainParagraph,
    ReferenceBlock,
    ReferenceDocument,
)
from channels.telegram.render import (
    chunk_rendered_text,
    render_markdown_to_telegram_html,
)

_TELEGRAM_MAX_MESSAGE_LENGTH = 4096
_REFERENCE_BODY_BUDGET = 3400
_HEADING_BUDGET = 240
_PARAGRAPH_BUDGET = 512
_GROUP_BUDGET = 120
_LIST_ROW_BUDGET = 300


@dataclass(frozen=True)
class _RenderedBlock:
    html: str
    is_markdown_body: bool = False
    starts_group: bool = False


class TelegramReferenceRenderer:
    """Render controlled structure as plain text and one body as Markdown."""

    def render_menu(self, document: ReferenceDocument) -> str:
        if any(isinstance(block, MarkdownBody) for block in document.blocks):
            raise ValueError("menu documents must not contain Markdown bodies")
        rendered = _join_blocks(
            tuple(
                _render_plain_block(block, menu=True)
                for block in document.blocks
            )
        )
        if len(rendered) > _TELEGRAM_MAX_MESSAGE_LENGTH:
            raise AssertionError(
                "rendered Telegram reference menu exceeds 4096 chars"
            )
        return rendered

    def render_detail_pages(
        self,
        document: ReferenceDocument,
    ) -> tuple[str, ...]:
        prefix_count = (
            1
            if (
                document.blocks
                and isinstance(document.blocks[0], PlainHeading)
            )
            else 0
        )
        prefix = _join_blocks(
            tuple(
                _render_plain_block(block, menu=False)
                for block in document.blocks[:prefix_count]
            )
        )
        separator = "\n\n" if prefix else ""
        content_budget = (
            _REFERENCE_BODY_BUDGET
            - len(prefix)
            - len(separator)
        )
        if content_budget <= 0:
            raise AssertionError(
                "Telegram Reference detail header exhausts body budget"
            )
        content_blocks = tuple(
            (
                _render_markdown_body(block, max_len=content_budget)
                if isinstance(block, MarkdownBody)
                else _render_plain_block(block, menu=False)
            )
            for block in document.blocks[prefix_count:]
        )
        content = _join_blocks(content_blocks)
        content_pages = tuple(
            chunk_rendered_text(
                content,
                max_len=content_budget,
            )
        )
        if content_pages:
            pages = tuple(
                f"{prefix}{separator}{page}"
                for page in content_pages
            )
        else:
            pages = (prefix,) if prefix else ()
        if not pages:
            pages = ("暂无内容。",)
        if any(
            len(page) > _TELEGRAM_MAX_MESSAGE_LENGTH for page in pages
        ):
            raise AssertionError(
                "rendered Telegram reference detail exceeds 4096 chars"
            )
        return pages


def _render_markdown_body(
    block: MarkdownBody,
    *,
    max_len: int,
) -> _RenderedBlock:
    source = str(block.text or "").strip() or block.empty
    rendered = render_markdown_to_telegram_html(source)
    try:
        chunk_rendered_text(rendered, max_len=max_len)
    except ValueError:
        rendered = html.escape(source, quote=False)
    return _RenderedBlock(rendered, is_markdown_body=True)


def _render_plain_block(
    block: ReferenceBlock,
    *,
    menu: bool,
) -> _RenderedBlock:
    if isinstance(block, PlainHeading):
        text = _bounded_plain_text(
            block.text,
            empty=block.empty,
            budget=_HEADING_BUDGET,
            prefix="<b>",
            suffix="</b>",
        )
        return _RenderedBlock(f"<b>{text}</b>")
    if isinstance(block, PlainParagraph):
        text = (
            _bounded_plain_text(
                block.text,
                empty=block.empty,
                budget=_PARAGRAPH_BUDGET,
            )
            if menu
            else _escaped_plain(block.text, empty=block.empty)
        )
        return _RenderedBlock(text)
    if isinstance(block, PlainGroup):
        text = _bounded_plain_text(
            block.text,
            empty=block.empty,
            budget=_GROUP_BUDGET,
            prefix="<b>",
            suffix="</b>",
        )
        return _RenderedBlock(f"<b>{text}</b>", starts_group=True)
    if isinstance(block, PlainBullet):
        text = _bounded_plain_text(
            block.text,
            empty=block.empty,
            budget=_LIST_ROW_BUDGET,
            prefix="• ",
        )
        return _RenderedBlock(f"• {text}")
    if isinstance(block, PlainKeyValue):
        key = _escaped_plain(block.key, empty="未命名字段")
        value = _escaped_plain(block.value, empty="—")
        return _RenderedBlock(f"<b>{key}</b>：{value}")
    if isinstance(block, EvidenceBlock):
        evidence = "；".join(
            f"Turn {item.turn_id} · Msg {item.message_id}"
            for item in block.items
        )
        return _RenderedBlock(
            f"来源：{_escaped_plain(evidence, empty='—')}"
        )
    if isinstance(block, MarkdownBody):
        raise TypeError("MarkdownBody must use the body renderer")
    raise TypeError(f"unsupported Reference block: {type(block)!r}")


def _join_blocks(blocks: tuple[_RenderedBlock, ...]) -> str:
    parts: list[str] = []
    previous: _RenderedBlock | None = None
    for block in blocks:
        if not block.html:
            continue
        if parts:
            separator = (
                "\n\n"
                if (
                    block.is_markdown_body
                    or block.starts_group
                    or (
                        previous is not None
                        and previous.is_markdown_body
                    )
                )
                else "\n"
            )
            parts.append(separator)
        parts.append(block.html)
        previous = block
    return "".join(parts)


def _escaped_plain(value: object, *, empty: str) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        normalized = " ".join(str(empty or "").split()) or "—"
    return html.escape(normalized, quote=False)


def _bounded_plain_text(
    value: object,
    *,
    empty: str,
    budget: int,
    prefix: str = "",
    suffix: str = "",
) -> str:
    """Normalize and clamp one complete plain block by final HTML length."""

    normalized = " ".join(str(value or "").split())
    if not normalized:
        normalized = " ".join(str(empty or "").split()) or "—"

    def fits(candidate: str) -> bool:
        return (
            len(prefix)
            + len(html.escape(candidate, quote=False))
            + len(suffix)
            <= budget
        )

    if fits(normalized):
        return html.escape(normalized, quote=False)

    low = 0
    high = len(normalized)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = f"{normalized[:middle].rstrip()}…"
        if fits(candidate):
            low = middle
        else:
            high = middle - 1
    candidate = f"{normalized[:low].rstrip()}…" if low else "…"
    if not fits(candidate):
        raise AssertionError("plain Reference block budget is too small")
    return html.escape(candidate, quote=False)


__all__ = ["TelegramReferenceRenderer"]
