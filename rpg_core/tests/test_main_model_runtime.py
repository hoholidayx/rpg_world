from types import SimpleNamespace

from rpg_core.agent import model_runtime as runtime_module
from rpg_core.agent.model_runtime import MainModelRuntime


class _SelectionService:
    def __init__(self) -> None:
        self.selections = {}

    def resolve_session(self, session_id: str):  # noqa: ANN201
        return self.selections.get(session_id)


class _Provider:
    def __init__(self, model: str) -> None:
        self._model = model

    def get_default_model(self) -> str:
        return self._model


def _selection(key: str, model: str):  # noqa: ANN201
    return SimpleNamespace(
        effective_provider_key=key,
        effective_source="session",
        effective=SimpleNamespace(model=model, context_window=100),
    )


def test_main_model_runtime_reuses_provider_for_same_effective_key(monkeypatch) -> None:
    selections = _SelectionService()
    selections.selections["s1"] = _selection("chat-a", "configured-a")
    calls: list[str] = []

    class _Manager:
        def get_provider(self, _biz_key, *, provider_key):  # noqa: ANN001, ANN201
            calls.append(provider_key)
            return _Provider(f"provider-{provider_key}")

    monkeypatch.setattr(
        runtime_module.LLMClientManager,
        "get",
        classmethod(lambda cls: _Manager()),
    )
    runtime = MainModelRuntime(
        selection_service=selections,
    )

    first = runtime.provider_for("s1")
    selections.selections["s1"] = _selection("chat-a", "updated-config")
    second = runtime.provider_for("s1")

    assert first is second
    assert calls == ["chat-a"]
    assert runtime.selection.effective.model == "updated-config"
    assert runtime.model == "provider-chat-a"


def test_main_model_runtime_switches_provider_only_for_new_key(monkeypatch) -> None:
    selections = _SelectionService()
    selections.selections["s1"] = _selection("chat-a", "a")
    calls: list[str] = []

    class _Manager:
        def get_provider(self, _biz_key, *, provider_key):  # noqa: ANN001, ANN201
            calls.append(provider_key)
            return _Provider(provider_key)

    monkeypatch.setattr(
        runtime_module.LLMClientManager,
        "get",
        classmethod(lambda cls: _Manager()),
    )
    runtime = MainModelRuntime(
        selection_service=selections,
    )
    assert runtime.model is None

    assert runtime.provider_for("s1").get_default_model() == "chat-a"
    selections.selections["s1"] = _selection("chat-b", "b")
    assert runtime.provider_for("s1").get_default_model() == "chat-b"
    assert calls == ["chat-a", "chat-b"]


def test_main_model_runtime_requires_catalog_selection() -> None:
    runtime = MainModelRuntime(
        selection_service=_SelectionService(),
    )

    try:
        runtime.resolve("missing")
    except FileNotFoundError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("missing selection should fail")
