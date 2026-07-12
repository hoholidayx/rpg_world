from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_service.schemas import AgentMessageRequest


@pytest.mark.parametrize("value", [None, "", "   "])
def test_agent_message_mode_empty_values_normalize_to_ic(value: object) -> None:
    request = AgentMessageRequest.model_validate({
        "session_id": "s1",
        "message": "hello",
        "mode": value,
    })
    assert request.mode == "ic"


def test_agent_message_mode_normalizes_case_and_rejects_invalid() -> None:
    assert AgentMessageRequest.model_validate({
        "session_id": "s1",
        "message": "hello",
        "mode": " GM ",
    }).mode == "gm"
    assert AgentMessageRequest(session_id="s1", message="hello").mode == "ic"
    with pytest.raises(ValidationError, match="invalid turn mode"):
        AgentMessageRequest.model_validate({
            "session_id": "s1",
            "message": "hello",
            "mode": "chat",
        })
    with pytest.raises(ValidationError):
        AgentMessageRequest.model_validate({
            "session_id": "s1",
            "message": "hello",
            "narrative_style_id": 0,
        })
