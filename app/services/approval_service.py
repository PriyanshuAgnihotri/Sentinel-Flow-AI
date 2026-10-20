from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Approval, AuditLog


@asynccontextmanager
async def _transaction(session: AsyncSession):
    """Support standalone calls and caller-managed transactions."""
    if session.in_transaction():
        async with session.begin_nested():
            yield
    else:
        async with session.begin():
            yield


class ApprovalNotFoundError(Exception):
    """Raised when an approval does not exist."""


class ApprovalAlreadyDecidedError(Exception):
    """Raised when an approval is no longer pending."""


class ApprovalService:
    """Persist approval requests and record decisions transactionally."""

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        request_id: str,
        user_id: str,
        action: dict,
    ) -> Approval:
        approval = Approval(
            id=str(uuid4()),
            request_id=request_id,
            user_id=user_id,
            action_json=action,
            status="pending",
        )

        audit = AuditLog(
            id=str(uuid4()),
            request_id=request_id,
            user_id=user_id,
            event_type="approval.created",
            details={"approval_id": approval.id},
        )

        async with _transaction(session):
            session.add(approval)
            session.add(audit)

        # Refresh only after the transaction context has completed.
        await session.refresh(approval)
        return approval

    @staticmethod
    async def decide(
        session: AsyncSession,
        *,
        approval_id: str,
        decision: str,
        actor_id: str,
        reason: str | None = None,
    ) -> Approval:
        if decision not in {"approved", "rejected"}:
            raise ValueError("Decision must be 'approved' or 'rejected'.")

        async with _transaction(session):
            result = await session.execute(
                select(Approval).where(Approval.id == approval_id).with_for_update()
            )
            approval = result.scalar_one_or_none()

            if approval is None:
                raise ApprovalNotFoundError(approval_id)

            if approval.status != "pending":
                raise ApprovalAlreadyDecidedError(f"Approval is already {approval.status}.")

            approval.status = decision
            approval.decided_by = actor_id
            approval.decision_reason = reason

            session.add(
                AuditLog(
                    id=str(uuid4()),
                    request_id=approval.request_id,
                    user_id=approval.user_id,
                    event_type=f"approval.{decision}",
                    details={
                        "approval_id": approval.id,
                        "actor_id": actor_id,
                        "reason": reason,
                    },
                )
            )

        await session.refresh(approval)
        return approval
