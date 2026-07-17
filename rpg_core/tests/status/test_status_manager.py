from __future__ import annotations

from types import SimpleNamespace

from rpg_data.models import STATUS_KIND_NORMAL, STATUS_KIND_SCENE, SessionStatusTable, StatusTableDocument
from rpg_core.status.manager import StatusManager


def _table(
    *,
    table_id: int = 1,
    status_kind: str = STATUS_KIND_NORMAL,
    name: str = "旗帜",
    rows: tuple[tuple[str, str], ...] = (("封印", "完整"),),
) -> SessionStatusTable:
    return SessionStatusTable(
        id=table_id,
        session_id="s_main",
        workspace_id="ws",
        story_id=20,
        source_table_id=30,
        origin="template_copy",
        status_kind=status_kind,
        name=name,
        description="",
        document=StatusTableDocument.from_data(
            SimpleNamespace(headers=("属性", "值"), rows=rows)  # type: ignore[arg-type]
        ),
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
            status_kind=STATUS_KIND_SCENE,
            name="当前场景",
            rows=(("位置", "森林"),),
        )

    def list_tables(self, session_id: str, status_kind: str | None = None):
        self.calls.append(("list_tables", session_id, status_kind))
        if status_kind == STATUS_KIND_SCENE:
            return [self.scene_table]
        if status_kind == STATUS_KIND_NORMAL:
            return [self.normal_table]
        return [self.normal_table, self.scene_table]

    def list_context_tables(self, session_id: str):
        self.calls.append(("list_context_tables", session_id))
        return [self.normal_table]

    def get_table(self, session_id: str, table_name: str, status_kind: str | None = None):
        self.calls.append(("get_table", session_id, table_name, status_kind))
        return self.normal_table

    def get_table_by_id(self, table_id: int):
        self.calls.append(("get_table_by_id", table_id))
        return self.scene_table if table_id == 2 else self.normal_table

    def get_table_for_session(self, session_id: str, table_id: int):
        self.calls.append(("get_table_for_session", session_id, table_id))
        return self.scene_table if table_id == 2 else self.normal_table

    def save_table(self, table_id: int, document: StatusTableDocument):
        self.calls.append(("save_table", table_id, document))
        table = self.scene_table if table_id == 2 else self.normal_table
        return SessionStatusTable(
            id=table.id,
            session_id=table.session_id,
            workspace_id=table.workspace_id,
            story_id=table.story_id,
            source_table_id=table.source_table_id,
            origin=table.origin,
            name=table.name,
            status_kind=table.status_kind,
            description=table.description,
            document=document,
            sort_order=table.sort_order,
            metadata_json=table.metadata_json,
            version=table.version,
            created_at=table.created_at,
            updated_at=table.updated_at,
        )

    def save_table_for_session(
        self,
        session_id: str,
        table_id: int,
        document: StatusTableDocument,
        **kwargs,
    ):
        self.calls.append(("save_table_for_session", session_id, table_id, document, kwargs))
        table = self.scene_table if table_id == 2 else self.normal_table
        return SessionStatusTable(
            id=table.id,
            session_id=table.session_id,
            workspace_id=table.workspace_id,
            story_id=table.story_id,
            source_table_id=table.source_table_id,
            origin=table.origin,
            name=table.name,
            status_kind=table.status_kind,
            description=table.description,
            document=document,
            sort_order=table.sort_order,
            metadata_json=table.metadata_json,
            version=table.version,
            created_at=table.created_at,
            updated_at=table.updated_at,
        )

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

    assert not hasattr(manager, "reload")
    assert not hasattr(manager, "_data_dir")
    assert not hasattr(manager, "path")
    assert not hasattr(manager, "loader")
    assert manager.list_types() == [STATUS_KIND_NORMAL, STATUS_KIND_SCENE]
    assert manager.list_tables(STATUS_KIND_NORMAL) == ["旗帜"]
    assert manager.list_context_tables()[0]["name"] == "旗帜"
    assert manager.get_table("旗帜", STATUS_KIND_NORMAL)["id"] == 1
    assert manager.get_active_scene_table()["id"] == 2
    assert manager.get_active_scene_table_ref() == (2, (STATUS_KIND_SCENE, "当前场景"))
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


def test_status_manager_exposes_document_cow_helpers() -> None:
    service = FakeStatusService()
    manager = StatusManager("s_main", service=service)

    document = manager.get_table_document_by_id(2)
    updated = document.with_key_value("位置", "城堡")
    table = manager.save_table_document(2, updated)

    assert table["rows"] == [["位置", "城堡"]]
    assert service.calls == [
        ("get_table_for_session", "s_main", 2),
        ("get_table_for_session", "s_main", 2),
        (
            "save_table_for_session",
            "s_main",
            2,
            updated,
            {
                "expected_status_kind": STATUS_KIND_SCENE,
                "base_document": None,
                "write_source": "agent_turn",
            },
        ),
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
