"""Legacy chat router placeholder.

Chat endpoints are exposed as session subresources in ``sessions.py``.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["play-chat"])
