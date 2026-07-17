from __future__ import annotations

import os
from pathlib import Path

from rpg_core.summary.front_matter import parse_markdown_front_matter
from rpg_core.summary.reader import SummaryReader


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_summary_reader_missing_directory_is_read_only(tmp_path: Path) -> None:
    session_root = tmp_path / "missing-session"

    index = SummaryReader(session_root).read_index()

    assert index.overall is None
    assert index.batches == ()
    assert not session_root.exists()


def test_summary_reader_parses_overall_and_batch_metadata(tmp_path: Path) -> None:
    session_root = tmp_path / "session"
    _write(
        session_root / "summaries" / "overall.md",
        """---
type: overall
last_batch_id: 2
---

# 雾港钟楼

主线已经推进。\n\n- 找到了钥匙
""",
    )
    _write(
        session_root / "summaries" / "002-key.md",
        """---
batch_id: 2
title: "盐霜钥匙"
source_turn_start: 4
source_turn_end: 7
source_message_ids:
  - 41
  - 42
time: "雨夜 23:40"
location: "雾港钟楼"
characters:
  - "林晚"
  - "伊凡"
---

林晚取得了第二把钥匙。
""",
    )

    index = SummaryReader(session_root).read_index()

    assert index.overall is not None
    assert index.overall.title == "雾港钟楼"
    assert index.overall.last_batch_id == 2
    assert index.overall.markdown.startswith("主线已经推进。")
    assert not index.overall.markdown.startswith("#")
    assert [item.batch_id for item in index.batches] == [2]
    assert index.batches[0].title == "盐霜钥匙"
    assert index.batches[0].characters == ("林晚", "伊凡")
    assert index.batches[0].time == "雨夜 23:40"
    assert index.batches[0].location == "雾港钟楼"
    assert index.batches[0].source_turn_start == 4
    assert index.batches[0].source_turn_end == 7
    assert index.batches[0].source_message_ids == (41, 42)
    assert SummaryReader(session_root).get("002") == index.batches[0]


def test_summary_reader_skips_malformed_and_keeps_newest_duplicate(tmp_path: Path) -> None:
    summaries = tmp_path / "session" / "summaries"
    older = summaries / "001-old.md"
    newer = summaries / "001-new.md"
    _write(older, "---\nbatch_id: 1\ntitle: Old\n---\nold body")
    _write(newer, "---\nbatch_id: 1\ntitle: New\n---\nnew body")
    _write(summaries / "broken.md", "---\nbatch_id: nope\n---\ninvalid")
    _write(summaries / "overall.md", "---\nlast_batch_id: 1\nmissing close")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    index = SummaryReader(tmp_path / "session").read_index()

    assert index.overall is None
    assert len(index.batches) == 1
    assert index.batches[0].title == "New"
    assert index.batches[0].markdown == "new body"


def test_summary_excerpt_is_normalized_and_bounded(tmp_path: Path) -> None:
    long_body = "  ".join(["剧情推进"] * 80)
    _write(
        tmp_path / "session" / "summaries" / "000-long.md",
        f"---\nbatch_id: 0\ntitle: Long\n---\n{long_body}",
    )

    document = SummaryReader(tmp_path / "session").read_index().batches[0]

    assert "  " not in document.excerpt
    assert len(document.excerpt) <= 240
    assert document.excerpt.endswith("…")


def test_shared_front_matter_parser_uses_yaml_lists() -> None:
    front_matter, body = parse_markdown_front_matter(
        "---\ncharacters:\n  - Alice\n  - Bob\n---\nbody"
    )

    assert front_matter["characters"] == ["Alice", "Bob"]
    assert body == "body"
