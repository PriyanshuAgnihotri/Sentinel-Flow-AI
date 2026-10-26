import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.tables import AuditLog, WorkflowRun
from app.services.workflow_lifecycle import WorkflowLifecycle
from app.services.workflow_run_service import WorkflowRunService


@pytest.mark.asyncio
async def test_workflow_persists_intermediate_and_final_states():
    request_id = str(uuid.uuid4())
    user_id = f"lifecycle-test-{uuid.uuid4()}"

    try:
        async with SessionLocal() as session:
            run = await WorkflowRunService.start(
                session,
                request_id=request_id,
                user_id=user_id,
                message="Test persistent workflow",
            )

            assert run.lifecycle_status == WorkflowLifecycle.PENDING

            await WorkflowRunService.transition(
                session,
                run=run,
                target_status=WorkflowLifecycle.RUNNING,
            )
            assert run.lifecycle_status == WorkflowLifecycle.RUNNING

            result = {
                "answer": "Test completed",
                "confidence": 0.9,
                "blocked_actions": [],
                "escalation_required": False,
            }

            await WorkflowRunService.transition(
                session,
                run=run,
                target_status=WorkflowLifecycle.COMPLETED,
                result=result,
            )

            assert run.lifecycle_status == WorkflowLifecycle.COMPLETED
            assert (
                run.result_json["lifecycle_status"]
                == WorkflowLifecycle.COMPLETED
            )

            audits = (
                await session.scalars(
                    select(AuditLog)
                    .where(AuditLog.request_id == request_id)
                    .order_by(AuditLog.created_at, AuditLog.id)
                )
            ).all()

            assert {
                audit.event_type for audit in audits
            } >= {
                "workflow.pending",
                "workflow.running",
                "workflow.completed",
            }

        async with SessionLocal() as session:
            with pytest.raises(
                ValueError,
                match="Invalid workflow lifecycle transition",
            ):
                await WorkflowRunService.transition(
                    session,
                    run=run,
                    target_status=WorkflowLifecycle.RUNNING,
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