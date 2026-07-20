from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_service import derivation_worker as worker_module
from agent_service import main as service_main
from agent_service.derivation_notifications import SessionDerivationNotification
from agent_service.derivation_worker import SessionDerivationWorker
from rpg_core.agent.runtime.derivation import SessionDerivationPreparationError
from rpg_core.session.deletion import (
    SessionDeleteResult,
    SessionRuntimeCleanupStatus,
)
from rpg_core.session.derivation import (
    SessionDerivationSeedResult,
    SessionDerivationSourceBusyError,
    SessionDerivationStatus,
)
from rpg_data import models


def _job(
    *,
    job_id: str = "job_1",
    status: str = models.SESSION_DERIVATION_JOB_STATUS_QUEUED,
    target_session_id: str | None = None,
) -> models.SessionDerivationJob:
    return models.SessionDerivationJob(
        id=job_id,
        source_session_id="source_1",
        branch_turn_id=3,
        requested_title="Fork",
        target_session_id=target_session_id,
        status=status,
        stage=status,
        created_at="2026-07-17T00:00:00Z",
        updated_at="2026-07-17T00:00:00Z",
    )


class FakeDerivationService:
    def __init__(self, *jobs: models.SessionDerivationJob) -> None:
        self.jobs = {job.id: job for job in jobs}
        self.fail_calls: list[tuple[str, str, str]] = []

    def create_job(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        requested_title: str = "",
    ) -> models.SessionDerivationJob:
        if source_session_id == "missing":
            raise FileNotFoundError("Ready source session not found: missing")
        if any(
            row.source_session_id == source_session_id
            and row.status in {
                models.SESSION_DERIVATION_JOB_STATUS_QUEUED,
                models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
            }
            for row in self.jobs.values()
        ):
            raise SessionDerivationSourceBusyError(source_session_id)
        job = models.SessionDerivationJob(
            id=f"job_{len(self.jobs) + 1}",
            source_session_id=source_session_id,
            branch_turn_id=branch_turn_id,
            requested_title=requested_title,
            created_at="2026-07-17T00:00:00Z",
            updated_at="2026-07-17T00:00:00Z",
        )
        self.jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> models.SessionDerivationJob | None:
        return self.jobs.get(job_id)

    def list_jobs(
        self,
        *statuses: SessionDerivationStatus,
    ) -> list[models.SessionDerivationJob]:
        if not statuses:
            return list(self.jobs.values())
        values = {status.value for status in statuses}
        return [job for job in self.jobs.values() if job.status in values]

    def start_job(self, job_id: str) -> models.SessionDerivationJob:
        job = replace(
            self.jobs[job_id],
            status=models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
            stage="snapshotting",
        )
        self.jobs[job_id] = job
        return job

    def set_target(self, job_id: str, target_session_id: str) -> models.SessionDerivationJob:
        job = replace(
            self.jobs[job_id],
            target_session_id=target_session_id,
            stage="rebuilding_status",
        )
        self.jobs[job_id] = job
        return job

    def complete_job(self, job_id: str) -> models.SessionDerivationJob:
        job = replace(
            self.jobs[job_id],
            status=models.SESSION_DERIVATION_JOB_STATUS_READY,
            stage="ready",
            finished_at="2026-07-17T00:01:00Z",
        )
        self.jobs[job_id] = job
        return job

    def fail_job(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.SessionDerivationJob:
        self.fail_calls.append((job_id, error_code, error_message))
        job = replace(
            self.jobs[job_id],
            status=models.SESSION_DERIVATION_JOB_STATUS_FAILED,
            stage="failed",
            error_code=error_code,
            error_message=error_message,
        )
        self.jobs[job_id] = job
        return job

    def interrupt_job(self, job_id: str) -> models.SessionDerivationJob:
        job = self.jobs[job_id]
        updated = replace(
            job,
            status=models.SESSION_DERIVATION_JOB_STATUS_INTERRUPTED,
            stage="interrupted",
            error_code="DERIVATION_WORKER_RESTARTED",
        )
        self.jobs[job.id] = updated
        return updated


class FakeSessionDeletion:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def delete_provisioning_target(
        self,
        job_id: str,
        session_id: str,
    ) -> SessionDeleteResult:
        self.deleted.append((job_id, session_id))
        return SessionDeleteResult(
            session_id=session_id,
            runtime_cleanup=SessionRuntimeCleanupStatus.DELETED,
        )


class FakeNotificationSink:
    def __init__(self) -> None:
        self.notifications: list[SessionDerivationNotification] = []

    async def publish(self, notification: SessionDerivationNotification) -> None:
        self.notifications.append(notification)


class FailingNotificationSink:
    async def publish(self, notification: SessionDerivationNotification) -> None:
        del notification
        raise RuntimeError("notification unavailable")


class FakeSourceAgent:
    def __init__(self, service: FakeDerivationService) -> None:
        self.service = service
        self.materialized: list[str] = []

    async def materialize_derivation(self, job_id: str) -> SessionDerivationSeedResult:
        self.materialized.append(job_id)
        job = self.service.set_target(job_id, "target_1")
        return SessionDerivationSeedResult(
            job=job,
            session=models.Session(
                id="target_1",
                workspace_id="ws",
                story_id=1,
                lifecycle=models.SESSION_LIFECYCLE_PROVISIONING,
            ),
            copied_message_count=6,
        )


class FakeTargetAgent:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.prepared: list[str] = []

    async def prepare_derivation_target(self, job_id: str) -> None:
        self.prepared.append(job_id)
        if self.failure is not None:
            raise self.failure


class FakeWorkerAgentManager:
    agents: dict[str, object] = {}
    dropped: list[str] = []
    drop_error: Exception | None = None

    @classmethod
    def get_or_create(cls, session_id: str) -> object:
        return cls.agents[session_id]

    @classmethod
    async def drop_session(cls, session_id: str) -> None:
        cls.dropped.append(session_id)
        if cls.drop_error is not None:
            raise cls.drop_error


@pytest.mark.asyncio
async def test_derivation_worker_completes_ready_job(monkeypatch) -> None:
    queued = _job()
    service = FakeDerivationService(queued)
    source = FakeSourceAgent(service)
    target = FakeTargetAgent()
    FakeWorkerAgentManager.agents = {"source_1": source, "target_1": target}
    FakeWorkerAgentManager.dropped = []
    FakeWorkerAgentManager.drop_error = None
    monkeypatch.setattr(worker_module, "AgentManager", FakeWorkerAgentManager)
    notifications = FakeNotificationSink()
    gateway = SimpleNamespace(
        session_derivations=service,
        session_deletion=FakeSessionDeletion(),
    )

    worker = SessionDerivationWorker(
        gateway=gateway,
        notification_sink=notifications,
        derivation_service=service,
        deletion_service=gateway.session_deletion,
    )
    await worker._execute(queued)

    completed = service.get_job(queued.id)
    assert completed is not None
    assert completed.status == models.SESSION_DERIVATION_JOB_STATUS_READY
    assert completed.target_session_id == "target_1"
    assert source.materialized == [queued.id]
    assert target.prepared == [queued.id]
    assert len(notifications.notifications) == 1
    assert notifications.notifications[0].status == "ready"


@pytest.mark.asyncio
async def test_derivation_notification_failure_does_not_change_ready_job(
    monkeypatch,
) -> None:
    queued = _job()
    service = FakeDerivationService(queued)
    FakeWorkerAgentManager.agents = {
        "source_1": FakeSourceAgent(service),
        "target_1": FakeTargetAgent(),
    }
    FakeWorkerAgentManager.dropped = []
    FakeWorkerAgentManager.drop_error = None
    monkeypatch.setattr(worker_module, "AgentManager", FakeWorkerAgentManager)
    worker = SessionDerivationWorker(
        gateway=SimpleNamespace(
            session_derivations=service,
            session_deletion=FakeSessionDeletion(),
        ),
        notification_sink=FailingNotificationSink(),
        derivation_service=service,
        deletion_service=FakeSessionDeletion(),
    )

    assert await worker._execute(queued) is True
    completed = service.get_job(queued.id)
    assert completed is not None
    assert completed.status == models.SESSION_DERIVATION_JOB_STATUS_READY


@pytest.mark.asyncio
async def test_derivation_worker_cleans_target_and_fails_when_prepare_fails(monkeypatch) -> None:
    queued = _job()
    service = FakeDerivationService(queued)
    source = FakeSourceAgent(service)
    target = FakeTargetAgent(
        failure=SessionDerivationPreparationError(
            "DERIVATION_SUMMARY_FAILED",
            "summary failed",
        )
    )
    FakeWorkerAgentManager.agents = {"source_1": source, "target_1": target}
    FakeWorkerAgentManager.dropped = []
    FakeWorkerAgentManager.drop_error = None
    monkeypatch.setattr(worker_module, "AgentManager", FakeWorkerAgentManager)
    deletion = FakeSessionDeletion()
    gateway = SimpleNamespace(
        session_derivations=service,
        session_deletion=deletion,
    )

    await SessionDerivationWorker(
        gateway=gateway,
        derivation_service=service,
        deletion_service=deletion,
    )._execute(queued)

    failed = service.get_job(queued.id)
    assert failed is not None
    assert failed.status == models.SESSION_DERIVATION_JOB_STATUS_FAILED
    assert failed.error_code == "DERIVATION_SUMMARY_FAILED"
    assert FakeWorkerAgentManager.dropped == ["target_1"]
    assert deletion.deleted == [(queued.id, "target_1")]


@pytest.mark.asyncio
async def test_derivation_worker_keeps_job_running_when_runtime_close_fails(
    monkeypatch,
) -> None:
    queued = _job()
    service = FakeDerivationService(queued)
    source = FakeSourceAgent(service)
    target = FakeTargetAgent(failure=RuntimeError("prepare failed"))
    FakeWorkerAgentManager.agents = {"source_1": source, "target_1": target}
    FakeWorkerAgentManager.dropped = []
    FakeWorkerAgentManager.drop_error = RuntimeError("runtime close failed")
    monkeypatch.setattr(worker_module, "AgentManager", FakeWorkerAgentManager)
    deletion = FakeSessionDeletion()
    notifications = FakeNotificationSink()
    gateway = SimpleNamespace(
        session_derivations=service,
        session_deletion=deletion,
    )

    worker = SessionDerivationWorker(
        gateway=gateway,
        notification_sink=notifications,
        derivation_service=service,
        deletion_service=deletion,
    )
    try:
        progressed = await worker._execute(queued)
    finally:
        FakeWorkerAgentManager.drop_error = None

    assert progressed is False
    assert worker._stale_recovery_pending is True
    current = service.get_job(queued.id)
    assert current is not None
    assert current.status == models.SESSION_DERIVATION_JOB_STATUS_RUNNING
    assert deletion.deleted == []
    assert service.fail_calls == []
    assert notifications.notifications == []

    assert await worker.interrupt_stale_jobs() is True
    current = service.get_job(queued.id)
    assert current is not None
    assert current.status == models.SESSION_DERIVATION_JOB_STATUS_INTERRUPTED
    assert deletion.deleted == [(queued.id, "target_1")]
    assert [item.status for item in notifications.notifications] == ["interrupted"]


@pytest.mark.asyncio
async def test_derivation_worker_interrupts_stale_running_jobs(monkeypatch) -> None:
    running = _job(
        status=models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
        target_session_id="target_1",
    )
    service = FakeDerivationService(running)
    FakeWorkerAgentManager.agents = {}
    FakeWorkerAgentManager.dropped = []
    FakeWorkerAgentManager.drop_error = None
    monkeypatch.setattr(worker_module, "AgentManager", FakeWorkerAgentManager)
    deletion = FakeSessionDeletion()
    notifications = FakeNotificationSink()
    gateway = SimpleNamespace(
        session_derivations=service,
        session_deletion=deletion,
    )

    worker = SessionDerivationWorker(
        gateway=gateway,
        notification_sink=notifications,
        derivation_service=service,
        deletion_service=deletion,
    )
    await worker.start()
    await worker.stop()

    interrupted = service.get_job(running.id)
    assert interrupted is not None
    assert interrupted.status == models.SESSION_DERIVATION_JOB_STATUS_INTERRUPTED
    assert interrupted.error_code == "DERIVATION_WORKER_RESTARTED"
    assert FakeWorkerAgentManager.dropped == ["target_1"]
    assert deletion.deleted == [(running.id, "target_1")]
    assert [item.status for item in notifications.notifications] == ["interrupted"]


@pytest.mark.asyncio
async def test_derivation_worker_recovers_from_list_and_claim_errors(monkeypatch) -> None:
    class FlakyDerivationService(FakeDerivationService):
        def __init__(self, job: models.SessionDerivationJob) -> None:
            super().__init__(job)
            self.queued_list_failures = 1
            self.claim_failures = 1
            self.completed = asyncio.Event()

        def list_jobs(
            self,
            *statuses: SessionDerivationStatus,
        ) -> list[models.SessionDerivationJob]:
            if statuses == (SessionDerivationStatus.QUEUED,) and self.queued_list_failures:
                self.queued_list_failures -= 1
                raise RuntimeError("temporary list failure")
            return super().list_jobs(*statuses)

        def start_job(self, job_id: str) -> models.SessionDerivationJob:
            if self.claim_failures:
                self.claim_failures -= 1
                raise RuntimeError("temporary claim failure")
            return super().start_job(job_id)

        def complete_job(self, job_id: str) -> models.SessionDerivationJob:
            completed = super().complete_job(job_id)
            self.completed.set()
            return completed

    queued = _job()
    service = FlakyDerivationService(queued)
    source = FakeSourceAgent(service)
    target = FakeTargetAgent()
    FakeWorkerAgentManager.agents = {"source_1": source, "target_1": target}
    FakeWorkerAgentManager.dropped = []
    FakeWorkerAgentManager.drop_error = None
    monkeypatch.setattr(worker_module, "AgentManager", FakeWorkerAgentManager)
    deletion = FakeSessionDeletion()
    worker = SessionDerivationWorker(
        gateway=SimpleNamespace(
            session_derivations=service,
            session_deletion=deletion,
        ),
        retry_delay_seconds=0.01,
        derivation_service=service,
        deletion_service=deletion,
    )

    await worker.start()
    try:
        await asyncio.wait_for(service.completed.wait(), timeout=1)
        assert worker.running is True
        assert service.get_job(queued.id).status == models.SESSION_DERIVATION_JOB_STATUS_READY
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_rescans_queued_jobs_after_stale_recovery(monkeypatch) -> None:
    scanned = asyncio.Event()

    class Service:
        def list_jobs(
            self,
            *statuses: SessionDerivationStatus,
        ) -> list[models.SessionDerivationJob]:
            assert statuses == (SessionDerivationStatus.QUEUED,)
            scanned.set()
            worker._stop_event.set()
            return []

    service = Service()
    worker = SessionDerivationWorker(
        gateway=SimpleNamespace(session_derivations=service),
        derivation_service=service,
        deletion_service=FakeSessionDeletion(),
    )
    worker._stale_recovery_pending = True
    worker._wake_event.clear()

    async def recover() -> bool:
        return True

    monkeypatch.setattr(worker, "interrupt_stale_jobs", recover)

    await asyncio.wait_for(worker._run(), timeout=1)

    assert scanned.is_set()


class FakeLifespanWorker:
    def __init__(self, *, gateway: object, notification_sink: object = None) -> None:
        self.gateway = gateway
        self.notification_sink = notification_sink
        self.running = False
        self.wake_count = 0

    async def start(self) -> None:
        self.running = True

    async def stop(self) -> None:
        self.running = False

    def wake(self) -> None:
        self.wake_count += 1

    async def interrupt_stale_jobs(self) -> None:
        return None


class FakeLifespanAgentManager:
    @classmethod
    async def areset(cls) -> None:
        return None


@pytest.mark.asyncio
async def test_lifespan_runs_stale_and_llm_cleanup_when_agent_reset_fails(
    monkeypatch,
) -> None:
    events: list[str] = []

    class Worker:
        def __init__(
            self,
            *,
            gateway: object,
            notification_sink: object = None,
        ) -> None:
            del gateway, notification_sink

        async def start(self) -> None:
            events.append("worker_start")

        async def stop(self) -> None:
            events.append("worker_stop")

        async def interrupt_stale_jobs(self) -> bool:
            events.append("interrupt_stale")
            return True

    class Manager:
        @classmethod
        async def areset(cls) -> None:
            events.append("agent_reset")
            raise RuntimeError("agent reset failed")

    async def configure(*args: object, **kwargs: object) -> None:
        del args, kwargs
        events.append("llm_configure")

    async def reset(*args: object, **kwargs: object) -> None:
        del args, kwargs
        events.append("llm_reset")

    monkeypatch.setattr(service_main, "SessionDerivationWorker", Worker)
    monkeypatch.setattr(service_main, "AgentManager", Manager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", object)
    monkeypatch.setattr(service_main.LLMClientManager, "aconfigure", configure)
    monkeypatch.setattr(service_main.LLMClientManager, "areset", reset)

    with pytest.raises(RuntimeError, match="agent reset failed"):
        async with service_main.lifespan(service_main.app):
            events.append("yield")

    assert events == [
        "llm_configure",
        "worker_start",
        "yield",
        "worker_stop",
        "agent_reset",
        "interrupt_stale",
        "llm_reset",
    ]
    assert service_main._derivation_worker is None


def test_derivation_create_query_and_error_contracts(monkeypatch) -> None:
    service = FakeDerivationService()

    class FakeCatalog:
        @staticmethod
        def get_session(session_id: str) -> models.Session | None:
            if session_id == "missing":
                return None
            return models.Session(id=session_id, workspace_id="ws", story_id=1)

    gateway = SimpleNamespace(
        catalog=FakeCatalog(),
        session_derivations=service,
    )
    monkeypatch.setattr(service_main, "SessionDerivationWorker", FakeLifespanWorker)
    monkeypatch.setattr(service_main, "AgentManager", FakeLifespanAgentManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: gateway)
    monkeypatch.setattr(
        service_main,
        "SessionDerivationService",
        lambda _gateway: service,
    )

    async def no_op(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(service_main.LLMClientManager, "aconfigure", no_op)
    monkeypatch.setattr(service_main.LLMClientManager, "areset", no_op)

    with TestClient(service_main.app) as client:
        created = client.post(
            "/agent/v1/chat/session/derivations",
            json={"session_id": "source_1", "branch_turn_id": 3, "title": "Fork"},
        )
        assert created.status_code == 202
        payload = created.json()
        assert payload["job_id"] == "job_1"
        assert payload["source_session_id"] == "source_1"
        assert payload["branch_turn_id"] == 3
        assert payload["status"] == "queued"

        queried = client.get(
            f"/agent/v1/chat/session/derivations/{payload['job_id']}"
        )
        assert queried.status_code == 200
        assert queried.json() == payload

        conflict = client.post(
            "/agent/v1/chat/session/derivations",
            json={"session_id": "source_1", "branch_turn_id": 3},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["error_code"] == "DERIVATION_SOURCE_BUSY"
        assert "active derivation" in conflict.json()["detail"]["message"]

        missing_source = client.post(
            "/agent/v1/chat/session/derivations",
            json={"session_id": "missing", "branch_turn_id": 3},
        )
        assert missing_source.status_code == 404

        missing_job = client.get(
            "/agent/v1/chat/session/derivations/not_found"
        )
        assert missing_job.status_code == 404
