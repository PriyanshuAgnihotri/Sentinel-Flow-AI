from enum import StrEnum
from pydantic import BaseModel, Field
from typing import Any


class Intent(StrEnum):
    ORDER_STATUS = "ORDER_STATUS"
    REFUND = "REFUND"
    KNOWLEDGE_QUESTION = "KNOWLEDGE_QUESTION"
    ACCOUNT_ACTION = "ACCOUNT_ACTION"
    UNKNOWN = "UNKNOWN"


class Risk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    user_id: str = Field(min_length=1, max_length=128)
    conversation_id: str | None = None


class WorkflowResponse(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1)
    sources: list[str] = []
    actions_taken: list[dict[str, Any]] = []
    blocked_actions: list[dict[str, Any]] = []
    escalation_required: bool = False
    trace_id: str
    request_id: str
    cache_hit: bool = False


class ApprovalDecision(BaseModel):
    decided_by: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=2000)


class RefundArgs(BaseModel):
    order_id: str = Field(pattern=r"^[A-Z0-9#-]{3,32}$")
    amount: float = Field(gt=0, le=1000)


class OrderStatusArgs(BaseModel):
    order_id: str = Field(pattern=r"^[A-Z0-9#-]{3,32}$")


class TicketArgs(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=4000)
    priority: str = Field(pattern=r"^(low|normal|high|urgent)$")


class DeleteAccountArgs(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
