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
    )
    violations: list[str] = []
    for path in _python_files("play_api", "channels"):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)}: {marker}")

    assert violations == []


def test_business_processes_only_use_public_llm_client_contract() -> None:
    forbidden = (
        "from llm_service",
        "import llm_service",
        "from openai",
        "import llama_cpp",
    )
    violations: list[str] = []
    for path in _python_files(
        "rpg_core",
        "rp_memory",
        "agent_service",
        "play_api",
        "channels",
        "rpg_media",
        "media_service",
    ):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)}: {marker}")

    assert violations == []


def test_llm_service_does_not_import_business_runtimes() -> None:
    forbidden = (
        "from rpg_core",
        "from rp_memory",
        "from rpg_media",
        "from rpg_data",
        "from agent_service",
        "from media_service",
    )
    violations: list[str] = []
    for path in _python_files("llm_service"):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)}: {marker}")
    assert violations == []


def test_llm_client_does_not_import_server_or_provider_implementations() -> None:
    forbidden = (
        "from llm_service",
        "import llm_service",
        "from openai",
        "import llama_cpp",
    )
    violations: list[str] = []
    for path in _python_files("llm_client"):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)}: {marker}")
    assert violations == []


def test_llama_subprocess_protocol_is_removed() -> None:
    assert not (ROOT / "llm_service/client.py").exists()
    assert not (ROOT / "llm_service/server.py").exists()
    assert not (ROOT / "llm_service/protocol.py").exists()


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
