"""Static contracts for the rpg_data registry and persistence boundary."""

from __future__ import annotations

import ast
from pathlib import Path

from rpg_data import models
from rpg_data.model.composer import (
    NarrativeStyle,
    StoryNarrativeStyle,
    StoryQuickReply,
)
from rpg_data.model.memory import DreamProposal, PersistentMemoryBundle
from rpg_data.model.media import MediaJob, MediaLibraryAssetBundle
from rpg_data.model.narrative_outcome import (
    NarrativeOutcomeCreate,
    NarrativeOutcomeRecord,
    NarrativeOutcomeWeights,
)
from rpg_data.model.rp_modules import (
    RPModuleCatalogEntry,
    SessionRPModuleOverride,
    SessionRPModuleSelectionRows,
    StoryRPModule,
)
from rpg_data.model.session import (
    Session,
    SessionDerivationJob,
    SessionHistorySearchHit,
    SessionHistoryTurnWindow,
    SessionMessage,
)
from rpg_data.model.status import (
    SessionStatusTable,
    StatusTableDocument,
    StoryStatusTable,
)
from rpg_data.model.tts import TTSJob, TTSMessageSource
from rpg_data.services.dream_memory import DreamMemoryDataService
from rpg_data.services.media import MediaDataService
from rpg_data.services.message import MessageDataService
from rpg_data.services.narrative_outcome import NarrativeOutcomeDataService
from rpg_data.services.plot_scheduling import PlotSchedulingDataService
from rpg_data.services.rp_modules import RPModuleDataService
from rpg_data.services.session_composer import SessionComposerDataService
from rpg_data.services.session_reference import SessionReferenceDataService
from rpg_data.services.session import SessionDataService
from rpg_data.services.story_memory import StoryMemoryDataService
from rpg_data.services.story_pack import StoryPackDataService
from rpg_data.services.status import StatusDataService
from rpg_data.services.tts import TTSDataService

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOTS = (
    "agent_service",
    "channels",
    "dream_service",
    "llm_client",
    "llm_service",
    "media_service",
    "memory_retrieval",
    "play_api",
    "rpg_core",
    "rpg_data",
    "rpg_media",
    "rpg_memory",
    "rpg_mcp",
    "rpg_tts",
    "tts_service",
)
PRODUCTION_ENTRYPOINTS = (
    "run_telegram.py",
)

FORBIDDEN_DATA_DEPENDENCIES = (
    "agent_service",
    "channels",
    "dream_service",
    "media_service",
    "memory_retrieval",
    "play_api",
    "play_events",
    "rp_memory",
    "rpg_core",
    "rpg_media",
    "rpg_memory",
    "rpg_tts",
    "tts_service",
)

RECENT_APPLICATION_SERVICE_FILES = (
    "rpg_core/session/catalog.py",
    "rpg_core/session/composer.py",
    "rpg_core/session/deletion.py",
    "rpg_core/session/derivation.py",
    "rpg_core/session/reset.py",
    "rpg_core/session/role.py",
    "rpg_core/session/status.py",
    "rpg_core/session/history.py",
    "rpg_core/session/manager.py",
    "rpg_core/session/progress.py",
    "channels/session_reference/service.py",
    "channels/session_reference/runtime.py",
    "rpg_core/rp_modules/application.py",
    "rpg_core/rp_modules/narrative_outcome/ledger.py",
    "rpg_core/rp_modules/plot_scheduler/management.py",
    "rpg_core/rp_modules/plot_scheduler/ledger.py",
    "rpg_core/rp_modules/plot_scheduler/snapshot.py",
    "rpg_memory/dream/application.py",
    "rpg_memory/persistent/store.py",
    "rpg_memory/story/store.py",
    "rpg_memory/story/application.py",
    "rpg_core/scene/status.py",
    "rpg_core/status/context_service.py",
    "rpg_core/status/administration.py",
    "rpg_core/status/manager.py",
    "rpg_core/agent/turn/transaction/commit_plan.py",
    "rpg_media/service.py",
    "rpg_tts/service.py",
)

MEDIA_BUSINESS_FILES = (
    "rpg_media/service.py",
    "rpg_media/source.py",
    "rpg_media/background_agent.py",
    "media_service/worker.py",
)

TTS_BUSINESS_FILES = (
    "rpg_tts/service.py",
    "tts_service/worker.py",
)

STATUS_APPLICATION_SERVICE_FILES = (
    "rpg_core/scene/status.py",
    "rpg_core/session/status.py",
    "rpg_core/status/administration.py",
    "rpg_core/status/context_service.py",
    "rpg_core/status/manager.py",
)

MESSAGE_AND_LEDGER_BUSINESS_FILES = (
    "rpg_core/session/history.py",
    "rpg_core/session/manager.py",
    "rpg_core/session/progress.py",
    "rpg_core/agent/turn/transaction/commit_plan.py",
    "rpg_core/rp_modules/narrative_outcome/ledger.py",
    "rpg_core/rp_modules/plot_scheduler/ledger.py",
    "rpg_core/rp_modules/plot_scheduler/management.py",
)

# Gateway lookup is valid only at process/composition boundaries. Keep the
# complete surface explicit so a data service locator cannot enter business
# objects during unrelated changes.
GATEWAY_LOOKUP_ALLOWLIST = frozenset({
    "agent_service/main.py",
    "dream_service/repository.py",
    "media_service/main.py",
    "play_api/backends/data_manager.py",
    "play_api/routers/plot_scheduling.py",
    "play_api/composition.py",
    "play_api/routers/sessions.py",
    "channels/cli/memory_recall.py",
    "rpg_core/agent/agent.py",
    "rpg_core/context/factory.py",
    "rpg_mcp/composition.py",
    "run_telegram.py",
    "tts_service/main.py",
})

CORE_GATEWAY_LOOKUP_ALLOWLIST = frozenset({
    "rpg_core/agent/agent.py",
    "rpg_core/context/factory.py",
})

# A few pre-boundary services still receive the whole Gateway even though they
# do not perform a global lookup. Freeze that legacy surface independently so a
# new caller cannot bypass the lookup guard through constructor injection.
WHOLE_GATEWAY_REFERENCE_ALLOWLIST = frozenset({
    "media_service/main.py",
    "play_api/backends/data_manager.py",
    "rpg_mcp/composition.py",
    "run_telegram.py",
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


def test_peewee_does_not_escape_rpg_data() -> None:
    violations: list[str] = []
    for path in _production_python_files():
        if path.is_relative_to(ROOT / "rpg_data"):
            continue
        for imported in _imports(path):
            if imported == "peewee" or imported.startswith("peewee."):
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


def test_message_history_and_ledgers_use_narrow_data_ports() -> None:
    forbidden = {
        "rpg_data.services.gateway",
        "rpg_data.services.message",
        "rpg_data.services.narrative_outcome",
        "rpg_data.services.plot_scheduling",
        "rpg_data.services.session",
    }
    violations = [
        relative_path
        for relative_path in MESSAGE_AND_LEDGER_BUSINESS_FILES
        if _imports(ROOT / relative_path) & forbidden
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


def test_tts_business_and_worker_use_narrow_data_ports() -> None:
    forbidden = {
        "rpg_data.services.gateway",
        "rpg_data.services.tts",
    }
    violations = [
        relative_path
        for relative_path in TTS_BUSINESS_FILES
        if _imports(ROOT / relative_path) & forbidden
    ]

    assert violations == []


def test_gateway_lookup_surface_does_not_grow() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in _production_python_files()
        if not path.is_relative_to(ROOT / "rpg_data")
        and _uses_gateway_lookup(path)
    }

    assert actual - GATEWAY_LOOKUP_ALLOWLIST == set()


def test_rpg_core_gateway_lookup_is_limited_to_composition_roots() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in _production_python_files()
        if path.is_relative_to(ROOT / "rpg_core")
        and _uses_gateway_lookup(path)
    }

    assert actual - CORE_GATEWAY_LOOKUP_ALLOWLIST == set()


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
        StoryPackDataService,
        StatusDataService,
        MediaDataService,
        TTSDataService,
        SessionComposerDataService,
        SessionReferenceDataService,
        RPModuleDataService,
        MessageDataService,
        NarrativeOutcomeDataService,
    )

    assert all(service_type.__name__.endswith("DataService") for service_type in service_types)


def test_legacy_models_module_reexports_canonical_aggregate_types() -> None:
    assert models.Session is Session
    assert models.SessionMessage is SessionMessage
    assert models.SessionHistorySearchHit is SessionHistorySearchHit
    assert models.SessionHistoryTurnWindow is SessionHistoryTurnWindow
    assert models.SessionDerivationJob is SessionDerivationJob
    assert models.DreamProposal is DreamProposal
    assert models.PersistentMemoryBundle is PersistentMemoryBundle
    assert models.SessionStatusTable is SessionStatusTable
    assert models.StatusTableDocument is StatusTableDocument
    assert models.StoryStatusTable is StoryStatusTable
    assert models.MediaJob is MediaJob
    assert models.MediaLibraryAssetBundle is MediaLibraryAssetBundle
    assert models.TTSJob is TTSJob
    assert models.TTSMessageSource is TTSMessageSource
    assert models.NarrativeStyle is NarrativeStyle
    assert models.StoryNarrativeStyle is StoryNarrativeStyle
    assert models.StoryQuickReply is StoryQuickReply
    assert models.RPModuleCatalogEntry is RPModuleCatalogEntry
    assert models.StoryRPModule is StoryRPModule
    assert models.SessionRPModuleOverride is SessionRPModuleOverride
    assert models.SessionRPModuleSelectionRows is SessionRPModuleSelectionRows
    assert models.NarrativeOutcomeCreate is NarrativeOutcomeCreate
    assert models.NarrativeOutcomeRecord is NarrativeOutcomeRecord
    assert models.NarrativeOutcomeWeights is NarrativeOutcomeWeights


def test_composer_application_service_uses_narrow_data_port() -> None:
    imports = _imports(ROOT / "rpg_core/session/composer.py")

    assert "rpg_data.services.gateway" not in imports
    assert "rpg_data.services.session_composer" not in imports


def test_rpg_core_does_not_depend_on_channel_packages() -> None:
    violations: list[str] = []
    for path in _python_files(ROOT / "rpg_core"):
        for imported in _imports(path):
            if imported == "channels" or imported.startswith("channels."):
                violations.append(
                    f"{path.relative_to(ROOT)}: {imported}"
                )

    assert violations == []


def test_channel_session_reference_uses_only_narrow_data_ports() -> None:
    forbidden_prefixes = (
        "agent_service",
        "dream_service",
        "llm_client",
        "llm_service",
        "media_service",
        "peewee",
        "play_api",
        "rpg_core.agent",
        "rpg_data.repositories",
        "rpg_data.services",
        "rpg_media",
        "rpg_memory.dream",
        "rpg_tts",
        "tts_service",
    )
    violations: list[str] = []
    reference_root = ROOT / "channels/session_reference"
    for path in _python_files(reference_root):
        for imported in _imports(path):
            imports_other_channel_code = (
                imported == "channels"
                or (
                    imported.startswith("channels.")
                    and imported != "channels.session_reference"
                    and not imported.startswith(
                        "channels.session_reference."
                    )
                )
            )
            if (
                imports_other_channel_code
                or imported.startswith(forbidden_prefixes)
            ):
                violations.append(
                    f"{path.relative_to(ROOT)}: {imported}"
                )

    assert violations == []


def test_play_api_does_not_depend_on_lightweight_channel_reference() -> None:
    violations: list[str] = []
    for path in _python_files(ROOT / "play_api"):
        for imported in _imports(path):
            if (
                imported == "channels.session_reference"
                or imported.startswith("channels.session_reference.")
            ):
                violations.append(
                    f"{path.relative_to(ROOT)}: {imported}"
                )

    assert violations == []


def test_telegram_reference_handlers_do_not_import_persistence_or_source_policy() -> None:
    forbidden_prefixes = (
        "peewee",
        "rpg_data",
        "rpg_memory.persistent.ledger",
        "rpg_core.summary.reader",
    )
    violations: list[str] = []
    for path in _python_files(ROOT / "channels/telegram"):
        for imported in _imports(path):
            if imported.startswith(forbidden_prefixes):
                violations.append(
                    f"{path.relative_to(ROOT)}: {imported}"
                )

    assert violations == []


def test_telegram_handlers_use_the_public_reference_package() -> None:
    violations: list[str] = []
    concrete_types = {
        "SessionReferenceApplicationService",
        "ThreadedSessionReferenceReader",
    }
    for path in _python_files(ROOT / "channels/telegram"):
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        for imported in _imports(path):
            if imported.startswith("channels.session_reference."):
                violations.append(
                    f"{path.relative_to(ROOT)}: {imported}"
                )
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "channels.session_reference"
            ):
                leaked = sorted(
                    alias.name
                    for alias in node.names
                    if alias.name in concrete_types
                )
                if leaked:
                    violations.append(
                        f"{path.relative_to(ROOT)}: "
                        f"{', '.join(leaked)}"
                    )

    assert violations == []


def test_telegram_composition_root_does_not_import_business_runtimes() -> None:
    forbidden_prefixes = (
        "agent_service.main",
        "dream_service",
        "llm_client",
        "llm_service",
        "media_service.main",
        "peewee",
        "rpg_core.agent",
        "rpg_data.repositories",
        "rpg_memory.dream",
        "rpg_media",
        "rpg_tts",
        "tts_service.main",
    )
    path = ROOT / "run_telegram.py"
    violations = [
        imported
        for imported in _imports(path)
        if imported.startswith(forbidden_prefixes)
    ]

    assert violations == []


def test_persistent_reference_policy_uses_only_narrow_data_contracts() -> None:
    forbidden_prefixes = (
        "channels",
        "peewee",
        "play_api",
        "rpg_core",
        "rpg_data.repositories",
        "rpg_data.services",
    )
    path = ROOT / "rpg_memory/persistent/reference.py"
    violations = [
        imported
        for imported in _imports(path)
        if imported.startswith(forbidden_prefixes)
    ]

    assert violations == []


def test_session_reference_data_service_does_not_own_player_policy() -> None:
    source = (
        ROOT / "rpg_data/services/session_reference.py"
    ).read_text(encoding="utf-8")

    assert "SESSION_LIFECYCLE_READY" not in source
    assert "project_context_memories" not in source
    assert "Telegram" not in source


def test_composer_data_services_do_not_expose_business_resolution() -> None:
    assert "resolve_session_style" not in vars(SessionComposerDataService)
    assert "get_turn_mode" not in vars(SessionDataService)
    assert "resolve_session_style" not in vars(SessionDataService)
    repository_source = (
        ROOT / "rpg_data/repositories/session_composer_repo.py"
    ).read_text(encoding="utf-8")
    assert "DEFAULT_TURN_MODES" not in repository_source


def test_rp_module_application_and_registry_do_not_use_gateway() -> None:
    for relative_path in (
        "rpg_core/rp_modules/application.py",
        "rpg_core/rp_modules/registry.py",
    ):
        imports = _imports(ROOT / relative_path)
        assert "rpg_data.services" not in imports
        assert "rpg_data.services.gateway" not in imports


def test_rp_module_data_service_does_not_expose_effective_policy() -> None:
    forbidden = {
        "clear_session_override",
        "mount_story_defaults",
        "resolve_snapshot",
        "set_session_override",
        "set_story_module",
    }

    assert forbidden.isdisjoint(vars(RPModuleDataService))


def test_media_data_service_does_not_expose_business_policy_entrypoints() -> None:
    forbidden = {
        "apply_background_decision",
        "interrupt_active_jobs",
        "interrupt_background_evaluations",
        "queue_background_evaluation",
    }

    assert forbidden.isdisjoint(vars(MediaDataService))


def test_tts_data_service_does_not_expose_business_policy_entrypoints() -> None:
    forbidden = {
        "interrupt_active_jobs",
        "mark_failed",
        "retry_job",
    }

    assert forbidden.isdisjoint(vars(TTSDataService))


def test_status_data_service_does_not_expose_business_policy_entrypoints() -> None:
    forbidden = {
        "commit_bootstrap_state",
        "create_story_template",
        "delete_story_template_mount",
        "get_active_scene_table",
        "get_scene_attrs",
        "list_context_tables",
        "runtime_delete_key_value",
        "runtime_set_key_value",
    }

    assert forbidden.isdisjoint(vars(StatusDataService))


def test_message_data_service_does_not_expose_history_or_candidate_policy() -> None:
    forbidden = {
        "count_story_memory_unprocessed_turns",
        "count_summary_candidate_turns",
        "list_for_agent_context",
        "list_story_memory_unprocessed_turn_groups",
        "list_summary_candidate_turn_groups",
        "list_summary_unprocessed_turn_groups",
    }

    assert forbidden.isdisjoint(vars(MessageDataService))
    assert {"count_distinct_turns", "list_filtered"}.issubset(
        vars(MessageDataService)
    )


def test_narrative_outcome_data_service_does_not_expose_rp_policy() -> None:
    assert "record" not in vars(NarrativeOutcomeDataService)
    source = (ROOT / "rpg_data/services/narrative_outcome.py").read_text(
        encoding="utf-8"
    )

    assert "NarrativeOutcomeSampler" not in source
    assert "NARRATIVE_OUTCOME_DEFINITION_BY_CODE" not in source


def _production_python_files():
    for root_name in PRODUCTION_ROOTS:
        yield from _python_files(ROOT / root_name)
    for relative_path in PRODUCTION_ENTRYPOINTS:
        yield ROOT / relative_path


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


def _uses_gateway_lookup(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {
            "rpg_data.services",
            "rpg_data.services.gateway",
        }:
            if any(
                alias.name == "get_data_service_gateway"
                for alias in node.names
            ):
                return True
        if isinstance(node, ast.Name) and node.id == "get_data_service_gateway":
            return True
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "get_data_service_gateway"
        ):
            return True
    return False
