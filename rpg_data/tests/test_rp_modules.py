from __future__ import annotations

from rpg_core.session.catalog import SessionCatalogService
from rpg_data.services import get_data_service_gateway


def test_catalog_default_mount_and_session_override_round_trip(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "rp-modules.sqlite3")
    service = gateway.rp_modules

    assert [item.module_name for item in service.list_catalog()] == [
        "narrative_outcome",
        "plot_scheduler",
        "dice",
    ]
    story_modules = service.list_story_modules("demo_workspace", 1)
    assert story_modules is not None
    assert {item.module_name for item in story_modules} == {
        "narrative_outcome",
        "dice",
    }

    story = service.upsert_story_module(
        "demo_workspace",
        1,
        "narrative_outcome",
        enabled=True,
        config={"auto_adjudication_enabled": False},
    )
    assert story is not None
    assert story.config == {"auto_adjudication_enabled": False}

    override = service.upsert_session_override(
        "s_forest001",
        "narrative_outcome",
        enabled=False,
        config={"weights": {"critical_success": 10}},
    )
    assert override is not None
    assert override.enabled is False
    assert override.config == {"weights": {"critical_success": 10}}
    empty_override = service.upsert_session_override(
        "s_forest001",
        "narrative_outcome",
        enabled=None,
        config={},
    )
    assert empty_override is not None
    assert empty_override.enabled is None
    assert empty_override.config == {}

    service.upsert_session_override(
        "s_forest001",
        "narrative_outcome",
        enabled=False,
        config={},
    )
    assert service.delete_session_override("s_forest001", "narrative_outcome") is True
    assert service.get_session_override("s_forest001", "narrative_outcome") is None


def test_new_story_mounts_all_current_default_modules(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "new-story-rp-modules.sqlite3")
    story = SessionCatalogService(gateway.sessions).create_story(
        "demo_workspace",
        title="New Story",
    )
    assert story is not None
    mounted = gateway.rp_modules.list_story_modules("demo_workspace", story.id)
    assert mounted is not None
    assert {item.module_name for item in mounted} == {
        "narrative_outcome",
        "plot_scheduler",
        "dice",
    }
