"""Loader and strict validation for project-maintained RP retrieval gold cases."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


RP_GOLD_CATEGORIES = (
    "state_and_item_location",
    "latest_fact",
    "epistemic_status",
    "attempt_vs_success",
    "commitment_vs_completion",
    "player_vs_npc",
    "alias_and_pronoun",
    "relative_and_scene_time",
    "multi_evidence",
    "no_answer",
    "story_session_isolation",
    "scene_status_narrative_boundary",
)
RP_GOLD_QUESTION_COUNT = 60
RP_GOLD_QUESTIONS_PER_CATEGORY = 5


def load_rp_gold() -> list[dict[str, object]]:
    path = Path(__file__).with_name("rp_gold.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 2 or not isinstance(payload.get("samples"), list):
        raise ValueError("unsupported RP gold case format")
    samples = payload["samples"]
    question_ids: set[str] = set()
    category_counts: Counter[str] = Counter()
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("RP gold sample must be an object")
        documents = sample.get("documents", [])
        questions = sample.get("questions", [])
        if not isinstance(documents, list) or not isinstance(questions, list):
            raise ValueError("RP gold documents/questions must be lists")
        evidence_ids = {str(document.get("id", "")) for document in documents}
        if "" in evidence_ids or len(evidence_ids) != len(documents):
            raise ValueError("RP gold evidence IDs must be non-empty and unique per sample")
        for question in questions:
            if not isinstance(question, dict):
                raise ValueError("RP gold question must be an object")
            question_id = str(question.get("id", ""))
            if not question_id or question_id in question_ids:
                raise ValueError("RP gold question IDs must be non-empty and globally unique")
            question_ids.add(question_id)
            category = str(question.get("category", ""))
            if category not in RP_GOLD_CATEGORIES:
                raise ValueError(f"RP gold question has unsupported category: {question_id}")
            category_counts[category] += 1
            if not str(question.get("rationale", "")).strip():
                raise ValueError(f"RP gold question must explain its rationale: {question_id}")
            if not str(question.get("review_notes", "")).strip():
                raise ValueError(f"RP gold question must include review notes: {question_id}")
            referenced = {
                str(value)
                for key in ("gold_evidence", "forbidden_evidence")
                for value in question.get(key, [])
            }
            if not referenced.issubset(evidence_ids):
                raise ValueError(f"RP gold question references unknown evidence: {question_id}")
            gold = list(question.get("gold_evidence", []))
            no_answer = bool(question.get("no_answer", False))
            if not gold and not no_answer:
                raise ValueError(
                    f"RP gold question without evidence must declare no_answer: {question_id}"
                )
            if gold and no_answer:
                raise ValueError(f"RP gold no-answer question must not have gold: {question_id}")
            if category == "no_answer" and not no_answer:
                raise ValueError(f"RP gold no_answer category must declare no_answer: {question_id}")
    if len(question_ids) != RP_GOLD_QUESTION_COUNT:
        raise ValueError(
            f"RP gold must contain {RP_GOLD_QUESTION_COUNT} questions, got {len(question_ids)}"
        )
    expected = Counter({
        category: RP_GOLD_QUESTIONS_PER_CATEGORY
        for category in RP_GOLD_CATEGORIES
    })
    if category_counts != expected:
        raise ValueError(
            f"RP gold category coverage mismatch: {dict(sorted(category_counts.items()))}"
        )
    return samples
