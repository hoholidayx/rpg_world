"""Static architecture contracts for the ``rpg_core`` package layout."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "rpg_core"


PUBLIC_EXPORTS = (
    ("rpg_core.agent.agent", "RPGGameAgent"),
    ("rpg_core.agent.manager", "AgentManager"),
    ("rpg_core.agent.agent_types", "AgentStreamEvent"),
    ("rpg_core.agent.agent_types", "TurnStats"),
    ("rpg_core.agent.loop", "AgentReply"),
    ("rpg_core.agent.command", "CommandDispatcher"),
    ("rpg_core.agent.derivation_service", "SessionDerivationPreparationError"),
    ("rpg_core.agent.sub_agents", "StatusSubAgentRecordStatus"),
    ("rpg_core.main_llm", "MainLLMSelectionService"),
    ("rpg_core.turns", "TurnRequest"),
    ("rpg_core.context", "RPGContext"),
    ("rpg_core.context.rpg_context", "Message"),
    ("rpg_core.character", "CharacterManager"),
    ("rpg_core.lorebook", "LorebookManager"),
    ("rpg_core.session", "SessionManager"),
    ("rpg_core.status", "StatusManager"),
    ("rpg_core.tooling", "BaseTool"),
    ("rpg_core.tooling", "ToolRegistry"),
)


@pytest.mark.parametrize(("module_name", "export_name"), PUBLIC_EXPORTS)
def test_stable_public_imports(module_name: str, export_name: str) -> None:
    module = importlib.import_module(module_name)
    assert getattr(module, export_name) is not None


def test_domain_packages_do_not_depend_on_agent_runtime_or_subagents() -> None:
    forbidden = (
        "rpg_core.agent.runtime",
        "rpg_core.agent.sub_agents",
    )
    violations: list[str] = []
    for path in _domain_python_files():
        for imported in _imports(path):
            if imported.startswith(forbidden):
                violations.append(f"{path.relative_to(ROOT)}: {imported}")

    assert violations == []


def test_shared_tooling_does_not_depend_on_agent_runtime() -> None:
    violations: list[str] = []
    for path in _python_files(CORE / "tooling"):
        for imported in _imports(path):
            if imported == "rpg_core.agent" or imported.startswith("rpg_core.agent."):
                violations.append(f"{path.relative_to(ROOT)}: {imported}")

    assert violations == []


def test_canonical_agent_modules_do_not_import_compatibility_facades() -> None:
    compatibility_modules = {
        "rpg_core.agent.agent_types",
        "rpg_core.agent.loop",
        "rpg_core.main_llm",
        "rpg_core.turns",
    }
    canonical_roots = (
        CORE / "agent" / "runtime",
        CORE / "agent" / "mailbox",
        CORE / "agent" / "command",
        CORE / "agent" / "turn" / "hooks",
        CORE / "agent" / "turn" / "transaction",
        CORE / "agent" / "sub_agents" / "memory",
        CORE / "agent" / "sub_agents" / "status",
    )
    violations: list[str] = []
    for path in _python_files(*canonical_roots):
        for imported in _imports(path):
            if imported in compatibility_modules:
                violations.append(f"{path.relative_to(ROOT)}: {imported}")

    assert violations == []


def test_public_package_imports_do_not_initialize_runtime_or_database() -> None:
    script = """
import importlib

for module_name in (
    'rpg_core.agent',
    'rpg_core.character',
    'rpg_core.lorebook',
    'rpg_core.session',
    'rpg_core.context',
):
    importlib.import_module(module_name)

from llm_client.manager import LLMClientManager
from rpg_data.services.gateway import _GATEWAYS

assert LLMClientManager._instance is None
assert _GATEWAYS == {}
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _domain_python_files():
    roots = (
        CORE / "character.py",
        CORE / "character",
        CORE / "context",
        CORE / "lorebook.py",
        CORE / "lorebook",
        CORE / "rp_modules",
        CORE / "scene",
        CORE / "session",
        CORE / "status",
        CORE / "summary",
    )
    yield from _python_files(*roots)


def _python_files(*roots: Path):
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            yield root
        elif root.is_dir():
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
