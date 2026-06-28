from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _python_files(*roots: str):
    for root in roots:
        for path in (ROOT / root).rglob("*.py"):
            if "tests" in path.parts:
                continue
            yield path


def _rpg_core_runtime_files():
    yield from _python_files("rpg_core")


def test_non_agent_processes_do_not_import_agent_runtime() -> None:
    forbidden = (
        "from rpg_core.agent.manager import AgentManager",
        "from rpg_core.agent.agent import RPGGameAgent",
        "configure_llama_client_from_runtime_config",
    )
    violations: list[str] = []
    for path in _python_files("play_api", "channels"):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)}: {marker}")

    assert violations == []


def test_only_agent_service_configures_llama_client_from_runtime_config() -> None:
    violations: list[str] = []
    for path in _python_files("agent_service", "play_api", "channels"):
        text = path.read_text(encoding="utf-8")
        if "configure_llama_client_from_runtime_config" in text and not str(path).endswith("agent_service/main.py"):
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []


def test_rpg_core_runtime_does_not_use_legacy_workspace_fallbacks() -> None:
    forbidden = (
        "require_workspace",
        "default_workspace_name",
        "resolve_api_workspace",
    )
    violations: list[str] = []
    for path in _rpg_core_runtime_files():
        if path.relative_to(ROOT).as_posix() == "rpg_core/utils/path_utils.py":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)}: {marker}")

    assert violations == []


def test_rpg_core_runtime_keeps_business_data_out_of_direct_files() -> None:
    allowed = {
        "rpg_core/settings.py",
        "rpg_core/context/builder.py",
        "rpg_core/context/factory.py",
        "rpg_core/agent/sub_agents/memory_sub_agent.py",
        "rpg_core/agent/tools/file_tools.py",
    }
    allowed_prefixes = (
        "rpg_core/summary/",
    )
    forbidden_markers = (
        ".md",
        ".json",
        ".csv",
        "load_json",
        "save_json",
        "delete_file",
        "BaseManager",
    )
    violations: list[str] = []
    for path in _rpg_core_runtime_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in allowed or any(rel.startswith(prefix) for prefix in allowed_prefixes):
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text:
                violations.append(f"{rel}: {marker}")

    assert violations == []
