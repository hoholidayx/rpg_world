from __future__ import annotations

import json

from rpg_core.summary.store import SummaryStore


def test_summary_store_loads_legacy_shape(tmp_path):
    path = tmp_path / "rpg_summaries.json"
    path.write_text(
        json.dumps(
            {
                "summaries": [
                    {"round_start": 1, "round_end": 2, "text": "legacy summary"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = SummaryStore(path)

    assert store.get_all_summaries() == ["legacy summary"]
