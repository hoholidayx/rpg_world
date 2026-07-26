from __future__ import annotations

from pathlib import Path

from rpg_core.summary.reference import SessionSummaryReferenceProvider
from rpg_data.model.session_reference import (
    SessionReferenceLocator,
    SessionReferenceSummarySource,
    SummaryBatchTurnRange,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_summary_reference_merges_ranges_and_orders_newest_batches(
    tmp_path: Path,
) -> None:
    locator = SessionReferenceLocator("s_summary", "workspace", 2)
    _write(
        tmp_path / "summaries" / "overall.md",
        "---\nlast_batch_id: 2\n---\n# 总览\n整体正文",
    )
    _write(
        tmp_path / "summaries" / "001.md",
        "---\nbatch_id: 1\nsource_turn_start: 99\nsource_turn_end: 99\n"
        "---\n第一批",
    )
    _write(
        tmp_path / "summaries" / "002.md",
        "---\nbatch_id: 2\nsource_turn_start: 5\nsource_turn_end: 7\n"
        "---\n第二批",
    )
    _write(
        tmp_path / "summaries" / "003.md",
        "---\nbatch_id: 3\nsource_turn_start: 9\nsource_turn_end: 12\n"
        "source_message_ids:\n  - 301\n---\n第三批",
    )
    source = SessionReferenceSummarySource(
        runtime_dir=tmp_path,
        batch_turn_ranges=(
            SummaryBatchTurnRange(batch_id=1, turn_start=1, turn_end=4),
            SummaryBatchTurnRange(batch_id=2, turn_start=5, turn_end=8),
        ),
    )
    provider = SessionSummaryReferenceProvider(
        type(
            "Source",
            (),
            {"get_summary_source": lambda _self, requested: source},
        )()
    )

    documents = provider.list_summaries(locator)

    assert [item.summary_id for item in documents] == [
        "overall",
        "3",
        "2",
        "1",
    ]
    assert (documents[0].turn_start, documents[0].turn_end) == (1, 8)
    assert documents[0].turn_range_source == "sql"
    assert (documents[1].turn_start, documents[1].turn_end) == (9, 12)
    assert documents[1].turn_range_source == "front_matter"
    assert documents[1].source_message_ids == (301,)
    assert (documents[2].turn_start, documents[2].turn_end) == (5, 8)
    assert documents[2].turn_range_source == "sql"
    assert (documents[3].turn_start, documents[3].turn_end) == (1, 4)
    assert documents[3].turn_range_source == "sql"
    assert provider.get_summary(locator, "2").text == "第二批"


def test_summary_reference_falls_back_to_front_matter_and_aggregates_overall(
    tmp_path: Path,
) -> None:
    locator = SessionReferenceLocator("s_summary", "workspace", 2)
    _write(
        tmp_path / "summaries" / "overall.md",
        "---\ntype: overall\nlast_batch_id: 3\n---\n# 总览\n整体正文",
    )
    _write(
        tmp_path / "summaries" / "002.md",
        "---\nbatch_id: 2\nsource_turn_start: 5\nsource_turn_end: 7\n"
        "---\n第二批",
    )
    _write(
        tmp_path / "summaries" / "003.md",
        "---\nbatch_id: 3\nsource_turn_start: 8\nsource_turn_end: 11\n"
        "---\n第三批",
    )
    source = SessionReferenceSummarySource(runtime_dir=tmp_path)
    provider = SessionSummaryReferenceProvider(
        type(
            "Source",
            (),
            {"get_summary_source": lambda _self, requested: source},
        )()
    )

    documents = provider.list_summaries(locator)

    assert [item.summary_id for item in documents] == ["overall", "3", "2"]
    assert (
        documents[0].turn_start,
        documents[0].turn_end,
        documents[0].turn_range_source,
    ) == (5, 11, "front_matter")
    assert (
        documents[1].turn_start,
        documents[1].turn_end,
        documents[1].turn_range_source,
    ) == (8, 11, "front_matter")
    assert documents[0].summary_type == "overall"
