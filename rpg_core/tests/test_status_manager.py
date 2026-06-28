from __future__ import annotations

from types import SimpleNamespace

from rpg_data.models import SessionStatusTable
from rpg_core.status.manager import StatusManager
from rpg_core.utils.manager_base import BaseManager


def _table(
    *,
    table_id: int = 1,
    type_name: str = "世界状态",
    name: str = "旗帜",
    builtin_key: str = "",
    rows: tuple[tuple[str, ...], ...] = (("封印", "完整"),),
) -> SessionStatusTable:
    return SessionStatusTable(
        id=table_id,
        session_id="s_main",
        session_type_id=10,
        workspace_id="ws",
        story_id=20,
        source_table_id=30,
        type_name=type_name,
        builtin_key=builtin_key,
        name=name,
        relative_path=f"stories/20/s_main/status/{type_name}/{name}.csv",
        description="",
        headers=("属性", "值"),
        rows=rows,
        sort_order=0,
        metadata_json="{}",
        version=1,
        created_at="",
        updated_at="",
    )


class FakeStatusService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.normal_table = _table()
        self.scene_table = _table(
            table_id=2,
            type_name="场景状态",
            name="当前场景",
            builtin_key="scene",
            rows=(("位置", "森林"),),
        )

    def list_session_types(self, session_id: str):
        self.calls.append(("list_session_types", session_id))
        return [SimpleNamespace(name="世界状态"), SimpleNamespace(name="场景状态")]

    def list_tables(self, session_id: str, type_name: str):
        self.calls.append(("list_tables", session_id, type_name))
        return [self.scene_table if type_name == "场景状态" else self.normal_table]

    def list_context_tables(self, session_id: str):
        self.calls.append(("list_context_tables", session_id))
        return [self.normal_table]

    def get_table(self, session_id: str, type_name: str, table_name: str):
        self.calls.append(("get_table", session_id, type_name, table_name))
        return self.normal_table

    def get_table_by_id(self, table_id: int):
        self.calls.append(("get_table_by_id", table_id))
        return self.scene_table if table_id == 2 else self.normal_table

    def set_key_value(self, table_id: int, key: str, value: str, **kwargs):
        self.calls.append(("set_key_value", table_id, key, value, kwargs))
        return self.scene_table

    def delete_key_value(self, table_id: int, key: str, **kwargs):
        self.calls.append(("delete_key_value", table_id, key, kwargs))
        return self.scene_table

    def get_active_scene_table(self, session_id: str):
        self.calls.append(("get_active_scene_table", session_id))
        return self.scene_table

    def get_scene_attrs(self, session_id: str):
        self.calls.append(("get_scene_attrs", session_id))
        return {"位置": "森林"}


def test_status_manager_is_thin_session_adapter() -> None:
    service = FakeStatusService()
    manager = StatusManager("s_main", service=service)

    assert not isinstance(manager, BaseManager)
    assert not hasattr(manager, "path")
    assert not hasattr(manager, "loader")
    assert manager.list_types() == ["世界状态", "场景状态"]
    assert manager.list_tables("世界状态") == ["旗帜"]
    assert manager.list_context_tables()[0]["name"] == "旗帜"
    assert manager.get_active_scene_table()["id"] == 2
    assert manager.get_scene_attrs() == {"位置": "森林"}


def test_status_manager_defaults_to_gateway(monkeypatch) -> None:
    import rpg_core.status.manager as manager_module

    service = FakeStatusService()
    monkeypatch.setattr(
        manager_module,
        "get_data_service_gateway",
        lambda: SimpleNamespace(status=service),
    )

    manager = StatusManager("s_gateway")
    assert manager.list_context_tables()[0]["id"] == 1
    assert service.calls == [("list_context_tables", "s_gateway")]


def test_status_manager_delegates_selector_writes() -> None:
    service = FakeStatusService()
    manager = StatusManager("s_main", service=service)

    manager.set_key_value(2, "位置", "城堡")
    manager.delete_key_value(2, "天气")

    assert service.calls == [
        ("set_key_value", 2, "位置", "城堡", {"key_column": "属性", "value_column": "值"}),
        ("delete_key_value", 2, "天气", {"key_column": "属性"}),
    ]


def test_context_factory_initializes_status_manager_with_session_id(
    monkeypatch,
    make_data_session,
) -> None:
    make_data_session("s_factory")
    import rpg_core.character as character_module
    import rpg_core.lorebook as lorebook_module
    import rpg_core.status as status_module
    from rpg_core.context.factory import build_rpg_context

    seen_session_ids: list[str] = []

    class FakeCharacterManager:
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id

        def list_enabled_characters(self):
            return []

    class FakeLorebookManager:
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id

        def list_enabled_entries(self):
            return []

    class FakeStatusManager:
        def __init__(self, session_id: str) -> None:
            seen_session_ids.append(session_id)

        def get_active_scene_table(self):
            return None

        def list_context_tables(self):
            return []

    monkeypatch.setattr(character_module, "CharacterManager", FakeCharacterManager)
    monkeypatch.setattr(lorebook_module, "LorebookManager", FakeLorebookManager)
    monkeypatch.setattr(status_module, "StatusManager", FakeStatusManager)

    context = build_rpg_context(workspace="data/test", session_id="s_factory")

    assert seen_session_ids == ["s_factory"]
    assert isinstance(context["status_mgr"], FakeStatusManager)
    assert context["scene_tracker"] is None
