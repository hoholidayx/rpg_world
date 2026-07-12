from __future__ import annotations

from channels.telegram.action_registry import (
    CallbackConsumePolicy,
    CallbackResolutionStatus,
    TelegramActionRegistry,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def _registry(clock: _Clock | None = None) -> TelegramActionRegistry:
    counter = iter(range(100))
    return TelegramActionRegistry(
        clock=clock or _Clock(),
        token_factory=lambda: f"token{next(counter)}",
    )


def test_register_returns_compact_unique_callback_data() -> None:
    registry = _registry()

    first = registry.add(kind="one", chat_id="1", session_id="s1")
    second = registry.add(kind="two", chat_id="1", session_id="s1")

    assert first.startswith("tg:a:")
    assert second.startswith("tg:a:")
    assert first != second
    assert len(first.encode("utf-8")) < 64


def test_resolve_does_not_consume_and_on_claim_is_single_use() -> None:
    registry = _registry()
    callback_data = registry.add(kind="switch", chat_id="1", session_id="s1")

    resolution = registry.resolve(callback_data, chat_id="1", current_session_id="s1")

    assert resolution.resolved
    assert resolution.action is not None
    assert registry.resolve(callback_data, chat_id="1", current_session_id="s1").resolved
    assert registry.claim(resolution.token) is not None
    assert registry.claim(resolution.token) is None


def test_reusable_action_can_be_claimed_multiple_times() -> None:
    registry = _registry()
    callback_data = registry.add(
        kind="page",
        chat_id="1",
        session_id="s1",
        consume_policy=CallbackConsumePolicy.REUSABLE,
    )
    resolution = registry.resolve(callback_data, chat_id="1", current_session_id="s1")

    assert registry.claim(resolution.token) is not None
    assert registry.claim(resolution.token) is not None


def test_expiry_boundary_and_cleanup() -> None:
    clock = _Clock()
    registry = _registry(clock)
    callback_data = registry.add(kind="short", chat_id="1", session_id="s1", ttl_seconds=10)
    registry.add(kind="other", chat_id="1", session_id="s1", ttl_seconds=5)

    clock.value = 109.999
    assert registry.resolve(callback_data, chat_id="1", current_session_id="s1").resolved

    clock.value = 110.0
    resolution = registry.resolve(callback_data, chat_id="1", current_session_id="s1")
    assert resolution.status == CallbackResolutionStatus.EXPIRED
    assert len(registry) == 0


def test_rejects_wrong_chat_session_unknown_and_legacy_callbacks() -> None:
    registry = _registry()
    callback_data = registry.add(kind="switch", chat_id="1", session_id="s1")

    assert registry.resolve(
        callback_data,
        chat_id="2",
        current_session_id="s1",
    ).status == CallbackResolutionStatus.CHAT_MISMATCH
    assert registry.resolve(
        callback_data,
        chat_id="1",
        current_session_id="s2",
    ).status == CallbackResolutionStatus.SESSION_MISMATCH
    assert registry.resolve(
        "tg:a:missing",
        chat_id="1",
        current_session_id="s1",
    ).status == CallbackResolutionStatus.INVALID
    assert registry.resolve(
        "tg_sess:old",
        chat_id="1",
        current_session_id="s1",
    ).status == CallbackResolutionStatus.LEGACY


def test_invalidate_token_chat_session_and_clear() -> None:
    registry = _registry()
    one = registry.add(kind="one", chat_id="1", session_id="s1")
    registry.add(kind="two", chat_id="1", session_id="s2")
    registry.add(kind="three", chat_id="2", session_id="s1")

    one_token = one.removeprefix("tg:a:")
    assert registry.invalidate(one_token)
    assert registry.invalidate_chat("1") == 1
    assert registry.invalidate_session("s1") == 1
    assert len(registry) == 0

    registry.add(kind="four", chat_id="3", session_id=None)
    registry.clear()
    assert len(registry) == 0
