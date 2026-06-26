"""Legacy scene router placeholder.

Scene endpoints are exposed as session subresources in ``sessions.py``.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/scene", tags=["play-scene"])
