from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models.tables import AuditLog, WorkflowRun
from app.services.stale_workflow_service import StaleWorkflowService


@pytest.mark.asyncio
async def test_finds_old_pending_and_running_workflows():
    request_id = str(uuid4())
    user_id = f"stale-test-{uuid4()}"
    now = datetime.now(UTC)

    runs = [
        WorkflowRun(
            id=str(uuid4()),
            request_id=request_id,
            user_id=user_id,
            input_text="Old pending workflow",
            lifecycle_status="pending",
            result_json={"lifecycle_status": "pending", "response": {}},
            confidence=0.0,
            escalation_required=False,
            created_at=now - timedelta(minutes=30),
            updated_at=now - timedelta(minutes=30),
        ),
        WorkflowRun(
            id=str(uuid4()),
            request_id=request_id,
            user_id=user_id,
            input_text="Old running workflow",
            lifecycle_status="running",
            result_json={"lifecycle_status": "running", "response": {}},
            confidence=0.0,
            escalation_required=False,
            created_at=now - timedelta(minutes=20),
            updated_at=now - timedelta(minutes=20),
        ),
        WorkflowRun(
            id=str(uuid4()),
            request_id=request_id,
            user_id=user_id,
            input_text="Recent running workflow",
            lifecycle_status="running",
            result_json={"lifecycle_status": "running", "response": {}},
            confidence=0.0,
            escalation_required=False,
            created_at=now - timedelta(minutes=2),
            updated_at=now - timedelta(minutes=2),
        ),
        WorkflowRun(
            id=str(uuid4()),
            request_id=request_id,
            user_id=user_id,
            input_text="Old completed workflow",
            lifecycle_status="completed",
            result_json={"lifecycle_status": "completed", "response": {}},
            confidence=1.0,
            escalation_required=False,
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        ),
    ]

    try:
        async with SessionLocal() as session:
            session.add_all(runs)
            await session.commit()

            stale_runs = await StaleWorkflowService.find_stale_runs(
                session,
                stale_after_minutes=15,
                now=now,
            )


            stale_ids = {run.id for run in stale_runs}
            assert {runs[0].id, runs[1].id}.issubset(stale_ids)
            assert runs[2].id not in stale_ids
            assert runs[3].id not in stale_ids

            assert all(
                run.lifecycle_status in {"pending", "running"}
                for run in stale_runs
            )
    finally:
        async with SessionLocal() as session:
            await session.execute(
                delete(WorkflowRun).where(
                    WorkflowRun.request_id == request_id,
                    WorkflowRun.user_id == user_id,
                )
            )
            await session.execute(
                delete(AuditLog).where(
                    AuditLog.request_id == request_id,
                    AuditLog.user_id == user_id,
                )
            )
            await session.commit()


@pytest.mark.asyncio
async def test_rejects_non_positive_stale_threshold():
    async with SessionLocal() as session:
        with pytest.raises(ValueError, match="greater than zero"):
            await StaleWorkflowService.find_stale_runs(
                session,
                stale_after_minutes=0,
            )


@pytest.mark.asyncio
async def test_rejects_naive_reference_datetime():
    async with SessionLocal() as session:
        with pytest.raises(ValueError, match="timezone-aware"):
            await StaleWorkflowService.find_stale_runs(
                session,
                now=datetime(2026, 10, 28, 12, 0),
            )


@pytest.mark.asyncio
async def test_detection_does_not_change_workflow_status():
    request_id = str(uuid4())
    user_id = f"stale-readonly-test-{uuid4()}"
    now = datetime.now(UTC)

    run = WorkflowRun(
        id=str(uuid4()),
        request_id=request_id,
        user_id=user_id,
        input_text="Stale workflow safety test",
        lifecycle_status="running",
        result_json={"lifecycle_status": "running", "response": {}},
        confidence=0.0,
        escalation_required=False,
        created_at=now - timedelta(minutes=30),
        updated_at=now - timedelta(minutes=30),
    )

    try:
        async with SessionLocal() as session:
            session.add(run)
            await session.commit()

            original_status = run.lifecycle_status
            original_result = dict(run.result_json)

            stale_runs = await StaleWorkflowService.find_stale_runs(
                session,
                stale_after_minutes=15,
                now=now,
            )

            assert any(stale.id == run.id for stale in stale_runs)
            assert run.lifecycle_status == original_status
            assert run.result_json == original_result
    finally:
        async with SessionLocal() as session:
            await session.execute(
                delete(WorkflowRun).where(
                    WorkflowRun.request_id == request_id,
                    WorkflowRun.user_id == user_id,
                )
            )
            await session.execute(
                delete(AuditLog).where(
                    AuditLog.request_id == request_id,
                    AuditLog.user_id == user_id,
                )
            )
            await session.commit()