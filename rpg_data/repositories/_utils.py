"""Shared helpers for Peewee repositories."""

from __future__ import annotations

from typing import Any, TypeVar

from peewee import SQL, DoesNotExist, Model

ModelT = TypeVar("ModelT", bound=Model)


def get_or_none(model: type[ModelT], row_id: Any) -> ModelT | None:
    try:
        return model.get_by_id(row_id)
    except DoesNotExist:
        return None


def update_timestamp(model: type[ModelT], row_id: Any) -> ModelT | None:
    updated = (
        model.update(updated_at=SQL("CURRENT_TIMESTAMP"))
        .where(model._meta.primary_key == row_id)
        .execute()
    )
    if not updated:
        return None
    return get_or_none(model, row_id)
