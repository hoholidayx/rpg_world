"""Shared Jinja rendering helpers for context-related templates."""

from __future__ import annotations

from jinja2 import Environment, FileSystemLoader

from rpg_world.rpg_core.settings import settings


_JINJA_ENV: Environment | None = None


def render_jinja_template(template_name: str, **context: object) -> str:
    """Render a Jinja template from ``rpg_core/jinja``."""
    global _JINJA_ENV
    if _JINJA_ENV is None:
        _JINJA_ENV = Environment(
            loader=FileSystemLoader(str(settings.jinja_dir)),
            autoescape=False,
        )
    return _JINJA_ENV.get_template(template_name).render(**context).strip()
