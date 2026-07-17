"""Pinned LongMemEval-S download, validation, and turn-level conversion."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

import httpx


LONGMEMEVAL_REVISION = "98d7416c24c778c2fee6e6f3006e7a073259d48f"
LONGMEMEVAL_FILENAME = "longmemeval_s_cleaned.json"
LONGMEMEVAL_URL = (
    "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/"
    f"{LONGMEMEVAL_REVISION}/{LONGMEMEVAL_FILENAME}"
)
LONGMEMEVAL_SHA256 = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
LONGMEMEVAL_SIZE = 277_383_467
LONGMEMEVAL_MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
LONGMEMEVAL_LICENSE = "MIT"
LONGMEMEVAL_LICENSE_URL = (
    "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/blob/"
    f"{LONGMEMEVAL_REVISION}/README.md"
)
LONGMEMEVAL_RECORDS = 500
CONVERTER_VERSION = 1


@dataclass(frozen=True)
class DatasetManifest:
    dataset: str
    revision: str
    source_url: str
    sha256: str
    size: int
    max_download_bytes: int
    license: str
    license_url: str
    converter_version: int
    evidence_granularity: str


MANIFEST = DatasetManifest(
    dataset="LongMemEval-S cleaned",
    revision=LONGMEMEVAL_REVISION,
    source_url=LONGMEMEVAL_URL,
    sha256=LONGMEMEVAL_SHA256,
    size=LONGMEMEVAL_SIZE,
    max_download_bytes=LONGMEMEVAL_MAX_DOWNLOAD_BYTES,
    license=LONGMEMEVAL_LICENSE,
    license_url=LONGMEMEVAL_LICENSE_URL,
    converter_version=CONVERTER_VERSION,
    evidence_granularity="turn",
)


def prepare_longmemeval(cache_dir: Path, *, force: bool = False) -> dict[str, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw_path = cache_dir / f"longmemeval-s.{LONGMEMEVAL_REVISION[:8]}.json"
    output_path = cache_dir / "longmemeval-s.full.jsonl"
    manifest_path = cache_dir / "manifest.json"
    if force or not _valid_download(raw_path):
        _download(LONGMEMEVAL_URL, raw_path)
    if not force and _valid_prepared(output_path, manifest_path):
        return {"raw": raw_path, "full": output_path, "manifest": manifest_path}
    record_count, unscored_count = convert_longmemeval(raw_path, output_path)
    payload = asdict(MANIFEST)
    payload["records"] = record_count
    payload["unscored_missing_has_answer"] = unscored_count
    payload["converted"] = {
        output_path.name: {
            "sha256": _sha256(output_path),
            "size": output_path.stat().st_size,
        }
    }
    _atomic_write(manifest_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return {"raw": raw_path, "full": output_path, "manifest": manifest_path}


def convert_longmemeval(raw_path: Path, output_path: Path) -> tuple[int, int]:
    _validate_integrity(raw_path)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    count = 0
    unscored = 0
    question_ids: set[str] = set()
    try:
        with temporary.open("w", encoding="utf-8") as output:
            for item in _iter_json_array(raw_path):
                converted, scored = _convert_item(item)
                question_id = str(converted["sample_id"])
                if question_id in question_ids:
                    raise ValueError(f"LongMemEval-S has duplicate question ID: {question_id}")
                question_ids.add(question_id)
                output.write(json.dumps(converted, ensure_ascii=False, sort_keys=True) + "\n")
                count += 1
                if not scored:
                    unscored += 1
        if count != LONGMEMEVAL_RECORDS:
            raise ValueError(
                f"LongMemEval-S record count mismatch: {count} != {LONGMEMEVAL_RECORDS}"
            )
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return count, unscored


def _convert_item(item: object) -> tuple[dict[str, object], bool]:
    if not isinstance(item, dict):
        raise ValueError("LongMemEval-S record must be an object")
    question_id = _required_text(item, "question_id")
    question = _required_text(item, "question")
    sessions = item.get("haystack_sessions")
    session_ids = item.get("haystack_session_ids")
    dates = item.get("haystack_dates")
    if not isinstance(sessions, list) or not isinstance(session_ids, list):
        raise ValueError(f"LongMemEval-S {question_id} has malformed sessions")
    if len(sessions) != len(session_ids):
        raise ValueError(f"LongMemEval-S {question_id} session IDs are misaligned")
    if not isinstance(dates, list) or len(dates) != len(sessions):
        raise ValueError(f"LongMemEval-S {question_id} session dates are misaligned")

    documents: list[dict[str, str]] = []
    evidence: list[str] = []
    seen_ids: set[str] = set()
    for session_index, (session_id_value, date_value, turns) in enumerate(
        zip(session_ids, dates, sessions, strict=True),
        start=1,
    ):
        session_id = str(session_id_value or f"session-{session_index}")
        if not isinstance(turns, list):
            raise ValueError(f"LongMemEval-S {question_id}/{session_id} turns are malformed")
        for turn_index, turn in enumerate(turns, start=1):
            if not isinstance(turn, dict):
                raise ValueError(f"LongMemEval-S {question_id}/{session_id} turn is malformed")
            content = " ".join(str(turn.get("content", "") or "").split())
            role = " ".join(str(turn.get("role", "") or "").split())
            if not content:
                continue
            # The cleaned upstream artifact can repeat the same session ID in one
            # haystack. Keep the source ID readable while making each occurrence
            # independently addressable and deterministic.
            evidence_id = f"{session_id}:s{session_index}:t{turn_index}"
            if evidence_id in seen_ids:
                raise ValueError(f"LongMemEval-S {question_id} has duplicate evidence IDs")
            seen_ids.add(evidence_id)
            documents.append({
                "id": evidence_id,
                "text": f"{role}: {content}" if role else content,
                "session": session_id,
                "date": str(date_value or ""),
            })
            if turn.get("has_answer") is True:
                evidence.append(evidence_id)
    if not documents:
        raise ValueError(f"LongMemEval-S {question_id} contains no usable turns")
    converted = {
        "sample_id": question_id,
        "documents": documents,
        "questions": [{
            "id": question_id,
            "question": question,
            "answer": str(item.get("answer", "") or ""),
            "evidence": evidence,
            "category": str(item.get("question_type", "unknown") or "unknown"),
            "scene_time": str(item.get("question_date", "") or ""),
        }],
    }
    return converted, bool(evidence)


def _required_text(item: dict[str, object], key: str) -> str:
    value = " ".join(str(item.get(key, "") or "").split())
    if not value:
        raise ValueError(f"LongMemEval-S record has empty {key}")
    return value


def _iter_json_array(path: Path, *, chunk_size: int = 1024 * 1024) -> Iterator[object]:
    """Decode a large top-level JSON array without loading the whole file."""
    decoder = json.JSONDecoder()
    buffer = ""
    started = False
    finished = False
    with path.open("r", encoding="utf-8") as source:
        while True:
            chunk = source.read(chunk_size)
            eof = not chunk
            buffer += chunk
            offset = 0
            while True:
                while offset < len(buffer) and buffer[offset].isspace():
                    offset += 1
                if not started:
                    if offset >= len(buffer):
                        break
                    if buffer[offset] != "[":
                        raise ValueError("LongMemEval-S root must be a JSON array")
                    started = True
                    offset += 1
                    continue
                while offset < len(buffer) and (
                    buffer[offset].isspace() or buffer[offset] == ","
                ):
                    offset += 1
                if offset < len(buffer) and buffer[offset] == "]":
                    finished = True
                    offset += 1
                    break
                if offset >= len(buffer):
                    break
                try:
                    value, end = decoder.raw_decode(buffer, offset)
                except json.JSONDecodeError:
                    break
                yield value
                offset = end
            buffer = buffer[offset:]
            if finished:
                if buffer.strip():
                    raise ValueError("LongMemEval-S has trailing data")
                return
            if eof:
                break
    raise ValueError("LongMemEval-S JSON array is incomplete")


def _download(url: str, destination: Path, *, attempts: int = 3) -> None:
    if LONGMEMEVAL_SIZE > LONGMEMEVAL_MAX_DOWNLOAD_BYTES:
        raise ValueError("LongMemEval-S expected size exceeds configured safety limit")
    last_error: Exception | None = None
    for attempt in range(1, max(1, int(attempts)) + 1):
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.part"
        )
        try:
            _download_once(url, temporary, max_bytes=LONGMEMEVAL_MAX_DOWNLOAD_BYTES)
            _validate_integrity(temporary)
            os.replace(temporary, destination)
            return
        except Exception as exc:
            last_error = exc
            if attempt < max(1, int(attempts)):
                time.sleep(0.5 * attempt)
        finally:
            temporary.unlink(missing_ok=True)
    raise RuntimeError(f"LongMemEval-S download failed after {attempts} attempts") from last_error


def _download_once(url: str, temporary: Path, *, max_bytes: int) -> None:
    downloaded = 0
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(180.0, connect=20.0),
        headers={"User-Agent": "rpg-world-memory-benchmark/1"},
    ) as client:
        with client.stream("GET", url) as response, temporary.open("wb") as output:
            response.raise_for_status()
            declared = response.headers.get("content-length")
            if declared and int(declared) > max_bytes:
                raise ValueError("LongMemEval-S response exceeds download safety limit")
            for chunk in response.iter_bytes(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > max_bytes:
                    raise ValueError("LongMemEval-S download exceeded safety limit")
                output.write(chunk)


def _validate_integrity(path: Path) -> None:
    if path.stat().st_size != LONGMEMEVAL_SIZE:
        raise ValueError(
            f"LongMemEval-S size mismatch: {path.stat().st_size} != {LONGMEMEVAL_SIZE}"
        )
    digest = _sha256(path)
    if digest != LONGMEMEVAL_SHA256:
        raise ValueError(f"LongMemEval-S SHA-256 mismatch: {digest}")


def _valid_download(path: Path) -> bool:
    try:
        return (
            path.is_file()
            and path.stat().st_size == LONGMEMEVAL_SIZE
            and _sha256(path) == LONGMEMEVAL_SHA256
        )
    except OSError:
        return False


def _valid_prepared(output_path: Path, manifest_path: Path) -> bool:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        converted = payload.get("converted", {}).get(output_path.name, {})
        return (
            payload.get("revision") == LONGMEMEVAL_REVISION
            and payload.get("sha256") == LONGMEMEVAL_SHA256
            and payload.get("converter_version") == CONVERTER_VERSION
            and payload.get("records") == LONGMEMEVAL_RECORDS
            and output_path.is_file()
            and output_path.stat().st_size == converted.get("size")
            and _sha256(output_path) == converted.get("sha256")
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
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
