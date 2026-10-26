import logging
from contextlib import asynccontextmanager
from typing import ClassVar
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.workflow_lifecycle import WorkflowLifecycle
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

    STATUS_COMPLETED: ClassVar[str] = "completed"
    STATUS_APPROVAL_REQUIRED: ClassVar[str] = "approval_required"
    STATUS_BLOCKED: ClassVar[str] = "blocked"
    STATUS_FAILED: ClassVar[str] = "failed"
    STATUS_PENDING: ClassVar[str] = "pending"
    STATUS_RUNNING: ClassVar[str] = "running"

    FINAL_STATUSES: ClassVar[frozenset[str]] = frozenset(
        {
            STATUS_COMPLETED,
            STATUS_APPROVAL_REQUIRED,
            STATUS_BLOCKED,
            STATUS_FAILED,
        }
    )

    VALID_STATUSES: ClassVar[frozenset[str]] = frozenset(
        FINAL_STATUSES | {STATUS_PENDING, STATUS_RUNNING}
    )
    
    @classmethod
    async def start(
        cls,
        session: AsyncSession,
        *,
        request_id: str,
        user_id: str,
        message: str,
        conversation_id: str | None = None,
    ) -> WorkflowRun:
        """Create and persist a workflow in the pending state."""
        run_id = str(uuid4())
        run = WorkflowRun(
            id=run_id,
            request_id=request_id,
            user_id=user_id,
            conversation_id=conversation_id,
            input_text=message,
            lifecycle_status=WorkflowLifecycle.PENDING,
            result_json={
                "lifecycle_status": WorkflowLifecycle.PENDING,
                "response": {},
            },
            confidence=0.0,
            escalation_required=False,
        )
        audit = AuditLog(
            id=str(uuid4()),
            request_id=request_id,
            user_id=user_id,
            event_type="workflow.pending",
            details={
                "workflow_run_id": run_id,
                "from_status": None,
                "to_status": WorkflowLifecycle.PENDING,
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
                "Unable to create workflow run",
                extra={"request_id": request_id},
            )
            raise WorkflowRunPersistenceError(
                "Unable to create workflow execution"
            ) from exc

    @classmethod
    async def transition(
        cls,
        session: AsyncSession,
        *,
        run: WorkflowRun,
        target_status: str,
        result: dict | None = None,
    ) -> WorkflowRun:
        """Validate and persist a lifecycle transition and audit event."""
        current_status = run.lifecycle_status
        WorkflowLifecycle.validate_transition(
            current_status,
            target_status,
        )

        if target_status not in cls.VALID_STATUSES:
            raise ValueError(f"Unsupported workflow status: {target_status}")

        existing_result = run.result_json or {}
        response = (
            result
            if result is not None
            else existing_result.get("response", {})
        )

        try:
            async with _transaction(session):
                run.lifecycle_status = target_status
                run.result_json = {
                    "lifecycle_status": target_status,
                    "response": response,
                }

                if result is not None:
                    run.confidence = float(result.get("confidence", 0.0))
                    run.escalation_required = bool(
                        result.get("escalation_required", False)
                    )

                audit = AuditLog(
                    id=str(uuid4()),
                    request_id=run.request_id,
                    user_id=run.user_id,
                    event_type=f"workflow.{target_status}",
                    details={
                        "workflow_run_id": run.id,
                        "from_status": current_status,
                        "to_status": target_status,
                        "cache_hit": bool(
                            result and result.get("cache_hit", False)
                        ),
                    },
                )
                session.add(audit)
                await session.flush()

            await session.refresh(run)
            return run
        except Exception as exc:
            logger.exception(
                "Unable to persist workflow transition",
                extra={
                    "request_id": run.request_id,
                    "workflow_run_id": run.id,
                },
            )
            raise WorkflowRunPersistenceError(
                "Unable to persist workflow transition"
            ) from exc
    

    @classmethod
    def determine_status(cls, result: dict) -> str:
        """Derive lifecycle status from the workflow response."""
        if result.get("blocked_actions"):
            return cls.STATUS_BLOCKED

        if result.get("approval_id") or result.get("escalation_required"):
            return cls.STATUS_APPROVAL_REQUIRED

        return cls.STATUS_COMPLETED

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

        if lifecycle_status not in cls.FINAL_STATUSES:
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
            lifecycle_status=lifecycle_status,
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
