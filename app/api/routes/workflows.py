from fastapi import APIRouter, Request, HTTPException
from app.schemas.workflow import ChatRequest, WorkflowResponse, ApprovalDecision
from app.services.orchestrator import Orchestrator
router = APIRouter()

@router.post("/chat", response_model=WorkflowResponse)
async def chat(body: ChatRequest, request: Request):
    orchestrator = Orchestrator(getattr(request.app.state, "cache", None))
    result = await orchestrator.run(body.message, body.user_id)
    return result

@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, decision: ApprovalDecision):
    # Safe scaffold behavior: records no real approval and executes no destructive action.
    raise HTTPException(501, "Approval persistence is not enabled in the scaffold; configure an authenticated approval repository before production use")

@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, decision: ApprovalDecision):
    raise HTTPException(501, "Approval persistence is not enabled in the scaffold; configure an authenticated approval repository before production use")
