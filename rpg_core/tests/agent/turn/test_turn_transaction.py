from types import SimpleNamespace

import pytest

from rpg_core.agent.turn.transaction import transaction as transaction_module
from rpg_core.agent.turn.transaction.commit_plan import TurnCommitPlan
from rpg_core.agent.turn.transaction.message_scratch import MessageScratch
from rpg_core.agent.turn.transaction.status_scratch import StatusDocumentScratch
from rpg_core.context.models import Message, Role
from rpg_core.session import InvalidTurnMetadataError, SessionManager


def test_turn_transaction_begin_failure_clears_active_turn(monkeypatch) -> None:
    session = SessionManager(history_enabled=False)
    transaction = transaction_module.AgentTurnTransaction(
        session=session,
        status_mgr=None,
        scene_tracker=None,
    )

    def fail_message_scratch(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("scratch failed")

    monkeypatch.setattr(transaction_module, "MessageScratch", fail_message_scratch)
    with pytest.raises(RuntimeError, match="scratch failed"):
        transaction.begin(SimpleNamespace())

    assert session.begin_turn() == 1
    session.end_turn(1)


def test_turn_commit_plan_restores_history_on_turn_metadata_error() -> None:
    session = SessionManager(history_enabled=False)
    session.append(Role.USER, "base", turn_id=1, seq_in_turn=1)
    scratch = MessageScratch(
        turn_id=2,
        base_history=session.history,
        staged_messages=[
            Message(Role.USER, "u2", turn_id=2, seq_in_turn=1),
            Message(Role.ASSISTANT, "duplicate", turn_id=2, seq_in_turn=1),
        ],
    )
    plan = TurnCommitPlan(
        session=session,
        status_mgr=None,
        message_scratch=scratch,
        status_scratch=StatusDocumentScratch(None),
    )

    with pytest.raises(InvalidTurnMetadataError, match="seq_in_turn must increase"):
        plan.commit()

    assert [message.content for message in session.history] == ["base"]


def test_provider_message_serialization_excludes_persistence_metadata() -> None:
    message = Message(
        Role.USER,
        "hello",
        mode="gm",
        uid=9,
        turn_id=3,
        seq_in_turn=1,
    )

    assert message.to_provider_dict() == {"role": "user", "content": "hello"}
    assert message.to_dict() == {"role": "user", "content": "hello"}
    assert message.to_persistence_dict() == {
        "role": "user",
        "content": "hello",
        "mode": "gm",
        "uid": 9,
        "turn_id": 3,
        "seq_in_turn": 1,
    }
