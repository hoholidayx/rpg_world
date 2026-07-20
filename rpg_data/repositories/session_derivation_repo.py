"""Persistence for asynchronous session-history derivation jobs."""

from __future__ import annotations

import uuid

from peewee import Database, SQL

from rpg_data.model import session as models
from rpg_data.repositories.records import SessionDerivationJobRecord, bind_database


class SessionDerivationRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def create(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        requested_title: str = "",
    ) -> models.SessionDerivationJob:
        row = SessionDerivationJobRecord.create(
            id=f"sd_{uuid.uuid4().hex}",
            source_session=source_session_id,
            branch_turn_id=int(branch_turn_id),
            requested_title=str(requested_title),
        )
        return _to_job(row)

    def get(self, job_id: str) -> models.SessionDerivationJob | None:
        row = SessionDerivationJobRecord.get_or_none(
            SessionDerivationJobRecord.id == str(job_id)
        )
        return _to_job(row) if row is not None else None

    def list_by_status(self, *statuses: str) -> list[models.SessionDerivationJob]:
        normalized = tuple(str(status) for status in statuses)
        query = SessionDerivationJobRecord.select()
        if normalized:
            query = query.where(SessionDerivationJobRecord.status.in_(normalized))
        rows = query.order_by(
            SessionDerivationJobRecord.created_at,
            SessionDerivationJobRecord.id,
        )
        return [_to_job(row) for row in rows]

    def has_active_for_source(self, source_session_id: str) -> bool:
        return (
            SessionDerivationJobRecord.select()
            .where(
                (SessionDerivationJobRecord.source_session == str(source_session_id))
                & SessionDerivationJobRecord.status.in_((
                    models.SESSION_DERIVATION_JOB_STATUS_QUEUED,
                    models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
                ))
            )
            .exists()
        )

    def has_active_for_target(self, target_session_id: str) -> bool:
        return (
            SessionDerivationJobRecord.select()
            .where(
                (SessionDerivationJobRecord.target_session_id == str(target_session_id))
                & SessionDerivationJobRecord.status.in_((
                    models.SESSION_DERIVATION_JOB_STATUS_QUEUED,
                    models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
                ))
            )
            .exists()
        )

    def update_if_status(
        self,
        job_id: str,
        expected_status: str,
        update: models.SessionDerivationJobUpdate,
    ) -> models.SessionDerivationJob | None:
        return self._update(job_id, update, expected_status=expected_status)

    def update(
        self,
        job_id: str,
        update: models.SessionDerivationJobUpdate,
    ) -> models.SessionDerivationJob | None:
        return self._update(job_id, update, expected_status=None)

    def _update(
        self,
        job_id: str,
        update: models.SessionDerivationJobUpdate,
        *,
        expected_status: str | None,
    ) -> models.SessionDerivationJob | None:
        values: dict[object, object] = {
            SessionDerivationJobRecord.version: SessionDerivationJobRecord.version + 1,
            SessionDerivationJobRecord.updated_at: SQL("CURRENT_TIMESTAMP"),
        }
        if update.target_session_id is not None:
            values[SessionDerivationJobRecord.target_session_id] = update.target_session_id
        if update.status is not None:
            if update.status not in models.SESSION_DERIVATION_JOB_STATUSES:
                raise ValueError(f"Unsupported derivation status: {update.status}")
            values[SessionDerivationJobRecord.status] = update.status
        if update.stage is not None:
            if update.stage not in models.SESSION_DERIVATION_STAGES:
                raise ValueError(f"Unsupported derivation stage: {update.stage}")
            values[SessionDerivationJobRecord.stage] = update.stage
        if update.error_code is not None:
            values[SessionDerivationJobRecord.error_code] = str(update.error_code)
        if update.error_message is not None:
            values[SessionDerivationJobRecord.error_message] = str(update.error_message)
        if update.write_context_usage:
            values[SessionDerivationJobRecord.context_used_tokens] = update.context_used_tokens
            values[SessionDerivationJobRecord.context_limit] = update.context_limit
        if update.context_threshold_exceeded is not None:
            values[SessionDerivationJobRecord.context_threshold_exceeded] = bool(
                update.context_threshold_exceeded
            )
        if update.mark_started:
            values[SessionDerivationJobRecord.started_at] = SQL(
                "COALESCE(started_at, CURRENT_TIMESTAMP)"
            )
        if update.mark_finished:
            values[SessionDerivationJobRecord.finished_at] = SQL("CURRENT_TIMESTAMP")
        predicate = SessionDerivationJobRecord.id == str(job_id)
        if expected_status is not None:
            predicate &= SessionDerivationJobRecord.status == str(expected_status)
        updated = SessionDerivationJobRecord.update(values).where(predicate).execute()
        return self.get(job_id) if updated else None


def _to_job(row: SessionDerivationJobRecord) -> models.SessionDerivationJob:
    return models.SessionDerivationJob(
        id=str(row.id),
        source_session_id=str(row.source_session_id),
        target_session_id=(
            str(row.target_session_id) if row.target_session_id is not None else None
        ),
        branch_turn_id=int(row.branch_turn_id),
        requested_title=str(row.requested_title or ""),
        status=str(row.status),
        stage=str(row.stage),
        error_code=str(row.error_code or ""),
        error_message=str(row.error_message or ""),
        context_used_tokens=(
            int(row.context_used_tokens)
            if row.context_used_tokens is not None
            else None
        ),
        context_limit=int(row.context_limit) if row.context_limit is not None else None,
        context_threshold_exceeded=bool(row.context_threshold_exceeded),
        started_at=str(row.started_at or ""),
        finished_at=str(row.finished_at or ""),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )
