from __future__ import annotations

import pytest

from rpg_data import models
from rpg_data.services.gateway import get_data_service_gateway
from rpg_media.brief import DemoVisualBriefPlanner
from rpg_media.errors import MediaSourceRangeError
from rpg_media.settings import DemoBriefSettings
from rpg_media.source import build_source_snapshot, visible_excerpt


def test_source_fingerprint_tracks_persisted_message_changes(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "source.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="source")
    assert session is not None
    message = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "月光照在石门上",
        turn_id=1,
        seq_in_turn=1,
    )
    before = build_source_snapshot(
        gateway.media,
        session.id,
        start_turn_id=1,
        end_turn_id=1,
    )

    gateway.messages.update(message.id, content="火光照在石门上")
    after = build_source_snapshot(
        gateway.media,
        session.id,
        start_turn_id=1,
        end_turn_id=1,
    )

    assert before.fingerprint != after.fingerprint
    assert '"content":"月光照在石门上"' in before.snapshot_json


def test_source_policy_rejects_gaps_and_more_than_twenty_turns(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "source-policy.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="source policy")
    assert session is not None
    for turn_id in (*range(1, 22), 23):
        gateway.messages.append(
            session.id,
            models.MESSAGE_ROLE_USER,
            f"turn {turn_id}",
            turn_id=turn_id,
            seq_in_turn=1,
        )

    with pytest.raises(MediaSourceRangeError, match="at most 20"):
        build_source_snapshot(
            gateway.media,
            session.id,
            start_turn_id=1,
            end_turn_id=21,
        )
    with pytest.raises(MediaSourceRangeError, match="contiguous"):
        build_source_snapshot(
            gateway.media,
            session.id,
            start_turn_id=20,
            end_turn_id=23,
        )


def test_visible_excerpt_uses_first_middle_last_sixteen_characters() -> None:
    text = "".join(str(index % 10) for index in range(80))
    excerpt = visible_excerpt(text)
    parts = excerpt.split("…")
    assert len(parts) == 3
    assert parts[0] == text[:16]
    assert parts[-1] == text[-16:]
    assert all(len(part) == 16 for part in parts)


@pytest.mark.asyncio
async def test_demo_planner_is_configuration_driven(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "brief.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="brief")
    assert session is not None
    gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        "Alice 推开覆雪的石门。",
        turn_id=1,
        seq_in_turn=1,
    )
    source = build_source_snapshot(
        gateway.media,
        session.id,
        start_turn_id=1,
        end_turn_id=1,
    )
    planner = DemoVisualBriefPlanner(
        DemoBriefSettings(
            scene_description_prefix="SCENE: ",
            environment="snow",
            style="ink",
            aspect_ratio="3:2",
        )
    )

    brief = await planner.plan(source)

    assert brief.scene_description == "SCENE: Alice 推开覆雪的石门。"
    assert brief.environment == "snow"
    assert brief.style == "ink"
    assert brief.aspect_ratio == "3:2"
