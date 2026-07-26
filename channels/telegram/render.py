"""Telegram 消息渲染器。

负责把 agent 的 Markdown 风格输出转换成 Telegram 可接受的 HTML。
这个模块只做文本转换，不关心发送时机、节流或网络请求。
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass

_TELEGRAM_MAX_LEN = 4096
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_LIST_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>(?:[-*+])|(?:\d+\.))\s+(?P<body>.+)$")
_TASK_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+])\s+\[(?P<state>[ xX])\]\s+(?P<body>.+)$")
_HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<body>.+)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_ENTITY_RE = re.compile(
    r"&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);"
)
_TAG_NAME_RE = re.compile(
    r"^<\s*(?P<closing>/)?\s*(?P<name>[A-Za-z][A-Za-z0-9:_-]*)"
)
_VOID_HTML_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_RP_TAG_RE = re.compile(
    r"</?rp-narration>|</rp-character>|<rp-character\s+name=\"([^\"]*)\">"
)
_RP_TAG_PREFIXES = (
    "<rp-narration>",
    "</rp-narration>",
    "<rp-character",
    "</rp-character>",
)


def project_rp_text(text: str, *, streaming: bool = False) -> str:
    """Project fixed-layer RP tags into Telegram-friendly plain text.

    The projection is display-only. During streaming, a trailing partial known
    tag is withheld until the next accumulated chunk makes it complete.
    """
    source = str(text or "")
    if streaming:
        last_open = source.rfind("<")
        if last_open >= 0:
            suffix = source[last_open:]
            if ">" not in suffix and any(
                prefix.startswith(suffix) or suffix.startswith(prefix.rstrip(">"))
                for prefix in _RP_TAG_PREFIXES
            ):
                source = source[:last_open]

    def replace_tag(match: re.Match[str]) -> str:
        character_name = match.group(1)
        return f"{character_name}：" if character_name is not None else ""

    return _RP_TAG_RE.sub(replace_tag, source)


def _escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def _format_inline_markup(text: str) -> str:
    """把常见 Markdown 标记转成 Telegram HTML。"""
    escaped = _escape_html(text)
    escaped = _LINK_RE.sub(
        lambda match: (
            f'<a href="{html.escape(match.group(2), quote=True)}">'
            f"{match.group(1)}</a>"
        ),
        escaped,
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<u>\1</u>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def _table_to_html(lines: list[str]) -> str:
    """把 Markdown 表格转成 Telegram 友好的 HTML 列表。"""
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return _format_inline_markup("\n".join(lines))

    data_rows = rows[1:]
    rendered_rows: list[str] = []
    for row in data_rows:
        if not row:
            continue
        first = _format_inline_markup(row[0])
        if len(row) == 2:
            second = _format_inline_markup(row[1])
            rendered_rows.append(f"• {first}: {second}")
            continue
        if len(row) >= 3:
            second = _format_inline_markup(row[1])
            third = _format_inline_markup(" — ".join(row[2:]))
            rendered_rows.append(f"• {first}: {second} — {third}")
            continue
        rendered_rows.append(f"• {first}")
    return "\n".join(rendered_rows)


def _list_to_html(lines: list[str]) -> str:
    """把 Markdown 列表转成 Telegram 友好的 HTML 文本。

    规则：
    - 无序列表统一使用 `•`
    - 有序列表保留数字序号
    - 缩进层级使用不间断空格字符，尽量保留嵌套结构
    """
    rendered: list[str] = []
    for line in lines:
        task_match = _TASK_ITEM_RE.match(line)
        if task_match:
            indent = task_match.group("indent").replace("\t", "  ")
            level = len(indent) // 2
            state = task_match.group("state").lower()
            body = _format_inline_markup(task_match.group("body"))
            prefix = "\u00a0" * (level * 2)
            checkbox = "☑" if state == "x" else "☐"
            rendered.append(f"{prefix}{checkbox} {body}")
            continue

        match = _LIST_ITEM_RE.match(line)
        if not match:
            rendered.append(_format_inline_markup(line))
            continue

        indent = match.group("indent").replace("\t", "  ")
        level = len(indent) // 2
        marker = match.group("marker")
        body = _format_inline_markup(match.group("body"))
        prefix = "\u00a0" * (level * 2)
        bullet = marker if marker.endswith(".") else "•"
        rendered.append(f"{prefix}{bullet} {body}")
    return "\n".join(rendered)


def render_markdown_to_telegram_html(text: str) -> str:
    """把模型输出的 Markdown 转成 Telegram 兼容 HTML。"""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            out.append("<pre>" + _escape_html("\n".join(code_lines)) + "</pre>")
            i += 1
            continue

        if "|" in line and i + 1 < len(lines) and _TABLE_SEPARATOR_RE.match(lines[i + 1]):
            table_lines = [line]
            i += 2
            while i < len(lines) and "|" in lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            out.append(_table_to_html(table_lines))
            continue

        if _LIST_ITEM_RE.match(line) or _TASK_ITEM_RE.match(line):
            list_lines = [line]
            i += 1
            while i < len(lines) and (_LIST_ITEM_RE.match(lines[i]) or _TASK_ITEM_RE.match(lines[i])):
                list_lines.append(lines[i])
                i += 1
            out.append(_list_to_html(list_lines))
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            body = _format_inline_markup(heading.group("body"))
            out.append(f"<b>{body}</b>")
            i += 1
            continue

        if stripped == "---":
            out.append("—" * 24)
            i += 1
            continue

        if stripped:
            out.append(_format_inline_markup(line))
        else:
            out.append("")
        i += 1

    rendered = "\n".join(out)
    if not _is_balanced_rendered_html(rendered):
        return _escape_html(text)
    return rendered


@dataclass(frozen=True)
class _HtmlToken:
    raw: str
    kind: str = "text"
    name: str = ""


@dataclass(frozen=True)
class _OpenHtmlTag:
    name: str
    opening: str
    closing: str


def _find_tag_end(text: str, start: int) -> int | None:
    """Return the inclusive end of an HTML tag, respecting quoted attributes."""
    quote: str | None = None
    index = start + 1
    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == ">":
            return index
        index += 1
    return None


def _classify_tag(raw: str) -> _HtmlToken | None:
    match = _TAG_NAME_RE.match(raw)
    if match is None:
        return None
    name = match.group("name").lower()
    if match.group("closing"):
        return _HtmlToken(raw=raw, kind="close", name=name)
    if raw.rstrip().endswith("/>") or name in _VOID_HTML_TAGS:
        return _HtmlToken(raw=raw, kind="self", name=name)
    return _HtmlToken(raw=raw, kind="open", name=name)


def _is_variation_selector(char: str) -> bool:
    codepoint = ord(char)
    return 0xFE00 <= codepoint <= 0xFE0F or 0xE0100 <= codepoint <= 0xE01EF


def _is_emoji_modifier(char: str) -> bool:
    return 0x1F3FB <= ord(char) <= 0x1F3FF


def _is_emoji_tag_character(char: str) -> bool:
    return 0xE0020 <= ord(char) <= 0xE007F


def _is_regional_indicator(char: str) -> bool:
    return 0x1F1E6 <= ord(char) <= 0x1F1FF


def _iter_graphemes(text: str) -> Iterator[str]:
    """Yield practical Unicode grapheme clusters without splitting emoji sequences."""
    cluster = ""
    for char in text:
        if not cluster:
            cluster = char
            continue

        category = unicodedata.category(char)
        append_to_cluster = (
            (cluster == "\r" and char == "\n")
            or cluster.endswith("\u200d")
            or char == "\u200d"
            or category in {"Mn", "Mc", "Me"}
            or _is_variation_selector(char)
            or _is_emoji_modifier(char)
            or _is_emoji_tag_character(char)
            or (
                _is_regional_indicator(char)
                and len(cluster) == 1
                and _is_regional_indicator(cluster)
            )
        )
        if append_to_cluster:
            cluster += char
            continue

        yield cluster
        cluster = char

    if cluster:
        yield cluster


def _tokenize_rendered_html(text: str) -> list[_HtmlToken]:
    """Tokenize tags, entities and graphemes so none can be split across chunks."""
    tokens: list[_HtmlToken] = []
    index = 0
    plain_start = 0

    def append_plain(value: str) -> None:
        tokens.extend(_HtmlToken(raw=cluster) for cluster in _iter_graphemes(value))

    while index < len(text):
        char = text[index]
        if char == "<":
            tag_end = _find_tag_end(text, index)
            if tag_end is not None:
                tag = _classify_tag(text[index : tag_end + 1])
                if tag is not None:
                    append_plain(text[plain_start:index])
                    tokens.append(tag)
                    index = tag_end + 1
                    plain_start = index
                    continue
        elif char == "&":
            entity = _ENTITY_RE.match(text, index)
            if entity is not None:
                append_plain(text[plain_start:index])
                tokens.append(_HtmlToken(raw=entity.group(0), kind="entity"))
                index = entity.end()
                plain_start = index
                continue
        index += 1

    append_plain(text[plain_start:])
    return tokens


def _split_token_lines(tokens: list[_HtmlToken]) -> list[list[_HtmlToken]]:
    """Group tokens by rendered lines to preserve natural split points."""
    lines: list[list[_HtmlToken]] = []
    current: list[_HtmlToken] = []
    for token in tokens:
        current.append(token)
        if token.kind == "text" and token.raw.endswith(("\n", "\r")):
            lines.append(current)
            current = []
    if current:
        lines.append(current)
    return lines


def _stack_after(
    stack: list[_OpenHtmlTag],
    tokens: list[_HtmlToken],
) -> list[_OpenHtmlTag]:
    projected = list(stack)
    for token in tokens:
        if token.kind == "open":
            projected.append(
                _OpenHtmlTag(
                    name=token.name,
                    opening=token.raw,
                    closing=f"</{token.name}>",
                )
            )
        elif token.kind == "close":
            if not projected or projected[-1].name != token.name:
                expected = projected[-1].name if projected else "<none>"
                raise ValueError(
                    "unbalanced Telegram HTML: "
                    f"closing </{token.name}> does not match {expected}"
                )
            projected.pop()
    return projected


def _is_balanced_rendered_html(text: str) -> bool:
    """Return whether generated Telegram HTML is strictly well nested."""
    try:
        stack = _stack_after([], _tokenize_rendered_html(text))
    except ValueError:
        return False
    return not stack


def _closing_text(stack: list[_OpenHtmlTag]) -> str:
    return "".join(tag.closing for tag in reversed(stack))


def _opening_text(stack: list[_OpenHtmlTag]) -> str:
    return "".join(tag.opening for tag in stack)


def chunk_rendered_text(text: str, max_len: int = _TELEGRAM_MAX_LEN) -> list[str]:
    """Split rendered Telegram HTML into independently valid messages.

    Tags that span a boundary are closed at the end of the current chunk and
    reopened at the start of the next one. HTML entities, Unicode grapheme
    clusters and tag declarations are atomic and are never sliced.

    Raises
    ------
    ValueError
        If ``max_len`` is not positive, the input contains mismatched closing
        tags, or one atomic formatted unit cannot fit inside a chunk.
    """
    if not text:
        return []
    if max_len <= 0:
        raise ValueError("max_len must be positive")

    token_lines = _split_token_lines(_tokenize_rendered_html(text))
    chunks: list[str] = []
    stack: list[_OpenHtmlTag] = []
    current_parts: list[str] = []
    current_len = 0
    has_source_tokens = False
    has_visible_payload = False

    def reset_with_reopened_tags() -> None:
        nonlocal current_parts, current_len, has_source_tokens, has_visible_payload
        reopened = _opening_text(stack)
        current_parts = [reopened] if reopened else []
        current_len = len(reopened)
        has_source_tokens = False
        has_visible_payload = False

    def flush_current() -> None:
        nonlocal current_parts, current_len, has_source_tokens, has_visible_payload
        if not has_source_tokens:
            return
        chunk = "".join(current_parts) + _closing_text(stack)
        if len(chunk) > max_len:
            raise AssertionError("Telegram HTML chunk exceeded max_len")
        if chunk:
            chunks.append(chunk)
        reset_with_reopened_tags()

    def append_tokens(tokens: list[_HtmlToken], projected: list[_OpenHtmlTag]) -> None:
        nonlocal stack, current_len, has_source_tokens, has_visible_payload
        current_parts.extend(token.raw for token in tokens)
        current_len += sum(len(token.raw) for token in tokens)
        has_source_tokens = True
        if any(token.kind in {"text", "entity", "self"} for token in tokens):
            has_visible_payload = True
        stack = projected

    def fits(tokens: list[_HtmlToken], projected: list[_OpenHtmlTag]) -> bool:
        return (
            current_len
            + sum(len(token.raw) for token in tokens)
            + len(_closing_text(projected))
            <= max_len
        )

    def can_flush_before_next_token() -> bool:
        return has_visible_payload or (has_source_tokens and not stack)

    reset_with_reopened_tags()
    for line_tokens in token_lines:
        projected_line_stack = _stack_after(stack, line_tokens)
        if not fits(line_tokens, projected_line_stack) and can_flush_before_next_token():
            flush_current()
            projected_line_stack = _stack_after(stack, line_tokens)

        if fits(line_tokens, projected_line_stack):
            append_tokens(line_tokens, projected_line_stack)
            continue

        for token in line_tokens:
            projected_token_stack = _stack_after(stack, [token])
            if not fits([token], projected_token_stack):
                if can_flush_before_next_token():
                    flush_current()
                    projected_token_stack = _stack_after(stack, [token])
                if not fits([token], projected_token_stack):
                    raise ValueError(
                        "max_len is too small for one Telegram HTML token "
                        "and its active formatting"
                    )
            append_tokens([token], projected_token_stack)

    flush_current()
    return chunks
