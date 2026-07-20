"""Static contracts for the rpg_data registry and persistence boundary."""

from __future__ import annotations

import ast
from pathlib import Path

from rpg_data import models
from rpg_data.model.memory import DreamProposal, PersistentMemoryBundle
from rpg_data.model.media import MediaJob, MediaLibraryAssetBundle
from rpg_data.model.session import Session, SessionDerivationJob, SessionMessage
from rpg_data.model.status import (
    SessionStatusTable,
    StatusTableDocument,
    StatusTableTemplate,
)
from rpg_data.services.dream_memory import DreamMemoryDataService
from rpg_data.services.media import MediaDataService
from rpg_data.services.plot_scheduling import PlotSchedulingDataService
from rpg_data.services.session import SessionDataService
from rpg_data.services.story_memory import StoryMemoryDataService
from rpg_data.services.status import StatusDataService

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOTS = (
    "agent_service",
    "channels",
    "dream_service",
    "llm_client",
    "llm_service",
    "media_service",
    "play_api",
    "rp_memory",
    "rpg_core",
    "rpg_data",
    "rpg_media",
    "rpg_tts",
    "tts_service",
)

FORBIDDEN_DATA_DEPENDENCIES = (
    "agent_service",
    "channels",
    "dream_service",
    "media_service",
    "play_api",
    "play_events",
    "rp_memory",
    "rpg_core",
    "rpg_media",
    "rpg_tts",
    "tts_service",
)

RECENT_APPLICATION_SERVICE_FILES = (
    "rpg_core/session/catalog.py",
    "rpg_core/session/deletion.py",
    "rpg_core/session/derivation.py",
    "rpg_core/session/reset.py",
    "rpg_core/session/role.py",
    "rpg_core/session/status.py",
    "rpg_core/rp_modules/plot_scheduler/management.py",
    "rpg_core/rp_modules/plot_scheduler/ledger.py",
    "rpg_core/rp_modules/plot_scheduler/snapshot.py",
    "rp_memory/dream/application.py",
    "rp_memory/persist_memory.py",
    "rp_memory/story_memory.py",
    "rp_memory/story_memory_service.py",
    "rpg_core/scene/status.py",
    "rpg_core/status/context_service.py",
    "rpg_core/status/administration.py",
    "rpg_core/status/manager.py",
    "rpg_media/service.py",
)

MEDIA_BUSINESS_FILES = (
    "rpg_media/service.py",
    "rpg_media/source.py",
    "rpg_media/background_agent.py",
    "media_service/worker.py",
)

STATUS_APPLICATION_SERVICE_FILES = (
    "rpg_core/scene/status.py",
    "rpg_core/session/status.py",
    "rpg_core/status/administration.py",
    "rpg_core/status/context_service.py",
    "rpg_core/status/manager.py",
)

# Gateway lookup is valid at process/composition boundaries. These legacy
# consumers remain explicit until their owning P3/P5/P6 work is scheduled;
# keeping them in a fixed allowlist prevents the service-locator surface from
# expanding during unrelated changes.
GATEWAY_LOOKUP_ALLOWLIST = frozenset({
    "agent_service/main.py",
    "dream_service/repository.py",
    "media_service/main.py",
    "play_api/backends/data_manager.py",
    "play_api/routers/plot_scheduling.py",
    "play_api/routers/rp_modules.py",
    "play_api/routers/session_composer.py",
    "play_api/routers/sessions.py",
    "rp_memory/run.py",
    "rpg_core/agent/agent.py",
    "rpg_core/agent/command/handlers.py",
    "rpg_core/agent/runtime/main_llm.py",
    "rpg_core/agent/runtime/tools.py",
    "rpg_core/character.py",
    "rpg_core/context/factory.py",
    "rpg_core/context/fixed_layer/contributors/story_prompt.py",
    "rpg_core/lorebook.py",
    "rpg_core/rp_modules/registry.py",
    "rpg_core/session/manager.py",
    "tts_service/main.py",
})

# A few pre-boundary services still receive the whole Gateway even though they
# do not perform a global lookup. Freeze that legacy surface independently so a
# new caller cannot bypass the lookup guard through constructor injection.
WHOLE_GATEWAY_REFERENCE_ALLOWLIST = frozenset({
    "media_service/main.py",
    "play_api/backends/data_manager.py",
    "rpg_core/agent/runtime/main_llm.py",
    "rpg_core/agent/turn/transaction/commit_plan.py",
    "rpg_core/session/history.py",
    "rpg_core/session/progress.py",
    "tts_service/main.py",
})


def test_rpg_data_does_not_import_business_or_transport_modules() -> None:
    violations: list[str] = []
    for path in _python_files(ROOT / "rpg_data"):
        for imported in _imports(path):
            if imported.startswith(FORBIDDEN_DATA_DEPENDENCIES):
                violations.append(f"{path.relative_to(ROOT)}: {imported}")

    assert violations == []


def test_repositories_and_peewee_records_do_not_escape_rpg_data() -> None:
    violations: list[str] = []
    for path in _production_python_files():
        if path.is_relative_to(ROOT / "rpg_data"):
            continue
        for imported in _imports(path):
            if imported == "rpg_data.repositories" or imported.startswith(
                "rpg_data.repositories."
            ):
                violations.append(f"{path.relative_to(ROOT)}: {imported}")

    assert violations == []


def test_recent_application_services_do_not_depend_on_gateway() -> None:
    violations: list[str] = []
    forbidden_names = {"DataServiceGateway", "get_data_service_gateway"}
    for relative_path in RECENT_APPLICATION_SERVICE_FILES:
        path = ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        used_names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        leaked = sorted(used_names & forbidden_names)
        if leaked:
            violations.append(f"{relative_path}: {', '.join(leaked)}")

    assert violations == []


def test_status_application_services_use_narrow_data_ports() -> None:
    violations = [
        relative_path
        for relative_path in STATUS_APPLICATION_SERVICE_FILES
        if "rpg_data.services.status" in _imports(ROOT / relative_path)
    ]

    assert violations == []


def test_media_business_and_workers_use_narrow_data_ports() -> None:
    forbidden = {
        "rpg_data.services.gateway",
        "rpg_data.services.media",
    }
    violations = [
        relative_path
        for relative_path in MEDIA_BUSINESS_FILES
        if _imports(ROOT / relative_path) & forbidden
    ]

    assert violations == []


def test_gateway_lookup_surface_does_not_grow() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in _production_python_files()
        if path.relative_to(ROOT).as_posix() != "rpg_data/services/gateway.py"
        and "get_data_service_gateway(" in path.read_text(encoding="utf-8")
    }

    assert actual - GATEWAY_LOOKUP_ALLOWLIST == set()


def test_whole_gateway_reference_surface_does_not_grow() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in _production_python_files()
        if not path.is_relative_to(ROOT / "rpg_data")
        and "DataServiceGateway" in path.read_text(encoding="utf-8")
    }

    assert actual - WHOLE_GATEWAY_REFERENCE_ALLOWLIST == set()


def test_recent_public_persistence_boundaries_use_data_service_naming() -> None:
    service_types = (
        SessionDataService,
        PlotSchedulingDataService,
        DreamMemoryDataService,
        StoryMemoryDataService,
        StatusDataService,
        MediaDataService,
    )

    assert all(service_type.__name__.endswith("DataService") for service_type in service_types)


def test_legacy_models_module_reexports_canonical_aggregate_types() -> None:
    assert models.Session is Session
    assert models.SessionMessage is SessionMessage
    assert models.SessionDerivationJob is SessionDerivationJob
    assert models.DreamProposal is DreamProposal
    assert models.PersistentMemoryBundle is PersistentMemoryBundle
    assert models.SessionStatusTable is SessionStatusTable
    assert models.StatusTableDocument is StatusTableDocument
    assert models.StatusTableTemplate is StatusTableTemplate
    assert models.MediaJob is MediaJob
    assert models.MediaLibraryAssetBundle is MediaLibraryAssetBundle


def test_media_data_service_does_not_expose_business_policy_entrypoints() -> None:
    forbidden = {
        "apply_background_decision",
        "interrupt_active_jobs",
        "interrupt_background_evaluations",
        "queue_background_evaluation",
    }

    assert forbidden.isdisjoint(vars(MediaDataService))


def test_status_data_service_does_not_expose_business_policy_entrypoints() -> None:
    forbidden = {
        "commit_bootstrap_state",
        "commit_deferred_update",
        "create_story_template",
        "delete_story_template_mount",
        "get_active_scene_table",
        "get_scene_attrs",
        "list_context_tables",
        "runtime_delete_key_value",
        "runtime_set_key_value",
    }

    assert forbidden.isdisjoint(vars(StatusDataService))


def _production_python_files():
    for root_name in PRODUCTION_ROOTS:
        yield from _python_files(ROOT / root_name)


def _python_files(root: Path):
    for path in root.rglob("*.py"):
        if "tests" not in path.parts:
            yield path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported
