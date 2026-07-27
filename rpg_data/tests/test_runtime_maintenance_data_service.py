from __future__ import annotations

import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from rpg_data.errors import DataIntegrityError
from rpg_data.model.runtime_maintenance import RuntimeMaintenanceItem
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways
from rpg_data.services import runtime_maintenance as maintenance_module


@pytest.fixture(autouse=True)
def _reset_gateways(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    monkeypatch.setenv("RPG_WORLD_BOOTSTRAP_DELETE_UNINDEXED_DIRS", "false")
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def _create_unindexed_session(
    tmp_path: Path,
    session_id: str,
    *,
    story_id: str = "1",
) -> Path:
    path = (
        tmp_path
        / "data"
        / "demo_workspace"
        / "stories"
        / story_id
        / session_id
    )
    path.mkdir(parents=True, exist_ok=True)
    (path / "marker.txt").write_text(session_id, encoding="utf-8")
    return path


def _scan_session_item(
    tmp_path: Path,
    session_id: str,
) -> tuple[object, RuntimeMaintenanceItem]:
    gateway = get_data_service_gateway(tmp_path / "runtime-maintenance.sqlite3")
    service = gateway.runtime_maintenance
    scan = service.scan_unindexed_runtime("demo_workspace")
    assert scan is not None
    return service, next(
        item for item in scan.items if item.session_id == session_id
    )


def test_scan_returns_immutable_workspace_scoped_items(tmp_path: Path) -> None:
    path = _create_unindexed_session(tmp_path, "s_unindexed")
    service, item = _scan_session_item(tmp_path, "s_unindexed")

    assert item.workspace_id == "demo_workspace"
    assert item.relative_path == "stories/1/s_unindexed"
    assert item.path == str(path.resolve())
    assert service.scan_unindexed_runtime("missing") is None
    with pytest.raises(FrozenInstanceError):
        item.path = "forged"  # type: ignore[misc]


def test_delete_rejects_forged_and_stale_locators(tmp_path: Path) -> None:
    path = _create_unindexed_session(tmp_path, "s_unindexed")
    service, item = _scan_session_item(tmp_path, "s_unindexed")

    forged = replace(item, path=str(path / "forged"))
    forged_result = service.delete_unindexed_runtime_item(forged)
    assert forged_result is not None
    assert forged_result.matched is False
    assert path.is_dir()

    path.rename(path.with_name("s_replaced"))
    stale_result = service.delete_unindexed_runtime_item(item)
    assert stale_result is not None
    assert stale_result.matched is False


def test_delete_rejects_cross_workspace_batches(tmp_path: Path) -> None:
    _create_unindexed_session(tmp_path, "s_one")
    _create_unindexed_session(tmp_path, "s_two")
    service, first = _scan_session_item(tmp_path, "s_one")
    scan = service.scan_unindexed_runtime("demo_workspace")
    assert scan is not None
    second = next(item for item in scan.items if item.session_id == "s_two")

    with pytest.raises(
        DataIntegrityError,
        match="must belong to one workspace",
    ):
        service.delete_unindexed_runtime_items(
            (first, replace(second, workspace_id="other"))
        )


def test_delete_collapses_nested_story_and_session_targets(
    tmp_path: Path,
) -> None:
    session_path = _create_unindexed_session(
        tmp_path,
        "s_nested",
        story_id="999",
    )
    story_path = session_path.parent
    gateway = get_data_service_gateway(tmp_path / "nested.sqlite3")
    service = gateway.runtime_maintenance
    scan = service.scan_unindexed_runtime("demo_workspace")
    assert scan is not None
    story_item = next(
        item
        for item in scan.items
        if item.kind == "story" and item.story_id == "999"
    )
    session_item = next(
        item for item in scan.items if item.session_id == "s_nested"
    )

    result = service.delete_unindexed_runtime_items(
        (session_item, story_item, session_item)
    )

    assert result is not None
    assert result.matched is True
    assert result.cleanup_pending is False
    assert result.deleted_items == (story_item,)
    assert not story_path.exists()


def test_staging_failure_restores_already_isolated_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_path = _create_unindexed_session(tmp_path, "s_first")
    second_path = _create_unindexed_session(tmp_path, "s_second")
    gateway = get_data_service_gateway(tmp_path / "rollback.sqlite3")
    service = gateway.runtime_maintenance
    scan = service.scan_unindexed_runtime("demo_workspace")
    assert scan is not None
    targets = tuple(
        item
        for item in scan.items
        if item.session_id in {"s_first", "s_second"}
    )
    real_replace = os.replace
    stage_calls = 0
    injected = OSError("injected staging failure")

    def fail_second_stage(source: object, destination: object) -> None:
        nonlocal stage_calls
        source_path = Path(source)
        if maintenance_module._QUARANTINE_PREFIX in str(Path(destination)):
            stage_calls += 1
            if stage_calls == 2:
                raise injected
        real_replace(source_path, destination)

    monkeypatch.setattr(maintenance_module.os, "replace", fail_second_stage)

    with pytest.raises(OSError) as raised:
        service.delete_unindexed_runtime_items(targets)

    assert raised.value is injected
    assert first_path.is_dir()
    assert second_path.is_dir()
    assert not list(first_path.parents[2].glob(".runtime-maintenance-*"))


def test_purge_failure_returns_pending_quarantine_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    original_path = _create_unindexed_session(tmp_path, "s_pending")
    service, item = _scan_session_item(tmp_path, "s_pending")
    injected = OSError("injected purge failure")

    def fail_purge(_path: object) -> None:
        raise injected

    monkeypatch.setattr(maintenance_module.shutil, "rmtree", fail_purge)
    caplog.set_level(
        "ERROR",
        logger="rpg_data.runtime_maintenance",
    )

    result = service.delete_unindexed_runtime_item(item)

    assert result is not None
    assert result.matched is True
    assert result.cleanup_pending is True
    assert not original_path.exists()
    assert len(result.pending_cleanup_paths) == 1
    assert Path(result.pending_cleanup_paths[0]).is_dir()
    assert "injected purge failure" in caplog.text
    assert "cleanup pending" in caplog.text
