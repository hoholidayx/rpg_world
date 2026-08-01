"""Deterministic benchmark checks and aggregate metrics."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from tests.rp_model_benchmark.models import RPBenchmarkCase


_INTERNAL_TERMS = (
    "rp_story_outcome",
    "status_table_set_values",
    "status_table_edit_fields",
    "runtime_context",
)


@dataclass(frozen=True)
class DeterministicCheck:
    id: str
    passed: bool
    evidence: str


def evaluate_case_run(
    case: RPBenchmarkCase,
    *,
    final_text: str,
    invocations: Sequence[Mapping[str, object]],
    provider_error: str | None,
) -> tuple[DeterministicCheck, ...]:
    checks: list[DeterministicCheck] = []
    checks.append(DeterministicCheck(
        "provider_completed",
        provider_error is None,
        provider_error or "provider completed",
    ))
    checks.append(DeterministicCheck(
        "final_text_present",
        bool(final_text.strip()),
        f"characters={len(final_text)}",
    ))

    xml_valid = _valid_rp_xml(final_text)
    if case.text.require_rp_xml:
        checks.append(DeterministicCheck(
            "rp_xml_required",
            xml_valid,
            "valid RP XML" if xml_valid else "missing or invalid RP XML",
        ))
    if case.text.forbid_rp_xml:
        contains_xml = "<rp-narration" in final_text or "<rp-character" in final_text
        checks.append(DeterministicCheck(
            "rp_xml_forbidden",
            not contains_xml,
            "RP XML absent" if not contains_xml else "RP XML appeared in OOC output",
        ))

    for index, literal in enumerate(case.text.required_literals):
        checks.append(DeterministicCheck(
            f"required_literal_{index}",
            literal in final_text,
            repr(literal),
        ))
    for index, literal in enumerate(case.text.forbidden_literals):
        checks.append(DeterministicCheck(
            f"forbidden_literal_{index}",
            literal not in final_text,
            repr(literal),
        ))
    for index, pattern in enumerate(case.text.required_regex):
        checks.append(DeterministicCheck(
            f"required_regex_{index}",
            re.search(pattern, final_text, re.MULTILINE) is not None,
            pattern,
        ))
    for index, pattern in enumerate(case.text.forbidden_regex):
        checks.append(DeterministicCheck(
            f"forbidden_regex_{index}",
            re.search(pattern, final_text, re.MULTILINE) is None,
            pattern,
        ))
    if case.text.forbid_internal_terms:
        leaked = [term for term in _INTERNAL_TERMS if term.casefold() in final_text.casefold()]
        checks.append(DeterministicCheck(
            "internal_terms_hidden",
            not leaked,
            f"leaked={leaked}",
        ))

    names = [str(item.get("name", "")) for item in invocations]
    available = [item.value for item in case.tools.available]
    for tool in case.tools.required:
        checks.append(DeterministicCheck(
            f"required_tool_{tool.value}",
            tool.value in names,
            f"actual={names}",
        ))
    for tool in case.tools.forbidden:
        checks.append(DeterministicCheck(
            f"forbidden_tool_{tool.value}",
            tool.value not in names,
            f"actual={names}",
        ))
    checks.append(DeterministicCheck(
        "no_unavailable_tool",
        set(names).issubset(available),
        f"available={available}, actual={names}",
    ))
    if case.tools.exact_sequence is not None:
        expected_sequence = [item.value for item in case.tools.exact_sequence]
        checks.append(DeterministicCheck(
            "exact_tool_sequence",
            names == expected_sequence,
            f"expected={expected_sequence}, actual={names}",
        ))
    for tool_name, expected in case.tools.argument_equals.items():
        invocation = next(
            (item for item in invocations if item.get("name") == tool_name),
            None,
        )
        actual = invocation.get("arguments") if invocation is not None else None
        checks.append(DeterministicCheck(
            f"tool_arguments_{tool_name}",
            isinstance(actual, Mapping) and _mapping_contains(actual, expected),
            f"expectedSubset={expected!r}, actual={actual!r}",
        ))
    return tuple(checks)


def aggregate_metrics(case_runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate quality and repeat consistency per configured Provider."""

    by_provider: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in case_runs:
        by_provider[str(item["providerKey"])].append(item)
    result: dict[str, Any] = {}
    for provider, runs in sorted(by_provider.items()):
        checks = [
            check
            for run in runs
            for check in run.get("deterministicChecks", [])
        ]
        passed = sum(bool(check.get("passed")) for check in checks)
        categories: dict[str, dict[str, int | float]] = {}
        for category in sorted({str(run["category"]) for run in runs}):
            category_runs = [run for run in runs if run["category"] == category]
            categories[category] = _run_metrics(category_runs)
        result[provider] = {
            **_run_metrics(runs),
            "checkCount": len(checks),
            "passedChecks": passed,
            "deterministicCheckRate": round(passed / len(checks), 6) if checks else 0.0,
            "repeatDecisionConsistency": _repeat_consistency(runs),
            "categories": categories,
        }
    return result


def checks_as_dict(checks: Iterable[DeterministicCheck]) -> list[dict[str, object]]:
    return [asdict(item) for item in checks]


def _run_metrics(runs: Sequence[Mapping[str, Any]]) -> dict[str, int | float]:
    total = len(runs)
    passed_runs = sum(
        bool(run.get("deterministicChecks"))
        and all(bool(check.get("passed")) for check in run["deterministicChecks"])
        for run in runs
    )
    provider_errors = sum(bool(run.get("providerError")) for run in runs)
    return {
        "runCount": total,
        "deterministicPassRuns": passed_runs,
        "deterministicPassRate": round(passed_runs / total, 6) if total else 0.0,
        "providerErrors": provider_errors,
    }


def _repeat_consistency(runs: Sequence[Mapping[str, Any]]) -> float:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[str(run["caseId"])].append(run)
    comparable = 0
    consistent = 0
    for values in grouped.values():
        if len(values) < 2:
            continue
        comparable += 1
        signatures = {
            (
                tuple(item.get("toolSequence", [])),
                tuple(
                    check["id"]
                    for check in item.get("deterministicChecks", [])
                    if not check.get("passed")
                ),
            )
            for item in values
        }
        consistent += int(len(signatures) == 1)
    return round(consistent / comparable, 6) if comparable else 1.0


def _valid_rp_xml(text: str) -> bool:
    if not text.strip():
        return False
    try:
        root = ET.fromstring(f"<root>{text}</root>")
    except ET.ParseError:
        return False
    if root.text and root.text.strip():
        return False
    if not list(root):
        return False
    for child in root:
        if child.tag not in {"rp-narration", "rp-character"}:
            return False
        if list(child):
            return False
        if child.tag == "rp-character" and not str(child.attrib.get("name", "")).strip():
            return False
        if child.tail and child.tail.strip():
            return False
    return True


def _mapping_contains(actual: Mapping[str, object], expected: Mapping[str, object]) -> bool:
    for key, expected_value in expected.items():
        if key not in actual:
            return False
        actual_value = actual[key]
        if isinstance(expected_value, Mapping):
            if not isinstance(actual_value, Mapping) or not _mapping_contains(
                actual_value,
                expected_value,
            ):
                return False
        elif actual_value != expected_value:
            return False
    return True


__all__ = [
    "DeterministicCheck",
    "aggregate_metrics",
    "checks_as_dict",
    "evaluate_case_run",
]
