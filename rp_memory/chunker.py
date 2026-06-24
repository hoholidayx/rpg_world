"""File text extraction and chunking for vector memory indexing.

Default strategy: one file = one chunk, preserving front matter metadata
(e.g. title/time/location from markdown summaries).  A sub-chunking
fallback is available for files that exceed the size threshold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chunk:
    """A text fragment ready for embedding, with its source metadata."""

    text: str
    metadata: dict[str, object] = field(default_factory=dict)


_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_LIST_ITEM_RE = re.compile(r"^\s+-\s+(.+)")

# Supported file extensions for text extraction — used consistently
# by FileTextExtractor and Chunker.
_EXT_MARKDOWN = ".md"
_EXT_JSON = ".json"
_EXT_JSONL = ".jsonl"
_EXT_CSV = ".csv"
_KNOWN_TEXT_EXTS = frozenset({_EXT_MARKDOWN, _EXT_JSON, _EXT_JSONL, _EXT_CSV})


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Extract YAML-ish front matter from markdown (handles ``key: value`` and
    ``key:\n  - item`` list syntax)."""
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    cur_key: str | None = None
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            cur_key = k.strip()
            meta[cur_key] = v.strip()
        else:
            lm = _LIST_ITEM_RE.match(line)
            if lm and cur_key is not None:
                existing = meta.get(cur_key, "")
                val = lm.group(1).strip().strip('"')
                if existing:
                    meta[cur_key] = f'{existing}, {val}'
                else:
                    meta[cur_key] = val
    return meta, text[m.end():]


class FileTextExtractor:
    """Extract plain text + metadata from various file formats."""

    @staticmethod
    def extract(path: Path) -> tuple[str, dict[str, str]]:
        ext = path.suffix.lower()
        if ext == _EXT_MARKDOWN:
            return FileTextExtractor._md(path)
        if ext == _EXT_JSON:
            return FileTextExtractor._json(path)
        if ext == _EXT_JSONL:
            return FileTextExtractor._jsonl(path)
        if ext == _EXT_CSV:
            return FileTextExtractor._csv(path)
        return FileTextExtractor._raw(path)

    # ── format-specific ──────────────────────────────────────

    @staticmethod
    def _raw(path: Path) -> tuple[str, dict[str, str]]:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), {}
        except OSError:
            return "", {}

    @staticmethod
    def _md(path: Path) -> tuple[str, dict[str, str]]:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "", {}
        meta, body = _parse_front_matter(raw)
        return body.strip(), meta

    @staticmethod
    def _json(path: Path) -> tuple[str, dict[str, str]]:
        try:
            import json
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return "", {}
        return _flatten_json(data), {}

    @staticmethod
    def _jsonl(path: Path) -> tuple[str, dict[str, str]]:
        import json
        lines: list[str] = []
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        for key in ("content", "text", "message", "name", "title"):
                            if key in obj and isinstance(obj[key], str):
                                lines.append(obj[key])
                                break
                        else:
                            lines.append(_flatten_json(obj))
                    else:
                        lines.append(str(obj))
                except (ValueError, TypeError):
                    lines.append(line)
        except OSError:
            pass
        return "\n".join(lines), {}

    @staticmethod
    def _csv(path: Path) -> tuple[str, dict[str, str]]:
        import csv
        import io
        lines: list[str] = []
        try:
            raw = path.read_text(encoding="utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(raw))
            for row in reader:
                for h in reader.fieldnames or []:
                    val = (row.get(h) or "").strip()
                    if val:
                        lines.append(f"{h}: {val}")
        except OSError:
            pass
        return "\n".join(lines), {}


def _flatten_json(obj: object, prefix: str = "") -> str:
    """Recursively flatten JSON into human-readable lines."""
    parts: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}{k}" if prefix else k
            if isinstance(v, (dict, list)):
                parts.append(f"{key}:")
                parts.append(_flatten_json(v, prefix=key + "."))
            elif isinstance(v, str) and v.strip():
                parts.append(f"{key}: {v}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            parts.append(f"[{i}]:")
            parts.append(_flatten_json(item, prefix=f"{prefix}[{i}]."))
    return "\n".join(parts)


class Chunker:
    """Split extracted text into embedding-ready chunks.

    Default: one file = one chunk.  When text exceeds *max_file_chars*,
    it is split at paragraph boundaries into overlapping sub-chunks.
    """

    def __init__(self, max_file_chars: int = 2000, overlap: int = 64) -> None:
        self.max_file_chars = max_file_chars
        self.overlap = overlap

    def chunk_file(
        self,
        text: str,
        file_path: str,
        front_matter: dict[str, str] | None = None,
    ) -> list[Chunk]:
        meta: dict[str, object] = {
            "source": _source_id(file_path),
            "file": file_path,
            "chunk_idx": 0,
        }
        if front_matter:
            meta.update(front_matter)

        if len(text) <= self.max_file_chars:
            return [Chunk(text=text, metadata=meta)]

        paragraphs = re.split(r"\n\s*\n", text)
        sub_chunks: list[str] = []
        current = ""
        for para in paragraphs:
            candidate = f"{current}\n\n{para}" if current else para
            if len(candidate) > self.max_file_chars and current:
                sub_chunks.append(current)
                overlap = current[-self.overlap:] if self.overlap > 0 else ""
                current = f"{overlap}\n\n{para}" if overlap else para
            else:
                current = candidate
        if current.strip():
            sub_chunks.append(current)

        result: list[Chunk] = []
        for idx, text_ in enumerate(sub_chunks):
            m = dict(meta)
            m["chunk_idx"] = idx
            result.append(Chunk(text=text_.strip(), metadata=m))
        return result


def _source_id(file_path: str) -> str:
    """Derive a source identifier from the file path (parent dir name)."""
    p = Path(file_path)
    return p.parent.name or p.stem
