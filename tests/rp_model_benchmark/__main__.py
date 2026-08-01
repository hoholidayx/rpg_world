"""CLI for the story-neutral RP model benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import random
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from llm_client.auth import resolve_llm_service_token
from llm_client.keys import AGENT_MAIN_BIZ_KEY
from llm_client.manager import LLMClientManager
from tests.rp_model_benchmark.loader import (
    DEFAULT_DATASET_PATH,
    RPBenchmarkInputError,
    load_dataset,
    select_cases,
)
from tests.rp_model_benchmark.reporting import BenchmarkRunWriter
from tests.rp_model_benchmark.review import (
    RPBenchmarkReviewError,
    finalize_review,
)
from tests.rp_model_benchmark.runner import ProviderCallRecord, run_case


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "finalize":
        try:
            report = finalize_review(args.run_dir)
        except RPBenchmarkReviewError as exc:
            parser.error(str(exc))
        print(json.dumps({
            "qualityStatus": report["qualityStatus"],
            "finalReport": str(Path(args.run_dir).resolve() / "final-report.md"),
        }, ensure_ascii=False, indent=2))
        return 0
    try:
        return asyncio.run(_run(args))
    except RPBenchmarkInputError as exc:
        parser.error(str(exc))
    return 2


async def _run(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset)
    selected_cases = list(select_cases(dataset, args.suite))
    random.Random(args.seed).shuffle(selected_cases)
    repeats = args.repeats if args.repeats is not None else (
        1 if args.suite == "smoke" else 2
    )
    if repeats < 1:
        raise RPBenchmarkInputError("--repeats must be positive")
    providers = _provider_args(args.provider)
    manager = await LLMClientManager.aconfigure(
        base_url=args.llm_service_url,
        token=resolve_llm_service_token(),
        request_timeout_ms=args.timeout_seconds * 1000,
        stream_timeout_ms=max(300, args.timeout_seconds) * 1000,
    )
    try:
        await manager.client.health()
        catalog = await manager.get_catalog(AGENT_MAIN_BIZ_KEY, refresh=True)
        selected_provider_keys = providers or [catalog.default_provider_key]
        if len(selected_provider_keys) != len(set(selected_provider_keys)):
            raise RPBenchmarkInputError("provider keys must be unique")
        available = {item.provider_key for item in catalog.options}
        unknown = sorted(set(selected_provider_keys).difference(available))
        if unknown:
            raise RPBenchmarkInputError(
                f"agent.main provider keys are unavailable: {unknown}"
            )
        provider_handles = {
            key: await manager.get_provider(AGENT_MAIN_BIZ_KEY, provider_key=key)
            for key in selected_provider_keys
        }
        writer = BenchmarkRunWriter(
            report_root=args.report_dir,
            dataset=dataset,
            metadata={
                "suite": args.suite,
                "repeats": repeats,
                "stableOrderSeed": args.seed,
                "providers": [
                    {
                        "providerKey": key,
                        "model": provider_handles[key].get_default_model(),
                    }
                    for key in selected_provider_keys
                ],
                "datasetPath": str(Path(args.dataset).resolve()),
                "datasetSha256": _sha256(Path(args.dataset)),
                "gitCommit": _git("rev-parse", "HEAD"),
                "gitDirty": bool(_git("status", "--short")),
                "python": sys.version,
                "platform": platform.platform(),
                "llmServiceUrl": args.llm_service_url,
                "requestTimeoutSeconds": args.timeout_seconds,
            },
        )
        calls: list[ProviderCallRecord] = []
        results = []
        total = len(selected_cases) * len(selected_provider_keys) * repeats
        completed = 0
        for case in selected_cases:
            for provider_key in selected_provider_keys:
                provider = provider_handles[provider_key]
                for repeat in range(1, repeats + 1):
                    result = await run_case(
                        provider,
                        provider_key=provider_key,
                        case=case,
                        repeat=repeat,
                        calls=calls,
                    )
                    results.append(result)
                    completed += 1
                    print(
                        f"[{completed}/{total}] {provider_key} {case.id} repeat={repeat}",
                        flush=True,
                    )
        report = writer.finalize(
            dataset=dataset,
            selected_cases=selected_cases,
            calls=calls,
            case_runs=results,
        )
        print(json.dumps({
            "runId": writer.run_id,
            "report": str(writer.run_dir / "report.md"),
            "reviewTemplate": str(writer.run_dir / "codex-review-template.json"),
            "providerErrorCount": len(report["providerErrors"]),
        }, ensure_ascii=False, indent=2))
        return 2 if report["providerErrors"] else 0
    finally:
        await LLMClientManager.areset()


def _provider_args(values: Sequence[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or ():
        result.extend(item.strip() for item in value.split(",") if item.strip())
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Story-neutral RP model capability benchmark",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    run.add_argument("--suite", choices=("smoke", "full"), default="smoke")
    run.add_argument(
        "--provider",
        action="append",
        help="agent.main provider key; repeat or comma-separate for comparison",
    )
    run.add_argument("--repeats", type=int, default=None)
    run.add_argument("--seed", type=int, default=20260801)
    run.add_argument("--timeout-seconds", type=int, default=120)
    run.add_argument(
        "--report-dir",
        type=Path,
        default=Path("data/benchmarks/rp-model"),
    )
    run.add_argument(
        "--llm-service-url",
        default=os.environ.get(
            "RPG_WORLD_LLM_SERVICE_URL",
            "http://127.0.0.1:8012/llm/v1",
        ),
    )
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--run-dir", required=True)
    return parser


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=_REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
