"""Opt-in contract smoke test against the configured test-profile provider."""

from __future__ import annotations

import os

import pytest

from dream_service.repository import RPGDataDreamRepository
from llm_client.auth import resolve_llm_service_token
from llm_client.manager import LLMClientManager
from rpg_data import models
from rpg_data.services.gateway import get_data_service_gateway, reset_data_service_gateways
from rp_memory.dream.engine import DreamEngine
from rp_memory.dream.model import LLMDreamModel
from rp_memory.dream.source import DreamSourceSelector
from rp_memory.dream.types import DreamDepth, DreamScope
from rp_memory.story_memory_service import StoryMemoryApplicationService

pytestmark = [
    pytest.mark.dream_live,
    pytest.mark.skipif(
        os.getenv("DREAM_LIVE_TEST") != "1"
        or os.getenv("RPG_WORLD_PROFILE", "").strip().casefold() != "test",
        reason=(
            "set RPG_WORLD_PROFILE=test and DREAM_LIVE_TEST=1 to call the "
            "configured Dream provider"
        ),
    ),
]


def _repository(gateway):  # noqa: ANN001, ANN202
    return RPGDataDreamRepository(
        dream_memory_data=gateway.dream_memory,
        session_data=gateway.sessions,
        resolve_session_runtime_dir=gateway.sessions.resolve_session_runtime_dir,
        close_data_services=gateway.close,
    )


@pytest.fixture(scope="module", autouse=True)
def _require_explicit_dream_live_selection(request) -> None:  # noqa: ANN001
    mark_expression = str(request.config.getoption("markexpr") or "")
    if "dream_live" not in mark_expression:
        pytest.skip("select the live provider test explicitly with -m dream_live")


@pytest.mark.parametrize("depth", [DreamDepth.SHALLOW, DreamDepth.DEEP])
async def test_live_deepseek_dream_proposal_is_typed_and_applicable(
    tmp_path,
    depth: DreamDepth,
) -> None:
    """Run through LLM Service; never read provider keys in this process."""

    await LLMClientManager.aconfigure(
        base_url=os.getenv(
            "RPG_WORLD_LLM_SERVICE_URL",
            "http://127.0.0.1:8012/llm/v1",
        ),
        token=resolve_llm_service_token(),
        request_timeout_ms=120000,
        stream_timeout_ms=300000,
    )
    gateway = get_data_service_gateway(tmp_path / f"{depth.value}.sqlite3")
    try:
        session = gateway.catalog.create_session(
            "demo_workspace",
            1,
            title=f"live-{depth.value}",
        )
        assert session is not None
        user_message = gateway.messages.append(
            session.id,
            models.MESSAGE_ROLE_USER,
            "阿澈当众发誓：无论付出什么代价，我都会守护月光港。",
            turn_id=1,
            seq_in_turn=1,
        )
        assistant_message = gateway.messages.append(
            session.id,
            models.MESSAGE_ROLE_ASSISTANT,
            "港主接受了誓言，并将守港银徽永久交给阿澈。",
            turn_id=1,
            seq_in_turn=2,
        )
        StoryMemoryApplicationService(
            gateway.story_memory
        ).add_details_and_mark_processed(
            session.id,
            ({
                "text": "阿澈承诺守护月光港，并获授守港银徽。",
                "turn_id": 1,
                "source_turn_start": 1,
                "source_turn_end": 1,
                "memory_kind": "commitment",
                "salience": 0.95,
                "evidence_message_ids": [
                    user_message.id,
                    assistant_message.id,
                ],
            },),
            message_ids=(user_message.id, assistant_message.id),
        )

        repository = _repository(gateway)
        engine = DreamEngine(
            model=LLMDreamModel(),
            selector=DreamSourceSelector(max_map_turns=3, max_map_chars=4000),
            map_concurrency=1,
            reduce_candidate_batch_size=8,
        )
        selection = engine.prepare(
            repository.build_source_snapshot(session.id),
            depth=depth,
            scope=DreamScope.FULL,
        )
        stored = repository.create_proposal(selection)
        generated = await engine.generate(selection)
        ready = repository.set_proposal_ready(stored.proposal_id, generated.items)
        assert ready.status == "ready"
        selected_non_retire = [
            item
            for item in ready.items
            if item.selected and item.action != "retire"
        ]
        assert selected_non_retire
        assert all(
            item.action == "retire" or item.evidence
            for item in ready.items
        )
        applied = repository.apply_proposal(session.id, stored.proposal_id)
        assert applied.status == "applied"
        active_count = repository.list_memories(session.id).active_count
        assert 1 <= active_count <= 64
    finally:
        gateway.close()
        reset_data_service_gateways()
        await LLMClientManager.areset()
