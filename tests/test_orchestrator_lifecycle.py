
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.tables import AuditLog, WorkflowRun
from app.schemas.workflow import Intent
from app.services.orchestrator import Orchestrator


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "expected_status"),
    [
        (
            {
                "answer": "Your order is in transit.",
                "confidence": 0.9,
                "blocked_actions": [],
                "escalation_required": False,
            },
            "completed",
        ),
        (
            {
                "answer": "A refund requires human review.",
                "confidence": 0.8,
                "blocked_actions": [],
                "escalation_required": True,
            },
            "approval_required",
        ),
        (
            {
                "answer": "This request is blocked.",
                "confidence": 0.99,
                "blocked_actions": [
                    {"type": "policy_violation", "reason": "Blocked in test"}
                ],
                "escalation_required": False,
            },
            "blocked",
        ),
    ],
)
async def test_orchestrator_persists_lifecycle_status(
    monkeypatch,
    state,
    expected_status,
):
    request_id = None
    user_id = f"orchestrator-test-{uuid.uuid4()}"

    state = {
        **state,
        "intent": Intent.UNKNOWN.value,
        "sources": [],
        "actions_taken": [],
    }

    monkeypatch.setattr(
        "app.services.orchestrator.inspect_input",
        lambda message: type("GuardrailResult", (), {"allowed": True})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator.workflow_graph.invoke",
        lambda payload: state,
    )

    try:
        async with SessionLocal() as session:
            result = await Orchestrator().run(
                message="Test lifecycle status",
                user_id=user_id,
                session=session,
            )
            request_id = result["request_id"]

            run = await session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.request_id == request_id,
                    WorkflowRun.user_id == user_id,
                )
            )

            assert run is not None
            assert run.lifecycle_status == expected_status
            assert run.result_json["lifecycle_status"] == expected_status

            audit = await session.scalar(
                select(AuditLog).where(
                    AuditLog.request_id == request_id,
                    AuditLog.user_id == user_id,
                    AuditLog.event_type == f"workflow.{expected_status}",
                )
            )
            assert audit is not None
    finally:
        if request_id:
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
async def test_orchestrator_persists_failed_status(monkeypatch):
    user_id = f"orchestrator-failed-test-{uuid.uuid4()}"
    request_id = None

    monkeypatch.setattr(
        "app.services.orchestrator.inspect_input",
        lambda message: type("GuardrailResult", (), {"allowed": True})(),
    )

    def fail_workflow(payload):
        raise RuntimeError("Simulated workflow failure")

    monkeypatch.setattr(
        "app.services.orchestrator.workflow_graph.invoke",
        fail_workflow,
    )

    try:
        async with SessionLocal() as session:
            result = await Orchestrator().run(
                message="Test failed workflow",
                user_id=user_id,
                session=session,
            )
            request_id = result["request_id"]

            run = await session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.request_id == request_id,
                    WorkflowRun.user_id == user_id,
                )
            )

            assert run is not None
            assert run.lifecycle_status == "failed"
            assert run.result_json["lifecycle_status"] == "failed"
    finally:
        if request_id:
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
