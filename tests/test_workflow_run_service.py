
import uuid
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.tables import AuditLog, WorkflowRun
from app.services.workflow_run_service import WorkflowRunService


@pytest.mark.asyncio
async def test_record_persists_run_and_audit():
    request_id = str(uuid4())
    user_id = f"workflow-test-{uuid4()}"

    result = {
        "answer": "Your order is in transit.",
        "confidence": 0.9,
        "sources": [],
        "actions_taken": [],
        "blocked_actions": [],
        "escalation_required": False,
        "request_id": request_id,
        "trace_id": str(uuid4()),
        "cache_hit": False,
    }

    try:
        async with SessionLocal() as session:
            run = await WorkflowRunService.record(
                session,
                request_id=request_id,
                user_id=user_id,
                message="Where is my order?",
                result=result,
                conversation_id=str(uuid4()),
            )

            assert run.request_id == request_id
            assert run.user_id == user_id
            assert run.result_json["lifecycle_status"] == "completed"
            assert run.result_json["response"]["answer"] == (
                "Your order is in transit."
            )

            audit = await session.scalar(
                select(AuditLog).where(
                    AuditLog.request_id == request_id,
                    AuditLog.event_type == "workflow.completed",
                )
            )
            assert audit is not None
            assert audit.details["workflow_run_id"] == run.id
    finally:
        async with SessionLocal() as session:
            await session.execute(
                WorkflowRun.__table__.delete().where(
                    WorkflowRun.request_id == request_id
                )
            )
            await session.execute(
                AuditLog.__table__.delete().where(
                    AuditLog.request_id == request_id
                )
            )
            await session.commit()


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            {
                "answer": "Done",
                "confidence": 0.9,
                "blocked_actions": [{"type": "account_deletion"}],
            },
            "blocked",
        ),
        (
            {
                "answer": "Please wait for approval.",
                "confidence": 0.8,
                "escalation_required": True,
            },
            "approval_required",
        ),
        
        (
            {
                "answer": "Done",
                "confidence": 0.9,
            },
            "completed",
        ),
    ],
)
def test_determine_lifecycle_status(result, expected):
    assert WorkflowRunService.determine_status(result) == expected

@pytest.mark.asyncio
async def test_record_persists_explicit_failed_status():
    request_id = str(uuid.uuid4())
    user_id = f"workflow-failed-test-{uuid.uuid4()}"

    async with SessionLocal() as session:
        try:
            run = await WorkflowRunService.record(
                session,
                request_id=request_id,
                user_id=user_id,
                message="Test workflow failure",
                result={
                    "answer": "The workflow encountered a temporary error.",
                    "confidence": 0.1,
                    "escalation_required": True,
                },
                status="failed",
            )

            assert run.result_json["lifecycle_status"] == "failed"
        finally:
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