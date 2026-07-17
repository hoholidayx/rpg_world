"""CLI for the fixed RP Memory benchmark workflow."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

from loguru import logger

from rp_memory.benchmark.datasets import SUPPORTED_DATASETS, parse_datasets
from rp_memory.benchmark.suite import (
    default_options,
    execute_suite,
    prepare_selected_datasets,
)


def main() -> None:
    _quiet_runtime_logs()
    parser = argparse.ArgumentParser(description="RP Memory recall benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)

    suite_parser = subparsers.add_parser(
        "suite",
        help="run selected datasets across offline and available configured paths",
    )
    suite_parser.add_argument(
        "--record",
        action="store_true",
        help="write a successful full run as an independent tracked Markdown report",
    )
    suite_parser.add_argument(
        "--datasets",
        action="append",
        metavar="NAME[,NAME...]",
        help=(
            "datasets to run; repeat or comma-separate values; default: locomo,rp-gold; "
            f"supported: {','.join(SUPPORTED_DATASETS)}"
        ),
    )
    suite_parser.add_argument(
        "--offline-only",
        action="store_true",
        help="do not contact LLM Service; dataset download may still occur if cache is absent",
    )
    suite_parser.add_argument(
        "--locomo-tier",
        choices=("smoke", "full"),
        default="full",
        help="development override; --record requires full",
    )

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="download, validate, and convert selected pinned dataset artifacts",
    )
    prepare_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/benchmarks"),
    )
    prepare_parser.add_argument(
        "--datasets",
        action="append",
        metavar="NAME[,NAME...]",
        help=(
            "datasets to prepare; default: locomo,rp-gold; "
            f"supported: {','.join(SUPPORTED_DATASETS)}"
        ),
    )
    prepare_parser.add_argument("--force", action="store_true")

    args = parser.parse_args()
    try:
        selected = parse_datasets(args.datasets)
    except ValueError as exc:
        parser.error(str(exc))
    if args.command == "prepare":
        prepared = prepare_selected_datasets(
            args.data_dir.resolve(),
            selected,
            force=args.force,
        )
        print(json.dumps({
            dataset: {key: str(value.resolve()) for key, value in paths.items()}
            for dataset, paths in prepared.items()
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return

    command = "uv run python -m rp_memory.benchmark " + shlex.join(sys.argv[1:])
    execution = execute_suite(
        default_options(
            command=command,
            datasets=selected,
            offline_only=args.offline_only,
            record=args.record,
            locomo_tier=args.locomo_tier,
        )
    )
    summary = {
        "runId": execution.result.environment.run_id,
        "successful": execution.result.successful,
        "report": str(execution.report_path),
        "historyRecorded": execution.history_recorded,
        "trackedReport": (
            str(execution.tracked_report_path)
            if execution.tracked_report_path is not None
            else None
        ),
        "paths": {
            result.path_id: result.status.value
            for result in execution.result.paths
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if not execution.result.successful:
        raise SystemExit(1)


def _quiet_runtime_logs() -> None:
    logger.disable("rp_memory")
    logging.getLogger("jieba").setLevel(logging.WARNING)
    try:
        import jieba

        jieba.setLogLevel(logging.WARNING)
    except ImportError:
        pass


if __name__ == "__main__":
    main()
