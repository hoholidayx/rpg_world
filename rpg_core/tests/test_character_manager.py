from __future__ import annotations

from rpg_data.models import SessionCharacter, SessionCharacterDetail
from rpg_core.character import CharacterManager


class FakeCharacterService:
    def __init__(self, characters: list[SessionCharacter] | None = None) -> None:
        self.characters = characters or []
        self.calls: list[tuple[str, str]] = []

    def list_characters(self, session_id: str):
        self.calls.append(("list_characters", session_id))
        return list(self.characters)

    def get_character(self, session_id: str, name: str):
        self.calls.append(("get_character", session_id))
        for character in self.characters:
            if character.name == name:
                return character
        return None


def _detail(
    name: str,
    *,
    detail_id: int = 1,
    sort_order: int = 0,
) -> SessionCharacterDetail:
    return SessionCharacterDetail(
        id=detail_id,
        character_id=100,
        name=name,
        content=f"{name} detail",
        tags=("tag",),
        sort_order=sort_order,
    )


def _character(
    name: str,
    *,
    character_id: int = 1,
    mount_id: int = 10,
    details: tuple[SessionCharacterDetail, ...] = (),
    sort_order: int = 0,
) -> SessionCharacter:
    return SessionCharacter(
        id=character_id,
        mount_id=mount_id,
        workspace_id="workspace",
        story_id=2,
        name=name,
        personality=f"{name} personality",
        content=f"{name} content",
        details=details,
        sort_order=sort_order,
    )


def test_character_manager_delegates_to_service_without_path_or_cache() -> None:
    service = FakeCharacterService([
        _character("Alice", details=(_detail("外貌", sort_order=20),), sort_order=10)
    ])
    manager = CharacterManager("s_main", service=service)

    assert manager.session_id == "s_main"
    assert manager.list_enabled_characters() == [
        {
            "id": 1,
            "mount_id": 10,
            "workspace_id": "workspace",
            "story_id": 2,
            "name": "Alice",
            "personality": "Alice personality",
            "content": "Alice content",
            "details": [
                {
                    "id": 1,
                    "character_id": 100,
                    "name": "外貌",
                    "content": "外貌 detail",
                    "tags": ["tag"],
                    "sort_order": 20,
                }
            ],
            "sort_order": 10,
        }
    ]
    assert service.calls == [("list_characters", "s_main")]

    service.characters.append(_character("Bob", character_id=2, mount_id=11, sort_order=20))
    assert [character["name"] for character in manager.list_characters()] == ["Alice", "Bob"]


def test_character_manager_defaults_to_gateway_service(monkeypatch) -> None:
    import rpg_core.character as manager_module

    service = FakeCharacterService([_character("Gateway")])
    calls = 0

    class FakeGateway:
        character = service

    def fake_get_gateway():
        nonlocal calls
        calls += 1
        return FakeGateway()

    monkeypatch.setattr(manager_module, "get_data_service_gateway", fake_get_gateway)

    manager = CharacterManager("s_gateway")

    assert calls == 1
    assert manager.list_enabled_characters()[0]["name"] == "Gateway"


def test_character_manager_detail_queries() -> None:
    service = FakeCharacterService([
        _character("Alice", details=(_detail("外貌"), _detail("战斗", detail_id=2)))
    ])
    manager = CharacterManager("s_main", service=service)

    assert manager.get_character("Alice")["name"] == "Alice"
    assert [detail["name"] for detail in manager.list_details("Alice")] == ["外貌", "战斗"]
    assert manager.get_detail("Alice", "战斗")["content"] == "战斗 detail"
    assert manager.list_detail_names("Alice") == ["外貌", "战斗"]
    assert [detail["name"] for detail in manager.get_details_by_names("Alice", ["战斗"])] == ["战斗"]
    assert [detail["name"] for detail in manager.get_all_details("Alice")] == ["外貌", "战斗"]


def test_character_manager_missing_character_or_detail_raises() -> None:
    manager = CharacterManager("missing", service=FakeCharacterService())

    assert manager.list_enabled_characters() == []
    try:
        manager.get_character("Nope")
    except FileNotFoundError as exc:
        assert str(exc) == "Character not found: Nope"
    else:
        raise AssertionError("expected FileNotFoundError")

    manager = CharacterManager("s_main", service=FakeCharacterService([_character("Alice")]))
    try:
        manager.get_detail("Alice", "Nope")
    except FileNotFoundError as exc:
        assert str(exc) == "Detail not found: Nope"
    else:
        raise AssertionError("expected FileNotFoundError")


def test_context_factory_initializes_character_manager_with_session_id(
    monkeypatch,
    make_data_session,
) -> None:
    make_data_session("s_factory")
    import rpg_core.character as character_module
    import rpg_core.lorebook as lorebook_module
    from rpg_core.context.factory import build_rpg_context

    seen_session_ids: list[str] = []

    class FakeCharacterManager:
        def __init__(self, session_id: str) -> None:
            seen_session_ids.append(session_id)

        def list_enabled_characters(self):
            return []

    class FakeLorebookManager:
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id

        def list_enabled_entries(self):
            return []

    monkeypatch.setattr(character_module, "CharacterManager", FakeCharacterManager)
    monkeypatch.setattr(lorebook_module, "LorebookManager", FakeLorebookManager)

    context = build_rpg_context(workspace="data/test", session_id="s_factory")

    assert seen_session_ids == ["s_factory"]
    assert isinstance(context["character_mgr"], FakeCharacterManager)
