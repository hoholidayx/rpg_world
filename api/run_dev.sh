#!/usr/bin/env bash
# Start RPG World API (FastAPI) in development mode with auto-reload.
#
# For production / multi-module startup, use the launcher instead:
#   uv run python -m rpg_world.run
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/settings.json'))['port'])")
cd "$SCRIPT_DIR/../.."  # project root
exec uv run uvicorn rpg_world.api.main:app \
  --reload \
  --reload-dir rpg_world \
  --reload-exclude '*/node_modules/*' \
  --host 127.0.0.1 \
  --port "$PORT"
