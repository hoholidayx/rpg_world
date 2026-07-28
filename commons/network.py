"""Shared network-boundary validation helpers."""

from __future__ import annotations

import ipaddress


def loopback_host(
    value: object,
    *,
    setting_name: str,
    default: str = "127.0.0.1",
) -> str:
    """Return a normalized explicit loopback bind or fail closed."""

    host = str(value or default).strip()
    if host.casefold() == "localhost":
        return "localhost"

    normalized = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise ValueError(
            f"{setting_name} must be localhost or a loopback IP address"
        ) from exc
    if not address.is_loopback:
        raise ValueError(
            f"{setting_name} must be localhost or a loopback IP address"
        )
    return normalized
