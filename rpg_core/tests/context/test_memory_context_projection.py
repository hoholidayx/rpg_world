from __future__ import annotations

from types import SimpleNamespace

from rpg_core.context.rendering import render_jinja_template


def test_memory_context_templates_render_facts_without_trace_identity() -> None:
    persistent = render_jinja_template(
        "modules/persistent_memory.jinja",
        persistent_memory=[
            SimpleNamespace(
                memory_id="persistent-uuid-must-stay-hidden",
                revision_number=3,
                text="艾琳承诺替莱昂保守身世秘密。",
                memory_kind="commitment",
                epistemic_status="confirmed",
                salience=0.9,
                evidence=[{"message_id": 991}],
            )
        ],
    )
    story = render_jinja_template(
        "modules/story_memory.jinja",
        story_details=[{
            "id": 42,
            "turn_id": 17,
            "text": "莱昂把银钥匙交给艾琳。",
            "memory_kind": "clue",
            "epistemic_status": "confirmed",
            "salience": 0.8,
            "evidence": [{
                "message_id": 992,
                "turn_id": 17,
                "content_hash": "evidence-hash-must-stay-hidden",
            }],
        }],
    )

    assert "[commitment; confirmed] 艾琳承诺替莱昂保守身世秘密。" in persistent
    assert "[clue; confirmed] 莱昂把银钥匙交给艾琳。" in story
    combined = persistent + story
    for hidden in (
        "persistent-uuid-must-stay-hidden",
        "revision_number",
        "991",
        "992",
        "evidence-hash-must-stay-hidden",
        "turn_id",
        "salience",
    ):
        assert hidden not in combined
