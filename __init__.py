from pathlib import Path

# Absolute path to the rpg_world/ package root directory.
# All relative paths (workspace data, character, lorebook) are resolved
# against this directory.  Modules MUST import this constant instead of
# computing the package root from __file__.parent… chains.
PACKAGE_ROOT = Path(__file__).resolve().parent
