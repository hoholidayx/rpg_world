"""Static architecture contracts for the canonical Python module layout."""

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
    ("rpg_core.agent.protocol", "AgentStreamEvent"),
    ("rpg_core.agent.telemetry", "TurnStats"),
    ("rpg_core.agent.turn.runner", "AgentReply"),
    ("rpg_core.agent.command", "CommandDispatcher"),
    ("rpg_core.agent.runtime.derivation", "SessionDerivationPreparationError"),
    ("rpg_core.agent.sub_agents", "StatusSubAgentRecordStatus"),
    ("rpg_core.agent.runtime.main_llm", "MainLLMSelectionService"),
    ("rpg_core.agent.turn.models", "TurnRequest"),
    ("rpg_core.context", "RPGContext"),
    ("rpg_core.context.models", "Message"),
    ("rpg_core.character", "CharacterManager"),
    ("rpg_core.lorebook", "LorebookManager"),
    ("rpg_core.session", "SessionManager"),
    ("rpg_core.status", "StatusManager"),
    ("rpg_core.tooling", "BaseTool"),
    ("rpg_core.tooling", "ToolRegistry"),
)

REMOVED_COMPATIBILITY_MODULES = {
    "llm_service.base_provider",
    "rpg_core.agent.agent_types",
    "rpg_core.agent.derivation_service",
    "rpg_core.agent.loop",
    "rpg_core.agent.sub_agents.memory.candidates",
    "rpg_core.agent.tools.base",
    "rpg_core.agent.tools.registry",
    "rpg_core.context.rpg_context",
    "rpg_core.main_llm",
    "rpg_core.rp_module_constants",
    "rpg_core.session.turns",
    "rpg_core.turns",
}

REMOVED_COMPATIBILITY_FILES = tuple(
    ROOT / f"{module_name.replace('.', '/')}.py"
    for module_name in sorted(REMOVED_COMPATIBILITY_MODULES)
)

PRODUCTION_ROOTS = (
    ROOT / "agent_service",
    ROOT / "channels",
    ROOT / "dream_service",
    ROOT / "llm_client",
    ROOT / "llm_service",
    ROOT / "media_service",
    ROOT / "play_api",
    ROOT / "rp_memory",
    ROOT / "rpg_core",
    ROOT / "rpg_data",
    ROOT / "rpg_media",
    ROOT / "rpg_tts",
    ROOT / "tts_service",
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


def test_removed_compatibility_modules_do_not_exist() -> None:
    present = [
        str(path.relative_to(ROOT))
        for path in REMOVED_COMPATIBILITY_FILES
        if path.exists()
    ]

    assert present == []


def test_production_has_no_import_only_facade_modules() -> None:
    violations = [
        str(path.relative_to(ROOT))
        for path in _python_files(*PRODUCTION_ROOTS)
        if path.name != "__init__.py" and _is_import_only_module(path)
    ]

    assert violations == []


def test_production_code_does_not_import_removed_compatibility_modules() -> None:
    violations: list[str] = []
    for path in _python_files(*PRODUCTION_ROOTS):
        for imported in _imports(path):
            if imported in REMOVED_COMPATIBILITY_MODULES:
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


def _is_import_only_module(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if all(
                isinstance(target, ast.Name) and target.id == "__all__"
                for target in targets
            ):
                continue
        return False
    return True
