"""Pinned LoCoMo download, validation, and deterministic conversion."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

LOCOMO_COMMIT = "3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376"
LOCOMO_URL = (
    "https://raw.githubusercontent.com/snap-research/locomo/"
    f"{LOCOMO_COMMIT}/data/locomo10.json"
)
LOCOMO_SHA256 = "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"
LOCOMO_SIZE = 2_805_274
LOCOMO_LICENSE = "CC BY-NC 4.0"
LOCOMO_LICENSE_URL = (
    "https://raw.githubusercontent.com/snap-research/locomo/"
    f"{LOCOMO_COMMIT}/LICENSE.txt"
)
CONVERTER_VERSION = 1


@dataclass(frozen=True)
class DatasetManifest:
    dataset: str
    commit: str
    source_url: str
    sha256: str
    size: int
    license: str
    license_url: str
    converter_version: int


MANIFEST = DatasetManifest(
    dataset="LoCoMo",
    commit=LOCOMO_COMMIT,
    source_url=LOCOMO_URL,
    sha256=LOCOMO_SHA256,
    size=LOCOMO_SIZE,
    license=LOCOMO_LICENSE,
    license_url=LOCOMO_LICENSE_URL,
    converter_version=CONVERTER_VERSION,
)


def prepare_locomo(cache_dir: Path, *, force: bool = False) -> dict[str, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw_path = cache_dir / f"locomo10.{LOCOMO_COMMIT[:8]}.json"
    if force or not _valid_download(raw_path):
        _download(LOCOMO_URL, raw_path)
    validate_locomo(raw_path)
    full_path = cache_dir / "locomo.full.jsonl"
    smoke_path = cache_dir / "locomo.smoke.jsonl"
    convert_locomo(raw_path, full_path, smoke=False)
    convert_locomo(raw_path, smoke_path, smoke=True)
    manifest_path = cache_dir / "manifest.json"
    payload = asdict(MANIFEST)
    payload["converted"] = {
        full_path.name: _sha256(full_path),
        smoke_path.name: _sha256(smoke_path),
    }
    _atomic_write(manifest_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return {
        "raw": raw_path,
        "full": full_path,
        "smoke": smoke_path,
        "manifest": manifest_path,
    }


def validate_locomo(path: Path) -> list[dict[str, object]]:
    if path.stat().st_size != LOCOMO_SIZE:
        raise ValueError(f"LoCoMo size mismatch: {path.stat().st_size} != {LOCOMO_SIZE}")
    digest = _sha256(path)
    if digest != LOCOMO_SHA256:
        raise ValueError(f"LoCoMo SHA-256 mismatch: {digest}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 10:
        raise ValueError("LoCoMo must contain exactly 10 conversation records")
    qa_count = 0
    for sample in payload:
        if not isinstance(sample, dict) or not isinstance(sample.get("conversation"), dict):
            raise ValueError("LoCoMo conversation record is malformed")
        qa = sample.get("qa")
        if not isinstance(qa, list):
            raise ValueError("LoCoMo QA record is malformed")
        qa_count += len(qa)
    if qa_count != 1_986:
        raise ValueError(f"LoCoMo QA count mismatch: {qa_count}")
    return payload


def convert_locomo(raw_path: Path, output_path: Path, *, smoke: bool) -> None:
    samples = validate_locomo(raw_path)
    selected = samples[:1] if smoke else samples
    lines = [json.dumps(_convert_sample(sample), ensure_ascii=False, sort_keys=True) for sample in selected]
    _atomic_write(output_path, "\n".join(lines) + "\n")


def _convert_sample(sample: dict[str, object]) -> dict[str, object]:
    conversation = sample["conversation"]
    assert isinstance(conversation, dict)
    documents: list[dict[str, str]] = []
    for session_key in sorted(
        (key for key in conversation if re.fullmatch(r"session_\d+", str(key))),
        key=lambda key: int(str(key).split("_")[1]),
    ):
        turns = conversation.get(session_key)
        if not isinstance(turns, list):
            continue
        date = str(conversation.get(f"{session_key}_date_time", "") or "")
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            evidence_id = str(turn.get("dia_id", "") or "")
            text = " ".join(str(turn.get("text", "") or "").split())
            speaker = " ".join(str(turn.get("speaker", "") or "").split())
            if evidence_id and text:
                documents.append({
                    "id": evidence_id,
                    "text": f"{speaker}: {text}" if speaker else text,
                    "session": str(session_key),
                    "date": date,
                })
    questions: list[dict[str, object]] = []
    qa = sample.get("qa")
    assert isinstance(qa, list)
    for index, item in enumerate(qa):
        if not isinstance(item, dict):
            raise ValueError("LoCoMo QA item is malformed")
        questions.append({
            "id": f"{sample.get('sample_id', '')}:q{index + 1}",
            "question": str(item.get("question", "") or ""),
            "answer": str(item.get("answer", "") or ""),
            "evidence": [str(value) for value in item.get("evidence", [])],
            "category": item.get("category"),
        })
    return {
        "sample_id": str(sample.get("sample_id", "") or ""),
        "documents": documents,
        "questions": questions,
    }


def _download(url: str, destination: Path, *, attempts: int = 3) -> None:
    """Download with bounded retries and publish only a fully verified file."""
    last_error: Exception | None = None
    for attempt in range(1, max(1, int(attempts)) + 1):
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.part"
        )
        try:
            _download_once(url, temporary)
            if temporary.stat().st_size != LOCOMO_SIZE or _sha256(temporary) != LOCOMO_SHA256:
                raise ValueError("downloaded LoCoMo artifact failed size or SHA-256 validation")
            os.replace(temporary, destination)
            return
        except Exception as exc:
            last_error = exc
            if attempt < max(1, int(attempts)):
                time.sleep(0.25 * attempt)
        finally:
            temporary.unlink(missing_ok=True)
    raise RuntimeError(f"LoCoMo download failed after {attempts} attempts") from last_error


def _download_once(url: str, temporary: Path) -> None:
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(45.0, connect=15.0),
        headers={"User-Agent": "rpg-world-memory-benchmark/1"},
    ) as client:
        with client.stream("GET", url) as response, temporary.open("wb") as output:
            response.raise_for_status()
            for chunk in response.iter_bytes(1024 * 1024):
                output.write(chunk)


def _valid_download(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size == LOCOMO_SIZE and _sha256(path) == LOCOMO_SHA256
    except OSError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
