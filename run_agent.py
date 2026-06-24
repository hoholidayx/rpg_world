"""Agent service entrypoint."""

from __future__ import annotations

import uvicorn

from agent_service.settings import settings as agent_service_settings


def main() -> None:
    """Start the Agent service process."""
    uvicorn.run(
        "agent_service.main:app",
        host=agent_service_settings.service.host,
        port=agent_service_settings.service.port,
        log_level=agent_service_settings.logging.log_level.lower(),
        reload=agent_service_settings.service.reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
