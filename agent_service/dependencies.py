"""FastAPI dependencies for lifespan-owned Agent service resources."""

from __future__ import annotations

from fastapi import HTTPException, Request

from agent_service.runtime import AgentServiceRuntime


def get_agent_service_runtime(request: Request) -> AgentServiceRuntime:
    runtime = getattr(request.app.state, "agent_service_runtime", None)
    if not isinstance(runtime, AgentServiceRuntime):
        raise HTTPException(
            status_code=503,
            detail="Agent service runtime is not available",
        )
    return runtime


__all__ = ["get_agent_service_runtime"]
