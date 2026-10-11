import uuid

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.tables import Approval, AuditLog
from app.services.approval_service import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    ApprovalService,
)


@pytest.mark.asyncio
async def test_create_approval_persists_pending_record_and_audit():
    request_id = str(uuid.uuid4())
    user_id = f"test-user-{uuid.uuid4()}"

    async with SessionLocal() as session:
        approval = await ApprovalService.create(
            session,
            request_id=request_id,
            user_id=user_id,
            action={"type": "refund", "order_id": "ORD-123"},
        )

        assert approval.status == "pending"
        assert approval.user_id == user_id
        assert approval.action_json["type"] == "refund"

        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.request_id == request_id,
                AuditLog.event_type == "approval.created",
            )
        )
        assert audit is not None
        assert audit.details["approval_id"] == approval.id

        await session.delete(approval)
        await session.delete(audit)
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approved", "rejected"])
async def test_decide_updates_status_and_writes_audit(decision):
    request_id = str(uuid.uuid4())
    user_id = f"test-user-{uuid.uuid4()}"
    actor_id = f"test-actor-{uuid.uuid4()}"

    async with SessionLocal() as session:
        approval = await ApprovalService.create(
            session,
            request_id=request_id,
            user_id=user_id,
            action={"type": "refund", "order_id": "ORD-456"},
        )
        approval_id = approval.id

        decided = await ApprovalService.decide(
            session,
            approval_id=approval_id,
            decision=decision,
            actor_id=actor_id,
            reason="Automated test",
        )

        assert decided.status == decision
        assert decided.decided_by == actor_id
        assert decided.decision_reason == "Automated test"

        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.request_id == request_id,
                AuditLog.event_type == f"approval.{decision}",
            )
        )
        assert audit is not None
        assert audit.details["actor_id"] == actor_id

        audits = (
            await session.scalars(select(AuditLog).where(AuditLog.request_id == request_id))
        ).all()
        for entry in audits:
            await session.delete(entry)

        await session.delete(decided)
        await session.commit()


@pytest.mark.asyncio
async def test_decide_rejects_missing_approval():
    async with SessionLocal() as session:
        with pytest.raises(ApprovalNotFoundError):
            await ApprovalService.decide(
                session,
                approval_id=str(uuid.uuid4()),
                decision="approved",
                actor_id="test-actor",
            )


@pytest.mark.asyncio
async def test_decide_rejects_second_decision():
    request_id = str(uuid.uuid4())

    async with SessionLocal() as session:
        approval = await ApprovalService.create(
            session,
            request_id=request_id,
            user_id=f"test-user-{uuid.uuid4()}",
            action={"type": "refund", "order_id": "ORD-789"},
        )
        approval_id = approval.id

        await ApprovalService.decide(
            session,
            approval_id=approval_id,
            decision="approved",
            actor_id="test-actor",
        )

        with pytest.raises(ApprovalAlreadyDecidedError):
            await ApprovalService.decide(
                session,
                approval_id=approval_id,
                decision="rejected",
                actor_id="test-actor",
            )

        result = await session.execute(select(Approval).where(Approval.id == approval_id))
        stored = result.scalar_one()
        assert stored.status == "approved"

        audits = (
            await session.scalars(select(AuditLog).where(AuditLog.request_id == request_id))
        ).all()
        for entry in audits:
            await session.delete(entry)

        await session.delete(stored)
        await session.commit()


@pytest.mark.asyncio
async def test_decide_rejects_invalid_decision():
    async with SessionLocal() as session:
        with pytest.raises(ValueError):
            await ApprovalService.decide(
                session,
                approval_id=str(uuid.uuid4()),
                decision="maybe",
                actor_id="test-actor",
            )
