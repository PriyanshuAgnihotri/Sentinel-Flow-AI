
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.schemas.workflow import ApprovalDecision, ChatRequest, WorkflowResponse
from app.services.approval_service import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    ApprovalService,
)
from app.services.orchestrator import ApprovalPersistenceError, Orchestrator

router = APIRouter()
session_dependency = Depends(get_session)


@router.post("/chat", response_model=WorkflowResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    session: AsyncSession = session_dependency,
):
    orchestrator = Orchestrator(getattr(request.app.state, "cache", None))

    try:
        result = await orchestrator.run(
            body.message,
            body.user_id,
            session=session,
        )
    except ApprovalPersistenceError:
        raise HTTPException(
            status_code=503,
            detail=(
                "The required approval could not be saved. "
                "No refund was issued; please retry later."
            ),
        ) from None

    return result


async def _decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    decision: str,
    authorization: str | None,
    session: AsyncSession,
):
    configured_token = settings.approval_api_token

    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail="Approval API authentication is not configured.",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required.")

    supplied_token = authorization.removeprefix("Bearer ").strip()
    if not supplied_token or not hmac.compare_digest(
        supplied_token,
        configured_token,
    ):
        raise HTTPException(status_code=401, detail="Invalid bearer token.")

    try:
        approval = await ApprovalService.decide(
            session,
            approval_id=approval_id,
            decision=decision,
            actor_id=settings.approval_api_actor_id,
            reason=body.reason,
        )
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="Approval not found.") from None
    except ApprovalAlreadyDecidedError:
        raise HTTPException(
            status_code=409,
            detail="Approval has already been decided.",
        ) from None

    return {
        "id": approval.id,
        "request_id": approval.request_id,
        "user_id": approval.user_id,
        "action": approval.action_json,
        "status": approval.status,
        "decided_by": approval.decided_by,
        "decision_reason": approval.decision_reason,
    }


@router.post("/approvals/{approval_id}/approve")
async def approve(
    approval_id: str,
    decision: ApprovalDecision,
    authorization: str | None = Header(default=None),
    session: AsyncSession = session_dependency,
):
    return await _decide_approval(
        approval_id,
        decision,
        "approved",
        authorization,
        session,
    )


@router.post("/approvals/{approval_id}/reject")
async def reject(
    approval_id: str,
    decision: ApprovalDecision,
    authorization: str | None = Header(default=None),
    session: AsyncSession = session_dependency,
):
    return await _decide_approval(
        approval_id,
        decision,
        "rejected",
        authorization,
        session,
    )
