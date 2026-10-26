import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.models.tables import WorkflowRun
from app.schemas.workflow import (
    ApprovalDecision,
    ChatRequest,
    WorkflowHistoryDetail,
    WorkflowHistoryPage,
    WorkflowResponse,
)
from app.services.approval_service import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    ApprovalService,
)
from app.services.orchestrator import ApprovalPersistenceError, Orchestrator
from app.services.workflow_run_service import WorkflowRunPersistenceError

router = APIRouter()
session_dependency = Depends(get_session)


@router.post("/chat", response_model=WorkflowResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = session_dependency,
):
    orchestrator = Orchestrator(getattr(request.app.state, "cache", None))

    try:
        result = await orchestrator.run(
            body.message,
            current_user,
            session=session,
            conversation_id=body.conversation_id,
        )
    except ApprovalPersistenceError:
        raise HTTPException(
            status_code=503,
            detail=(
                "The required approval could not be saved. "
                "No refund was issued; please retry later."
            ),
        ) from None
    except WorkflowRunPersistenceError:
        raise HTTPException(
            status_code=503,
            detail=(
                "The workflow result could not be saved. "
                "Please retry later."
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



def _workflow_history_item(run: WorkflowRun) -> dict:
    stored_result = run.result_json or {}
    response = stored_result.get("response", {})

    return {
        "id": run.id,
        "request_id": run.request_id,
        "user_id": run.user_id,
        "conversation_id": run.conversation_id,
        "input_text": run.input_text,
        "lifecycle_status": run.lifecycle_status,
        "confidence": run.confidence,
        "escalation_required": run.escalation_required,
        "created_at": run.created_at,
        "result": response,
    }


@router.get("/workflows", response_model=WorkflowHistoryPage)
async def list_workflow_history(
    current_user: str = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = session_dependency,
):
    total = await session.scalar(
        select(func.count())
        .select_from(WorkflowRun)
        .where(WorkflowRun.user_id == current_user)
    )

    runs = (
        await session.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.user_id == current_user)
            .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return {
        "items": [
            {
                key: value
                for key, value in _workflow_history_item(run).items()
                if key != "result"
            }
            for run in runs
        ],
        "limit": limit,
        "offset": offset,
        "total": total or 0,
    }
@router.get("/workflows/{run_id}", response_model=WorkflowHistoryDetail)
async def get_workflow_history_detail(
    run_id: str,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = session_dependency,
):
    run = await session.scalar(
        select(WorkflowRun).where(
            WorkflowRun.id == run_id,
            WorkflowRun.user_id == current_user,
        )
    )

    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found.")

    return _workflow_history_item(run)