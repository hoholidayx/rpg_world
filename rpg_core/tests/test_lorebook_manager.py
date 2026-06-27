from __future__ import annotations

from rpg_data.models import SessionLorebookEntry
from rpg_core.lorebook.manager import LorebookManager


class FakeLorebookService:
    def __init__(self, entries: list[SessionLorebookEntry] | None = None) -> None:
        self.entries = entries or []
        self.calls: list[tuple[str, str]] = []

    def list_entries(self, session_id: str):
        self.calls.append(("list_entries", session_id))
        return list(self.entries)

    def list_enabled_entries(self, session_id: str):
        self.calls.append(("list_enabled_entries", session_id))
        return list(self.entries)

    def get_entry(self, session_id: str, name: str):
        self.calls.append(("get_entry", session_id))
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None


def _entry(
    name: str,
    *,
    entry_id: int = 1,
    mount_id: int = 10,
    sort_order: int = 0,
) -> SessionLorebookEntry:
    return SessionLorebookEntry(
        id=entry_id,
        mount_id=mount_id,
        workspace_id="workspace",
        story_id=2,
        name=name,
        content=f"{name} content",
        description=f"{name} description",
        tags=("tag",),
        sort_order=sort_order,
    )


def test_lorebook_manager_delegates_to_service_without_path_or_cache() -> None:
    service = FakeLorebookService([_entry("First", sort_order=20)])
    manager = LorebookManager("s_main", service=service)

    assert manager.session_id == "s_main"
    assert manager.list_enabled_entries() == [
        {
            "id": 1,
            "mount_id": 10,
            "workspace_id": "workspace",
            "story_id": 2,
            "name": "First",
            "content": "First content",
            "description": "First description",
            "tags": ["tag"],
            "sort_order": 20,
        }
    ]
    assert service.calls == [("list_enabled_entries", "s_main")]

    service.entries.append(_entry("Second", entry_id=2, mount_id=11, sort_order=30))
    assert [entry["name"] for entry in manager.list_enabled_entries()] == ["First", "Second"]


def test_lorebook_manager_defaults_to_gateway_service(monkeypatch) -> None:
    import rpg_core.lorebook.manager as manager_module

    service = FakeLorebookService([_entry("Gateway")])
    calls = 0

    class FakeGateway:
        lorebook = service

    def fake_get_gateway():
        nonlocal calls
        calls += 1
        return FakeGateway()

    monkeypatch.setattr(manager_module, "get_data_service_gateway", fake_get_gateway)

    manager = LorebookManager("s_gateway")

    assert calls == 1
    assert manager.list_enabled_entries()[0]["name"] == "Gateway"


def test_lorebook_manager_lists_all_entries_and_gets_by_name() -> None:
    service = FakeLorebookService([
        _entry("First"),
        _entry("Second", entry_id=2, mount_id=11),
    ])
    manager = LorebookManager("s_main", service=service)

    assert [entry["name"] for entry in manager.list_entries()] == ["First", "Second"]
    assert manager.get_entry("Second")["name"] == "Second"


def test_lorebook_manager_missing_entry_raises_file_not_found() -> None:
    manager = LorebookManager("missing", service=FakeLorebookService())

    assert manager.list_enabled_entries() == []
    try:
        manager.get_entry("Nope")
    except FileNotFoundError as exc:
        assert str(exc) == "Lorebook entry not found: Nope"
    else:
        raise AssertionError("expected FileNotFoundError")


def test_context_factory_initializes_lorebook_manager_with_session_id(
    monkeypatch,
    temp_settings,
) -> None:
    del temp_settings
    import rpg_core.character as character_module
    import rpg_core.lorebook as lorebook_module
    from rpg_core.context.factory import build_rpg_context

    seen_session_ids: list[str] = []

    class FakeLorebookManager:
        def __init__(self, session_id: str) -> None:
            seen_session_ids.append(session_id)

        def list_enabled_entries(self):
            return []

    class FakeCharacterManager:
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id

        def list_enabled_characters(self):
            return []

    monkeypatch.setattr(character_module, "CharacterManager", FakeCharacterManager)
    monkeypatch.setattr(lorebook_module, "LorebookManager", FakeLorebookManager)

    context = build_rpg_context(workspace="data/test", session_id="s_factory")

    assert seen_session_ids == ["s_factory"]
    assert isinstance(context["lorebook_mgr"], FakeLorebookManager)
