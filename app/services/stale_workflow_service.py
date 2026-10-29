from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import WorkflowRun
from app.services.workflow_lifecycle import WorkflowLifecycle


class StaleWorkflowService:
    """Identify potentially stale workflows without modifying their state."""

    DEFAULT_STALE_AFTER_MINUTES = 15

    @classmethod
    async def find_stale_runs(
        cls,
        session: AsyncSession,
        *,
        stale_after_minutes: int = DEFAULT_STALE_AFTER_MINUTES,
        now: datetime | None = None,
    ) -> list[WorkflowRun]:
        """Return pending or running runs older than the configured threshold."""
        if stale_after_minutes <= 0:
            raise ValueError("stale_after_minutes must be greater than zero")

        reference_time = now or datetime.now(UTC)
        if reference_time.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        cutoff = reference_time - timedelta(minutes=stale_after_minutes)

        statement = (
            select(WorkflowRun)
            .where(
                WorkflowRun.lifecycle_status.in_(
                    [WorkflowLifecycle.PENDING, WorkflowLifecycle.RUNNING]
                ),
                WorkflowRun.updated_at < cutoff,
            )
            .order_by(WorkflowRun.updated_at.asc(), WorkflowRun.id.asc())
        )

        result = await session.scalars(statement)
        return list(result.all())
