"""Legacy commands router placeholder.

Command endpoints are exposed as session subresources in ``sessions.py``.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/commands", tags=["play-commands"])
