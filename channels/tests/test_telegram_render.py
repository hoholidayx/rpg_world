from __future__ import annotations

import html
from html.parser import HTMLParser

import pytest

from channels.telegram.render import (
    chunk_rendered_text,
    render_markdown_to_telegram_html,
)


class _ValidatingHTMLParser(HTMLParser):
    _VOID_TAGS = {"br", "hr", "img", "input", "meta", "link"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.visible: list[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:  # noqa: ANN001
        if tag not in self._VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, _tag: str, _attrs) -> None:  # noqa: ANN001
        return

    def handle_endtag(self, tag: str) -> None:
        assert self.stack, f"unexpected closing tag </{tag}>"
        assert self.stack.pop() == tag

    def handle_data(self, data: str) -> None:
        self.visible.append(data)

    def handle_entityref(self, name: str) -> None:
        self.visible.append(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.visible.append(html.unescape(f"&#{name};"))


def _assert_valid_chunks(chunks: list[str], max_len: int) -> str:
    assert chunks
    visible: list[str] = []
    for chunk in chunks:
        assert 0 < len(chunk) <= max_len
        parser = _ValidatingHTMLParser()
        parser.feed(chunk)
        parser.close()
        assert parser.stack == []
        visible.extend(parser.visible)
    return "".join(visible)


def test_long_bold_text_closes_and_reopens_without_splitting_entities() -> None:
    payload = "勇者 & 巨龙 😀 " * 80
    rendered = f"<b>{html.escape(payload, quote=False)}</b>"
    max_len = 72

    chunks = chunk_rendered_text(rendered, max_len=max_len)

    assert len(chunks) > 2
    assert all(chunk.startswith("<b>") and chunk.endswith("</b>") for chunk in chunks)
    assert _assert_valid_chunks(chunks, max_len) == payload


def test_long_preformatted_block_splits_into_independent_pre_blocks() -> None:
    payload = "\n".join(
        f"line_{index} = value < {index} and value & ready"
        for index in range(30)
    )
    rendered = f"<pre>{html.escape(payload, quote=False)}</pre>"
    max_len = 96

    chunks = chunk_rendered_text(rendered, max_len=max_len)

    assert len(chunks) > 2
    assert all(chunk.startswith("<pre>") and chunk.endswith("</pre>") for chunk in chunks)
    assert _assert_valid_chunks(chunks, max_len) == payload


def test_long_link_reopens_the_complete_anchor_tag_in_each_chunk() -> None:
    payload = "远方地图与隐藏入口 " * 40
    opening = '<a href="https://example.com/map?mode=full&amp;chapter=7">'
    rendered = f"{opening}{payload}</a>"
    max_len = 104

    chunks = chunk_rendered_text(rendered, max_len=max_len)

    assert len(chunks) > 2
    assert all(chunk.startswith(opening) and chunk.endswith("</a>") for chunk in chunks)
    assert _assert_valid_chunks(chunks, max_len) == payload


def test_nested_tags_remain_well_nested_across_boundaries() -> None:
    nested_payload = "内层线索 & 证言 👁️ " * 35
    rendered = (
        "<b>外层开头 <u>"
        f"{html.escape(nested_payload, quote=False)}"
        "</u> 外层结尾</b>"
    )
    max_len = 80

    chunks = chunk_rendered_text(rendered, max_len=max_len)

    assert len(chunks) > 2
    assert any(chunk.startswith("<b><u>") for chunk in chunks[1:])
    assert _assert_valid_chunks(chunks, max_len) == (
        f"外层开头 {nested_payload} 外层结尾"
    )


def test_entity_is_atomic_at_a_tight_chunk_boundary() -> None:
    rendered = "A&amp;B " * 20
    max_len = 9

    chunks = chunk_rendered_text(rendered, max_len=max_len)

    assert all(
        chunk.count("&") == chunk.count("&amp;")
        for chunk in chunks
    )
    assert _assert_valid_chunks(chunks, max_len) == "A&B " * 20


def test_emoji_zwj_graphemes_are_not_split() -> None:
    family = "👨‍👩‍👧‍👦"
    rendered = f"<b>{family * 7}</b>"
    max_len = 21

    chunks = chunk_rendered_text(rendered, max_len=max_len)

    assert _assert_valid_chunks(chunks, max_len) == family * 7
    for chunk in chunks:
        parser = _ValidatingHTMLParser()
        parser.feed(chunk)
        parser.close()
        visible = "".join(parser.visible)
        assert visible
        assert visible == family * (len(visible) // len(family))


def test_impossibly_small_formatted_unit_fails_explicitly() -> None:
    with pytest.raises(ValueError, match="too small"):
        chunk_rendered_text("<b>😀</b>", max_len=7)


def test_non_positive_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        chunk_rendered_text("text", max_len=0)


def test_crossing_markdown_falls_back_to_safe_plain_text() -> None:
    source = "**bold __text** underline__"

    rendered = render_markdown_to_telegram_html(source)
    chunks = chunk_rendered_text(rendered, max_len=18)

    assert "<b>" not in rendered
    assert "<u>" not in rendered
    assert _assert_valid_chunks(chunks, 18) == source
