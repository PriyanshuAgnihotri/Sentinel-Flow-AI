from app.agents.graph import workflow_graph
from app.services.observability import trace_ids, observe
from app.services.cache import SemanticCache

class Orchestrator:
    def __init__(self, cache: SemanticCache | None = None): self.cache = cache
    async def run(self, message: str, user_id: str) -> dict:
        request_id, trace_id = trace_ids()
        span = observe("sentinelflow.workflow", request_id, {"user_id": user_id})
        try:
            if self.cache:
                hit = await self.cache.lookup(message)
                if hit:
                    hit.update({"request_id": request_id, "trace_id": trace_id})
                    return hit
            state = workflow_graph.invoke({"message": message, "user_id": user_id, "request_id": request_id, "trace_id": trace_id, "steps": 0})
            result = {"answer": state.get("answer", "I could not safely resolve this request."), "confidence": state.get("confidence", .2),
                "sources": state.get("sources", []), "actions_taken": state.get("actions_taken", []), "blocked_actions": state.get("blocked_actions", []),
                "escalation_required": state.get("escalation_required", False), "trace_id": trace_id, "request_id": request_id, "cache_hit": False}
            if self.cache: await self.cache.store(message, result)
            if span:
                try: span.update(output={"intent": state.get("intent"), "confidence": result["confidence"], "escalation_required": result["escalation_required"]}); span.end()
                except Exception: pass
            return result
        except Exception:
            if span:
                try: span.update(level="ERROR"); span.end()
                except Exception: pass
            return {"answer": "The workflow encountered a temporary error. No sensitive action was performed; please retry or contact support.", "confidence": .1, "sources": [], "actions_taken": [], "blocked_actions": [], "escalation_required": True, "trace_id": trace_id, "request_id": request_id, "cache_hit": False}
