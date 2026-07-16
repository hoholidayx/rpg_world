"""Convert the fixed RP assistant protocol into deterministic spoken parts."""

from __future__ import annotations

import re

_RP_TAG_RE = re.compile(
    r"<\s*/?\s*(?:rp-narration|rp-character)(?:\s+[^<>]*?)?\s*>",
    re.IGNORECASE,
)
_BREAK_RE = re.compile(r"(?:\r?\n)+|(?<=[。！？!?；;.!])\s*")
_SPACE_RE = re.compile(r"[\t \f\v]+")


def normalize_spoken_text(content: str) -> str:
    text = _RP_TAG_RE.sub("\n", str(content or ""))
    lines = [_SPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def split_spoken_text(text: str, max_chars: int) -> tuple[str, ...]:
    normalized = str(text or "").strip()
    if not normalized:
        return ()
    limit = max(100, int(max_chars))
    units = [unit.strip() for unit in _BREAK_RE.split(normalized) if unit.strip()]
    parts: list[str] = []
    current = ""
    for unit in units:
        for piece in _split_long_unit(unit, limit):
            candidate = f"{current}\n{piece}".strip() if current else piece
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                parts.append(current)
            current = piece
    if current:
        parts.append(current)
    return tuple(parts)


def _split_long_unit(unit: str, limit: int) -> list[str]:
    if len(unit) <= limit:
        return [unit]
    pieces: list[str] = []
    remaining = unit
    while len(remaining) > limit:
        boundary = remaining.rfind(" ", 0, limit + 1)
        if boundary < limit // 2:
            boundary = limit
        pieces.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces
