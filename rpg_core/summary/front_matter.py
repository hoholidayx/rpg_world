"""Shared YAML front-matter parsing for summary markdown files."""

from __future__ import annotations

import re

import yaml


_FRONT_MATTER_RE = re.compile(
    r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)",
    re.DOTALL,
)


def parse_markdown_front_matter(text: str) -> tuple[dict[str, object], str]:
    """Return parsed YAML front matter and the remaining markdown body.

    Markdown without front matter remains valid. A document that starts a
    front-matter block but never closes it is treated as malformed instead of
    leaking the YAML header into the rendered body.
    """

    match = _FRONT_MATTER_RE.match(text)
    if match is None:
        if text.startswith("---"):
            raise ValueError("unterminated YAML front matter")
        return {}, text

    raw = yaml.safe_load(match.group(1))
    if raw is None:
        front_matter: dict[str, object] = {}
    elif isinstance(raw, dict):
        front_matter = {str(key): value for key, value in raw.items()}
    else:
        raise ValueError("YAML front matter must be a mapping")
    return front_matter, text[match.end() :]
