import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.tables import Approval, AuditLog
from app.services.approval_service import ApprovalService
from app.services.orchestrator import ApprovalPersistenceError


@pytest_asyncio.fixture(loop_scope="session")
async def client(monkeypatch):
    monkeypatch.setattr(settings, "approval_api_token", "test-approval-token")
    monkeypatch.setattr(settings, "approval_api_actor_id", "api-test-actor")

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client


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


async def test_approval_api_returns_503_when_token_not_configured(client, monkeypatch):
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
async def test_approval_api_persists_decision_and_audit(client, endpoint, expected_status):
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
            side_effect=ApprovalPersistenceError(
                "Unable to create the required refund approval"
            )
        ),
    )

    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "I want a refund for order #12345",
            "user_id": f"approval-failure-test-{uuid.uuid4()}",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "The required approval could not be saved. "
        "No refund was issued; please retry later."
    )
    assert "approval_id" not in response.json()
    ApprovalService.create.assert_awaited_once()
