# SentinelFlow architecture

```mermaid
flowchart TD
  U[Customer / Support UI] --> API[FastAPI API + Request ID]
  API --> CACHE{Redis semantic cache}
  CACHE -- hit --> OUT[Structured response]
  CACHE -- miss --> G[Input Guardrail]
  G -- blocked --> AUDIT[Audit / policy event]
  G -- allowed --> R[Router: intent + risk]
  R --> K[Knowledge retrieval]
  R --> T[Approved tool adapters]
  R --> H[Human approval for high risk]
  K --> S[Supervisor + bounded transitions]
  T --> S
  H --> S
  S --> DB[(PostgreSQL: runs, tickets, orders, approvals, audit)]
  S --> LF[Langfuse traces]
  S --> CACHE
  S --> OUT
```

The current scaffold includes an executable LangGraph flow for input inspection, intent routing, mock order status, safe knowledge demo answers, and high-risk escalation. PostgreSQL models and Redis cache adapter are present, but durable repository/checkpoint integration, authenticated approval decisions, production embeddings/vector index, and aggregate metrics are explicit follow-up work—not represented as completed features.
