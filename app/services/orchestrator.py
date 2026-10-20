
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import workflow_graph
from app.core.guardrails import inspect_input
from app.schemas.workflow import Intent
from app.services.approval_service import ApprovalService
from app.services.cache import SemanticCache
from app.services.observability import observe, trace_ids

logger = logging.getLogger(__name__)


class ApprovalPersistenceError(Exception):
    """Raised when a required approval cannot be persisted."""


class Orchestrator:
    def __init__(self, cache: SemanticCache | None = None):
        self.cache = cache

    async def run(
        self,
        message: str,
        user_id: str,
        session: AsyncSession,
    ) -> dict:
        request_id, trace_id = trace_ids()
        span = observe(
            "sentinelflow.workflow",
            request_id,
            {"user_id": user_id},
        )

        try:
            # Run deterministic guardrails before any cache lookup.
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
                self._finish_span(span, state, result)
                return result

            # Only exact requests within the user scope can be cache hits.
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

            # Persist a review request for refund-related escalations.
            # This creates a review record only; it never issues a refund.
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

            if self.cache:
                await self.cache.store(message, user_id, result)

            self._finish_span(span, state, result)
            return result

        except ApprovalPersistenceError:
            if span:
                try:
                    span.update(level="ERROR")
                    span.end()
                except Exception:
                    logger.warning(
                        "Unable to finalize failed workflow span",
                        exc_info=True,
                    )
            raise

        except Exception:
            logger.exception(
                "Workflow execution failed; returning safe fallback"
            )
            if span:
                try:
                    span.update(level="ERROR")
                    span.end()
                except Exception:
                    logger.warning(
                        "Unable to finalize failed workflow span",
                        exc_info=True,
                    )

            return {
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
