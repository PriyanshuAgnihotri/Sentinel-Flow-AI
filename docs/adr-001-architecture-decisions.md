# ADR-001: SentinelFlow architecture decisions

- **LangGraph:** Explicit nodes and transitions make the support workflow inspectable, testable, and bounded; routing is not hidden in one large prompt.
- **Redis semantic cache:** Fast, TTL-bound reuse can reduce latency and model spend. The included deterministic hashing embedding is only an offline scaffold; production must use a real embedding model and vector index, and should cache only policy-versioned, non-user-specific answers.
- **PostgreSQL checkpointing:** Relational records suit users, orders, approvals, workflow runs, and audit events. The schema is provided; LangGraph checkpointer wiring and repository writes remain to be implemented before claiming durable resume support.
- **Guardrails separate from agents:** Deterministic policy enforcement must not depend on an LLM following instructions. Model output is never authority to bypass policy.
- **Human approval for destructive actions:** Refunds and account deletion create financial/privacy impact. Approval must be authenticated, authorized, auditable, idempotent, and verified against the target resource before execution.

## Security notes

Mock tools do not mutate real systems. Never connect destructive actions until identity verification, tenant-scoped authorization, approval persistence, idempotency, audit logging, rate limiting, and integration-specific controls are implemented and reviewed.
