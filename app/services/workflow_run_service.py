
import logging
from contextlib import asynccontextmanager
from typing import ClassVar
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import AuditLog, WorkflowRun

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _transaction(session: AsyncSession):
    """Use a savepoint when a caller owns the transaction."""
    if session.in_transaction():
        async with session.begin_nested():
            yield
    else:
        async with session.begin():
            yield


class WorkflowRunPersistenceError(Exception):
    """Raised when a workflow run cannot be persisted."""


class WorkflowRunService:
    """Persist workflow execution results and lifecycle outcomes."""

    VALID_STATUSES: ClassVar[set[str]] = {
        "completed",
        "approval_required",
        "blocked",
        "failed",
    }

    @staticmethod
    def determine_status(result: dict) -> str:
        """Derive lifecycle status from the workflow response."""
        if result.get("blocked_actions"):
            return "blocked"

        if result.get("approval_id") or result.get("escalation_required"):
            return "approval_required"

        return "completed"

    @classmethod
    async def record(
        cls,
        session: AsyncSession,
        *,
        request_id: str,
        user_id: str,
        message: str,
        result: dict,
        conversation_id: str | None = None,
        status: str | None = None,
    ) -> WorkflowRun:
        """Persist a workflow run and its audit event."""
        lifecycle_status = (
            status if status is not None else cls.determine_status(result)
        )

        if lifecycle_status not in cls.VALID_STATUSES:
            raise ValueError(
                f"Unsupported workflow status: {lifecycle_status}"
            )

        run_id = str(uuid4())

        run = WorkflowRun(
            id=run_id,
            request_id=request_id,
            user_id=user_id,
            conversation_id=conversation_id,
            input_text=message,
            result_json={
                "lifecycle_status": lifecycle_status,
                "response": result,
            },
            confidence=float(result.get("confidence", 0.0)),
            escalation_required=bool(
                result.get("escalation_required", False)
            ),
        )

        audit = AuditLog(
            id=str(uuid4()),
            request_id=request_id,
            user_id=user_id,
            event_type=f"workflow.{lifecycle_status}",
            details={
                "workflow_run_id": run_id,
                "cache_hit": bool(result.get("cache_hit", False)),
            },
        )

        try:
            async with _transaction(session):
                session.add_all([run, audit])
                await session.flush()

            await session.refresh(run)
            return run

        except Exception as exc:
            logger.exception(
                "Unable to persist workflow run",
                extra={
                    "request_id": request_id,
                    "workflow_run_id": run_id,
                },
            )
            raise WorkflowRunPersistenceError(
                "Unable to persist workflow execution"
            ) from exc
