from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _python_files(*roots: str):
    for root in roots:
        for path in (ROOT / root).rglob("*.py"):
            if "tests" in path.parts:
                continue
            yield path


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
