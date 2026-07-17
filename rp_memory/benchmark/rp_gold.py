"""Loader for project-maintained RP retrieval gold cases."""

from __future__ import annotations

import json
from pathlib import Path


def load_rp_gold() -> list[dict[str, object]]:
    path = Path(__file__).with_name("rp_gold.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("samples"), list):
        raise ValueError("unsupported RP gold case format")
    samples = payload["samples"]
    question_ids: set[str] = set()
    for sample in samples:
        documents = sample.get("documents", [])
        questions = sample.get("questions", [])
        evidence_ids = {str(document.get("id", "")) for document in documents}
        for question in questions:
            question_id = str(question.get("id", ""))
            if not question_id or question_id in question_ids:
                raise ValueError("RP gold question ids must be non-empty and unique")
            question_ids.add(question_id)
            referenced = {
                str(value)
                for key in ("gold_evidence", "forbidden_evidence")
                for value in question.get(key, [])
            }
            if not referenced.issubset(evidence_ids):
                raise ValueError(f"RP gold question references unknown evidence: {question_id}")
            gold = list(question.get("gold_evidence", []))
            if not gold and not bool(question.get("no_answer", False)):
                raise ValueError(
                    f"RP gold question without evidence must declare no_answer: {question_id}"
                )
    return samples
