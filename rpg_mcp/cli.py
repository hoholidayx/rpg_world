"""Command-line entry point for the mode-scoped RPG World MCP server."""

from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path
from typing import Sequence

from rpg_mcp.server import build_server


def _loopback_host(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized.lower() == "localhost":
        return normalized
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "streamable HTTP host must be a loopback IP or localhost"
        ) from exc
    if not address.is_loopback:
        raise argparse.ArgumentTypeError(
            "streamable HTTP host must be loopback-only"
        )
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rpg-world-mcp",
        description=(
            "Portable Story design and RPG World synchronization MCP server."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("design", "runtime", "all"),
        default="design",
    )
    parser.add_argument(
        "--project-root",
        help=(
            "DesignProject root. Required for design/all; optional in runtime."
        ),
    )
    parser.add_argument(
        "--db-path",
        help="Optional RPG World SQLite path for runtime/all mode.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    parser.add_argument(
        "--host",
        type=_loopback_host,
        default="127.0.0.1",
    )
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.mode in {"design", "all"} and not args.project_root:
        parser.error("--project-root is required in design/all mode")
    if args.transport == "streamable-http":
        _loopback_host(args.host)
    bundle = build_server(
        mode=args.mode,
        project_root=(
            Path(args.project_root).expanduser()
            if args.project_root is not None
            else None
        ),
        db_path=(
            Path(args.db_path).expanduser()
            if args.db_path is not None
            else None
        ),
        host=args.host,
        port=args.port,
    )
    try:
        bundle.server.run(transport=args.transport)
    finally:
        bundle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
