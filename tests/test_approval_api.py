import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.services.workflow_lifecycle import WorkflowLifecycle
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.tables import Approval, AuditLog, WorkflowRun
from app.services.approval_service import ApprovalService
from app.services.orchestrator import ApprovalPersistenceError
from app.services.workflow_run_service import (
    WorkflowRunPersistenceError,
    WorkflowRunService,
)


@pytest_asyncio.fixture(loop_scope="session")
async def client(monkeypatch):
    monkeypatch.setattr(settings, "approval_api_token", "test-approval-token")
    monkeypatch.setattr(settings, "approval_api_actor_id", "api-test-actor")

    monkeypatch.setattr(
        "app.core.auth.settings.auth_jwt_secret",
        "test-secret-for-unit-tests-32-bytes-minimum",
    )
    monkeypatch.setattr(
        "app.core.auth.settings.auth_jwt_issuer",
        "sentinelflow-tests",
    )
    monkeypatch.setattr(
        "app.core.auth.settings.auth_jwt_audience",
        "sentinelflow-api",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client


def create_history_token(user_id: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "iss": "sentinelflow-tests",
            "aud": "sentinelflow-api",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.auth_jwt_secret,
        algorithm="HS256",
    )


async def create_test_approval():
    request_id = str(uuid.uuid4())
    async with SessionLocal() as session:
        approval = await ApprovalService.create(
            session,
            request_id=request_id,
            user_id=f"api-test-user-{uuid.uuid4()}",
            action={"type": "refund", "order_id": "ORD-API-123"},
        )
        return approval.id, request_id


async def cleanup_test_records(approval_id, request_id):
    async with SessionLocal() as session:
        audits = (
            await session.scalars(select(AuditLog).where(AuditLog.request_id == request_id))
        ).all()
        approval = await session.get(Approval, approval_id)

        for audit in audits:
            await session.delete(audit)
        if approval is not None:
            await session.delete(approval)
        await session.commit()


@pytest.mark.parametrize("endpoint", ["approve", "reject"])
async def test_approval_api_requires_authentication(client, endpoint):
    response = await client.post(
        f"/api/v1/approvals/{uuid.uuid4()}/{endpoint}",
        json={"decided_by": "attacker", "reason": "test"},
    )
    assert response.status_code == 401


async def test_approval_api_returns_503_when_token_not_configured(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "approval_api_token", "")
    response = await client.post(
        f"/api/v1/approvals/{uuid.uuid4()}/approve",
        headers={"Authorization": "Bearer test-approval-token"},
        json={"decided_by": "tester", "reason": "test"},
    )
    assert response.status_code == 503


@pytest.mark.parametrize(
    ("endpoint", "expected_status"),
    [("approve", "approved"), ("reject", "rejected")],
)
async def test_approval_api_persists_decision_and_audit(
    client,
    endpoint,
    expected_status,
):
    approval_id, request_id = await create_test_approval()
    try:
        response = await client.post(
            f"/api/v1/approvals/{approval_id}/{endpoint}",
            headers={"Authorization": "Bearer test-approval-token"},
            json={"decided_by": "untrusted-client", "reason": "API test"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == approval_id
        assert body["status"] == expected_status
        assert body["decided_by"] == "api-test-actor"
        assert body["decision_reason"] == "API test"

        async with SessionLocal() as session:
            stored = await session.get(Approval, approval_id)
            assert stored is not None
            assert stored.status == expected_status
            assert stored.decided_by == "api-test-actor"

            audit = await session.scalar(
                select(AuditLog).where(
                    AuditLog.request_id == request_id,
                    AuditLog.event_type == f"approval.{expected_status}",
                )
            )
            assert audit is not None
            assert audit.details["actor_id"] == "api-test-actor"
    finally:
        await cleanup_test_records(approval_id, request_id)


async def test_approval_api_returns_404_for_unknown_id(client):
    response = await client.post(
        f"/api/v1/approvals/{uuid.uuid4()}/approve",
        headers={"Authorization": "Bearer test-approval-token"},
        json={"decided_by": "tester", "reason": "test"},
    )
    assert response.status_code == 404


async def test_approval_api_returns_409_for_duplicate_decision(client):
    approval_id, request_id = await create_test_approval()
    headers = {"Authorization": "Bearer test-approval-token"}
    body = {"decided_by": "tester", "reason": "first decision"}

    try:
        first = await client.post(
            f"/api/v1/approvals/{approval_id}/approve",
            headers=headers,
            json=body,
        )
        second = await client.post(
            f"/api/v1/approvals/{approval_id}/reject",
            headers=headers,
            json=body,
        )

        assert first.status_code == 200
        assert second.status_code == 409
    finally:
        await cleanup_test_records(approval_id, request_id)


async def test_chat_returns_503_when_refund_approval_cannot_be_saved(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        ApprovalService,
        "create",
        AsyncMock(
            side_effect=ApprovalPersistenceError("Unable to create the required refund approval")
        ),
    )

    user_id = f"approval-failure-test-{uuid.uuid4()}"

    response = await client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {create_history_token(user_id)}"},
        json={
            "message": "I want a refund for order #12345",
            "user_id": user_id,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "The required approval could not be saved. No refund was issued; please retry later."
    )
    assert "approval_id" not in response.json()
    ApprovalService.create.assert_awaited_once()


async def test_chat_persists_workflow_run_and_audit(client):
    user_id = f"workflow-api-test-{uuid.uuid4()}"
    conversation_id = str(uuid.uuid4())
    request_id = None

    try:
        response = await client.post(
            "/api/v1/chat",
            headers={"Authorization": f"Bearer {create_history_token(user_id)}"},
            json={
                "message": "How do I reset my password?",
                "user_id": user_id,
                "conversation_id": conversation_id,
            },
        )

        assert response.status_code == 200
        body = response.json()
        request_id = body["request_id"]

        async with SessionLocal() as session:
            run = await session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.request_id == request_id,
                    WorkflowRun.user_id == user_id,
                )
            )

            assert run is not None
            assert run.conversation_id == conversation_id
            assert run.input_text == "How do I reset my password?"
            assert run.result_json["response"]["answer"] == body["answer"]

            lifecycle_status = run.result_json["lifecycle_status"]
            assert lifecycle_status in {
                "completed",
                "approval_required",
                "blocked",
                "failed",
            }

            audit = await session.scalar(
                select(AuditLog).where(
                    AuditLog.request_id == request_id,
                    AuditLog.user_id == user_id,
                    AuditLog.event_type == f"workflow.{lifecycle_status}",
                )
            )

            assert audit is not None
            assert audit.details["workflow_run_id"] == run.id

    finally:
        if request_id is not None:
            async with SessionLocal() as session:
                await session.execute(
                    WorkflowRun.__table__.delete().where(
                        WorkflowRun.request_id == request_id,
                        WorkflowRun.user_id == user_id,
                    )
                )
                await session.execute(
                    AuditLog.__table__.delete().where(
                        AuditLog.request_id == request_id,
                        AuditLog.user_id == user_id,
                    )
                )
                await session.commit()



async def test_chat_rolls_back_refund_approval_when_workflow_run_persistence_fails(
    client,
    monkeypatch,
):
    user_id = f"atomicity-test-{uuid.uuid4()}"

    original_transition = WorkflowRunService.transition

    async def fail_final_transition(session, *, run, target_status, result=None):
        if target_status in {
            WorkflowLifecycle.COMPLETED,
            WorkflowLifecycle.APPROVAL_REQUIRED,
            WorkflowLifecycle.BLOCKED,
            WorkflowLifecycle.FAILED,
        }:
            raise WorkflowRunPersistenceError(
                "Unable to persist workflow transition"
            )

        return await original_transition(
            session,
            run=run,
            target_status=target_status,
            result=result,
        )

    monkeypatch.setattr(
        WorkflowRunService,
        "transition",
        fail_final_transition,
    )

    response = await client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {create_history_token(user_id)}"},
        json={
            "message": "I want a refund for order #12345",
            "user_id": user_id,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "The workflow result could not be saved. Please retry later."
    )

    async with SessionLocal() as session:
        approvals = (
            await session.scalars(
                select(Approval).where(Approval.user_id == user_id)
            )
        ).all()
        assert approvals == []

        audits = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.user_id == user_id,
                    AuditLog.event_type == "approval.created",
                )
            )
        ).all()
        assert audits == []



async def create_test_workflow_run(
    *,
    user_id: str,
    request_id: str | None = None,
    created_at: datetime | None = None,
) -> str:
    run_id = str(uuid.uuid4())
    request_id = request_id or str(uuid.uuid4())

    async with SessionLocal() as session:
        run = WorkflowRun(
            id=run_id,
            request_id=request_id,
            user_id=user_id,
            conversation_id=str(uuid.uuid4()),
            input_text="Test workflow history request",
            result_json={
                "lifecycle_status": "completed",
                "response": {
                    "answer": "Test response",
                    "sources": [],
                    "actions_taken": [],
                    "blocked_actions": [],
                    "escalation_required": False,
                },
            },
            confidence=0.95,
            escalation_required=False,
        )
        if created_at is not None:
            run.created_at = created_at

        session.add(run)
        await session.commit()

    return run_id


async def cleanup_workflow_runs(*run_ids: str) -> None:
    async with SessionLocal() as session:
        for run_id in run_ids:
            run = await session.get(WorkflowRun, run_id)
            if run is not None:
                await session.delete(run)
        await session.commit()


async def test_workflow_history_requires_authentication(client):
    response = await client.get("/api/v1/workflows")
    assert response.status_code == 401


async def test_workflow_history_lists_only_authenticated_user(client):
    user_id = f"history-user-{uuid.uuid4()}"
    other_user_id = f"other-user-{uuid.uuid4()}"

    own_run_id = await create_test_workflow_run(user_id=user_id)
    other_run_id = await create_test_workflow_run(user_id=other_user_id)

    try:
        response = await client.get(
            "/api/v1/workflows",
            params={"limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {create_history_token(user_id)}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == own_run_id
        assert body["items"][0]["user_id"] == user_id
        assert body["items"][0]["lifecycle_status"] == "completed"
    finally:
        await cleanup_workflow_runs(own_run_id, other_run_id)


async def test_workflow_history_pagination(client):
    user_id = f"history-page-user-{uuid.uuid4()}"
    run_ids = []

    try:
        for index in range(3):
            run_ids.append(
                await create_test_workflow_run(
                    user_id=user_id,
                    created_at=datetime.now(UTC) + timedelta(seconds=index),
                )
            )

        headers = {"Authorization": f"Bearer {create_history_token(user_id)}"}
        first = await client.get(
            "/api/v1/workflows",
            params={"limit": 2, "offset": 0},
            headers=headers,
        )
        second = await client.get(
            "/api/v1/workflows",
            params={"limit": 2, "offset": 2},
            headers=headers,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["total"] == 3
        assert len(first.json()["items"]) == 2
        assert len(second.json()["items"]) == 1
        assert first.json()["items"][0]["created_at"] >= (first.json()["items"][1]["created_at"])
    finally:
        await cleanup_workflow_runs(*run_ids)


async def test_workflow_history_detail_and_cross_user_access(client):
    owner_id = f"history-owner-{uuid.uuid4()}"
    other_user_id = f"history-non-owner-{uuid.uuid4()}"
    run_id = await create_test_workflow_run(user_id=owner_id)

    try:
        own_response = await client.get(
            f"/api/v1/workflows/{run_id}",
            headers={"Authorization": f"Bearer {create_history_token(owner_id)}"},
        )
        other_response = await client.get(
            f"/api/v1/workflows/{run_id}",
            headers={"Authorization": f"Bearer {create_history_token(other_user_id)}"},
        )

        assert own_response.status_code == 200
        assert own_response.json()["id"] == run_id
        assert own_response.json()["result"]["answer"] == "Test response"
        assert other_response.status_code == 404
    finally:
        await cleanup_workflow_runs(run_id)


async def test_workflow_history_rejects_invalid_pagination(client):
    user_id = f"history-pagination-user-{uuid.uuid4()}"
    response = await client.get(
        "/api/v1/workflows",
        params={"limit": 101},
        headers={"Authorization": f"Bearer {create_history_token(user_id)}"},
    )
    assert response.status_code == 422


async def test_workflow_history_rejects_invalid_jwt(client):
    response = await client.get(
        "/api/v1/workflows",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert response.status_code == 401
