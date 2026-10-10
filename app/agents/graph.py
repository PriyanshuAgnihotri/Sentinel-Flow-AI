from typing import TypedDict, Any
from uuid import uuid4
from langgraph.graph import StateGraph, END
from app.core.guardrails import inspect_input
from app.schemas.workflow import Intent, Risk
from app.tools.mock_tools import get_order_status, create_support_ticket

class FlowState(TypedDict, total=False):
    message: str; user_id: str; request_id: str; trace_id: str
    safe: bool; guardrail_category: str; intent: str; risk: str
    answer: str; confidence: float; sources: list[str]; actions_taken: list[dict[str, Any]]
    blocked_actions: list[dict[str, Any]]; escalation_required: bool; steps: int

def input_guardrail(s: FlowState) -> FlowState:
    result = inspect_input(s["message"])
    return {"safe": result.allowed, "guardrail_category": result.category or "", "steps": s.get("steps", 0)+1,
            **({} if result.allowed else {"answer": "I can’t help with that request. Please describe the support issue you need help with.", "confidence": 0.99, "blocked_actions": [{"type": result.category, "reason": result.reason, "policy_rule": result.policy_rule}], "escalation_required": False})}

def router(s: FlowState) -> FlowState:
    msg = s["message"].lower()
    if "refund" in msg or "money back" in msg: intent, risk = Intent.REFUND, Risk.HIGH
    elif "delete my account" in msg or "delete account" in msg: intent, risk = Intent.ACCOUNT_ACTION, Risk.HIGH
    elif "order" in msg and any(x in msg for x in ("where", "status", "track", "shipped")): intent, risk = Intent.ORDER_STATUS, Risk.LOW
    elif any(x in msg for x in ("password", "reset", "how do i", "policy", "troubleshoot")): intent, risk = Intent.KNOWLEDGE_QUESTION, Risk.LOW
    else: intent, risk = Intent.UNKNOWN, Risk.MEDIUM
    return {"intent": intent.value, "risk": risk.value, "steps": s.get("steps", 0)+1}

def worker(s: FlowState) -> FlowState:
    intent = s["intent"]
    if intent == Intent.ORDER_STATUS:
        import re
        match = re.search(r"(?:#\d+|ORD-[A-Z0-9]+)", s["message"], re.I)
        if not match:
            return {"answer": "What is your order ID? I need it to check the shipment status.", "confidence": .82, "sources": [], "actions_taken": [], "blocked_actions": [], "escalation_required": False}
        result = get_order_status(match.group(0))
        answer = (f"Order {result['order_id']} is {result['status']}; estimated delivery is {result['eta']}." if result["found"] else f"I couldn’t find order {result['order_id']}. Please verify the ID or open a support ticket.")
        return {"answer": answer, "confidence": .96 if result["found"] else .72, "sources": ["mock_order_service"], "actions_taken": [{"tool": "get_order_status", "result": result}], "blocked_actions": [], "escalation_required": False}
    if intent == Intent.REFUND:
        return {"answer": "Refunds require human approval after order and eligibility verification. I’ve prepared this for review; no refund has been issued.", "confidence": .96, "sources": ["refund_policy"], "actions_taken": [], "blocked_actions": [], "escalation_required": True}
    if intent == Intent.ACCOUNT_ACTION:
        return {"answer": "Account deletion is a destructive action. I can’t execute it automatically; identity verification and human approval are required.", "confidence": .99, "sources": ["account_deletion_policy"], "actions_taken": [], "blocked_actions": [{"type": "account_deletion", "reason": "Approval required; demo does not execute deletion", "policy_rule": "ACTION-HIGH-001"}], "escalation_required": True}
    if intent == Intent.KNOWLEDGE_QUESTION:
        return {"answer": "To reset your password, choose ‘Forgot password’ on the sign-in page and follow the email verification link. Never share your password or verification code with support.", "confidence": .78, "sources": ["demo_knowledge_base:password_reset"], "actions_taken": [], "blocked_actions": [], "escalation_required": False}
    return {"answer": "I need a little more detail to route this correctly. What product or account issue are you experiencing?", "confidence": .48, "sources": [], "actions_taken": [], "blocked_actions": [], "escalation_required": False}

def supervisor(s: FlowState) -> FlowState:
    if s.get("steps", 0) >= 8 and not s.get("answer"):
        return {"answer": "I couldn’t safely resolve this automatically. A support specialist should review it.", "confidence": .2, "escalation_required": True}
    return {"steps": s.get("steps", 0)+1}

def build_graph():
    graph = StateGraph(FlowState)
    graph.add_node("input_guardrail", input_guardrail); graph.add_node("router", router)
    graph.add_node("worker", worker); graph.add_node("supervisor", supervisor)
    graph.set_entry_point("input_guardrail")
    graph.add_conditional_edges("input_guardrail", lambda s: "router" if s.get("safe") else "supervisor", {"router":"router", "supervisor":"supervisor"})
    graph.add_edge("router", "worker"); graph.add_edge("worker", "supervisor"); graph.add_edge("supervisor", END)
    return graph.compile()

workflow_graph = build_graph()
