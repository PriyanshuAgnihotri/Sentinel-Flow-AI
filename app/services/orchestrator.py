import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import workflow_graph
from app.core.guardrails import inspect_input
from app.schemas.workflow import Intent
from app.services.approval_service import ApprovalService
from app.services.cache import SemanticCache
from app.services.observability import observe, trace_ids
from app.services.workflow_lifecycle import WorkflowLifecycle
from app.services.workflow_run_service import (
    WorkflowRunPersistenceError,
    WorkflowRunService,
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def _transaction(session: AsyncSession):
    """Coordinate operations within one transaction."""
    if session.in_transaction():
        async with session.begin_nested():
            yield
    else:
        async with session.begin():
            yield

class ApprovalPersistenceError(Exception):
    """Raised when a required approval cannot be persisted."""


class Orchestrator:
    @staticmethod
    def _validate_final_status(status: str) -> None:
        """Validate the transition from running to a terminal outcome."""
        WorkflowLifecycle.validate_transition(
            WorkflowLifecycle.RUNNING,
            status,
        )

    def __init__(self, cache: SemanticCache | None = None):
        self.cache = cache

    async def run(
        self,
        message: str,
        user_id: str,
        session: AsyncSession,
        conversation_id: str | None = None,
    ) -> dict:
        request_id, trace_id = trace_ids()
        span = observe(
            "sentinelflow.workflow",
            request_id,
            {"user_id": user_id},
        )

        run_record = None

        try:
            # Persist lifecycle checkpoints before guardrails or agent execution.
            run_record = await WorkflowRunService.start(
                session,
                request_id=request_id,
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
            )
            await session.commit()

            run_record = await WorkflowRunService.transition(
                session,
                run=run_record,
                target_status=WorkflowLifecycle.RUNNING,
            )
            await session.commit()

            guardrail_result = inspect_input(message)

            if not guardrail_result.allowed:
                state = workflow_graph.invoke(
                    {
                        "message": message,
                        "user_id": user_id,
                        "request_id": request_id,
                        "trace_id": trace_id,
                        "steps": 0,
                    }
                )
                result = self._build_result(
                    state=state,
                    request_id=request_id,
                    trace_id=trace_id,
                    cache_hit=False,
                )
                await self._persist_run(
                    session,
                    run_record=run_record,
                    result=result,
                )
                self._finish_span(span, state, result)
                return result

            # Exact-match cache lookup is scoped to the requesting user.
            if self.cache:
                hit = await self.cache.lookup(message, user_id)
                if hit:
                    hit.update(
                        {
                            "request_id": request_id,
                            "trace_id": trace_id,
                            "cache_hit": True,
                        }
                    )
                    await self._persist_run(
                        session,
                        run_record=run_record,
                        result=hit,
                    )
                    self._finish_cached_span(span, hit)
                    return hit

            state = workflow_graph.invoke(
                {
                    "message": message,
                    "user_id": user_id,
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "steps": 0,
                }
            )

            result = self._build_result(
                state=state,
                request_id=request_id,
                trace_id=trace_id,
                cache_hit=False,
            )

                        # Save the approval and workflow run atomically.
            async with _transaction(session):
                if (
                    state.get("intent") == Intent.REFUND.value
                    and result["escalation_required"]
                    and not result["blocked_actions"]
                ):
                    try:
                        approval = await ApprovalService.create(
                            session,
                            request_id=request_id,
                            user_id=user_id,
                            action={
                                "type": "refund_review",
                                "message": message,
                                "requires_identity_verification": True,
                                "execution_enabled": False,
                            },
                        )
                    except Exception as exc:
                        logger.exception(
                            "Unable to persist required refund approval",
                            extra={"request_id": request_id},
                        )
                        raise ApprovalPersistenceError(
                            "Unable to create the required refund approval"
                        ) from exc

                    result["approval_id"] = approval.id

                await self._persist_run(
                    session,
                    run_record=run_record,
                    result=result,
                    commit=False,
                )

            # Commit approval creation and final workflow status atomically.
            await session.commit()

            if self.cache:
                await self.cache.store(message, user_id, result)

            self._finish_span(span, state, result)
            return result

        except (ApprovalPersistenceError, WorkflowRunPersistenceError):
            self._end_error_span(span)
            raise

        except Exception:
            logger.exception(
                "Workflow execution failed; returning safe fallback",
                extra={"request_id": request_id},
            )

            fallback = {
                "answer": (
                    "The workflow encountered a temporary error. "
                    "No sensitive action was performed; please retry "
                    "or contact support."
                ),
                "confidence": 0.1,
                "sources": [],
                "actions_taken": [],
                "blocked_actions": [],
                "escalation_required": True,
                "trace_id": trace_id,
                "request_id": request_id,
                "cache_hit": False,
            }

            # If a run was created, record the failure on that same run.
            # If creation failed before a run existed, do not return a fallback
            # without a durable workflow record.
            if run_record is None:
                self._end_error_span(span)
                raise

            # Avoid carrying any partial transaction into failure persistence.
            await session.rollback()
            await self._persist_run(
                session,
                run_record=run_record,
                result=fallback,
                status=WorkflowLifecycle.FAILED,
            )
            self._end_error_span(span)
            return fallback


    @staticmethod
    async def _persist_run(
        session: AsyncSession,
        *,
        run_record,
        result: dict,
        status: str | None = None,
        commit: bool = True,
    ) -> None:
        """Persist the terminal state on the existing workflow run."""
        final_status = (
            status
            if status is not None
            else WorkflowRunService.determine_status(result)
        )
        Orchestrator._validate_final_status(final_status)

        await WorkflowRunService.transition(
            session,
            run=run_record,
            target_status=final_status,
            result=result,
        )

        if commit:
            await session.commit()


    @staticmethod
    def _build_result(
        *,
        state: dict,
        request_id: str,
        trace_id: str,
        cache_hit: bool,
    ) -> dict:
        return {
            "answer": state.get(
                "answer",
                "I could not safely resolve this request.",
            ),
            "confidence": state.get("confidence", 0.2),
            "sources": state.get("sources", []),
            "actions_taken": state.get("actions_taken", []),
            "blocked_actions": state.get("blocked_actions", []),
            "escalation_required": state.get(
                "escalation_required",
                False,
            ),
            "trace_id": trace_id,
            "request_id": request_id,
            "cache_hit": cache_hit,
        }

    @staticmethod
    def _finish_span(span, state: dict, result: dict) -> None:
        if span:
            try:
                span.update(
                    output={
                        "intent": state.get("intent"),
                        "confidence": result["confidence"],
                        "escalation_required": result["escalation_required"],
                    }
                )
                span.end()
            except Exception:
                logger.warning(
                    "Unable to finalize workflow telemetry span",
                    exc_info=True,
                )

    @staticmethod
    def _finish_cached_span(span, result: dict) -> None:
        if span:
            try:
                span.update(
                    output={
                        "cache_hit": True,
                        "confidence": result["confidence"],
                        "escalation_required": result[
                            "escalation_required"
                        ],
                    }
                )
                span.end()
            except Exception:
                logger.warning(
                    "Unable to finalize cached workflow span",
                    exc_info=True,
                )

    @staticmethod
    def _end_error_span(span) -> None:
        if span:
            try:
                span.update(level="ERROR")
                span.end()
            except Exception:
                logger.warning(
                    "Unable to finalize failed workflow span",
                    exc_info=True,
                )
