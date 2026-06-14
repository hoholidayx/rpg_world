"""Telegram 消息渲染器。

负责把 agent 的 Markdown 风格输出转换成 Telegram 可接受的 HTML。
这个模块只做文本转换，不关心发送时机、节流或网络请求。
"""

from __future__ import annotations

import html
import re

_TELEGRAM_MAX_LEN = 4096
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_LIST_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>(?:[-*+])|(?:\d+\.))\s+(?P<body>.+)$")
_TASK_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+])\s+\[(?P<state>[ xX])\]\s+(?P<body>.+)$")
_HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<body>.+)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


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
    - 缩进层级使用 `&nbsp;` 表示，尽量保留嵌套结构
    """
    rendered: list[str] = []
    for line in lines:
        task_match = _TASK_ITEM_RE.match(line)
        if task_match:
            indent = task_match.group("indent").replace("\t", "  ")
            level = len(indent) // 2
            state = task_match.group("state").lower()
            body = _format_inline_markup(task_match.group("body"))
            prefix = "&nbsp;" * (level * 2)
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
        prefix = "&nbsp;" * (level * 2)
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

    return "\n".join(out)


def chunk_rendered_text(text: str, max_len: int = _TELEGRAM_MAX_LEN) -> list[str]:
    """按长度切分已经渲染好的 Telegram HTML。"""
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        line_len = len(line)
        if current_lines and current_len + line_len > max_len:
            chunks.append("".join(current_lines))
            current_lines = [line]
            current_len = line_len
            continue
        if not current_lines and line_len > max_len:
            chunks.extend([line[i : i + max_len] for i in range(0, len(line), max_len)])
            current_len = 0
            current_lines = []
            continue
        current_lines.append(line)
        current_len += line_len

    if current_lines:
        chunks.append("".join(current_lines))
    return chunks
