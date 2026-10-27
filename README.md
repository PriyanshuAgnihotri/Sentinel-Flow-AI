# SentinelFlow

**A policy-controlled, observable multi-agent workflow orchestrator for customer support—not a generic chatbot.**

- **Live demo:** Not deployed yet. Deploy using the Railway/Vercel steps below and add URLs here.
- **API docs:** `http://localhost:8000/docs` after local startup.
- **Status:** Starter implementation / demo scaffold. See known limitations before production use.

## Architecture

See the [architecture diagram](docs/architecture.md).

Source diagram: [`docs/architecture.md`](docs/architecture.md) (Mermaid). Agent path: Input Guardrail → Router (intent/risk) → approved worker or high-risk escalation → Supervisor → structured response. The graph is bounded and the mock integrations cannot issue refunds or delete accounts.

## Repository layout

```text
sentinel-flow/
├── app/
│   ├── agents/graph.py          # LangGraph nodes and state transitions
│   ├── api/routes/workflows.py  # chat + approval endpoint contracts
│   ├── core/                    # settings and deterministic guardrails
│   ├── db/session.py            # async SQLAlchemy engine
│   ├── models/tables.py         # users, orders, workflow runs, tickets, approvals, audit
│   ├── schemas/workflow.py      # Pydantic request/response/tool schemas
│   ├── services/                # orchestrator, cache, observability
│   └── tools/mock_tools.py      # safe deterministic mock adapters
├── tests/                       # pytest safety and workflow tests
├── docs/                        # architecture and ADR
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── pyproject.toml
```

## Local setup

Requirements: Docker Desktop or Docker Engine + Compose; Python 3.11+ if running without Docker.

```bash
cp .env.example .env
# Add OPENAI_API_KEY and Langfuse keys if you configure those integrations.
docker compose up --build
```

Open `http://localhost:8000/docs`. Health checks: `GET /health`, `GET /ready`. Example:

```bash
curl -s http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"demo-user","message":"Where is my order #12345?"}'
```

Expected behavior is a mock order status response. Try a refund request to see escalation and confirm no refund is issued. Prompt-injection attempts should be blocked before routing.

Run tests:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/ready` | Dependency readiness/degraded state |
| GET | `/metrics` | Metrics endpoint placeholder (wire real aggregation before production) |
| POST | `/api/v1/chat` | Run support workflow |
| POST | `/api/v1/approvals/{approval_id}/approve` | Approves a pending approval using bearer-token authentication and persistent decision handling |
| POST | `/api/v1/approvals/{approval_id}/reject` | Rejects a pending approval using bearer-token authentication and persistent decision handling |

Example response fields: `answer`, `confidence`, `sources`, `actions_taken`, `blocked_actions`, `escalation_required`, `trace_id`, `request_id`, `cache_hit`.

## Deployment checklist

### Railway (API + PostgreSQL + Redis)
1. Push this repository to GitHub as `sentinel-flow`.
2. Create a Railway project; add PostgreSQL and Redis services.
3. Deploy the repository as a Docker service. Set the Dockerfile path to `Dockerfile` if autodetection fails.
4. Configure `DATABASE_URL` using Railway's PostgreSQL connection string, converted to SQLAlchemy async format (`postgresql+asyncpg://...`); set `REDIS_URL` from the Redis service.
5. Add `OPENAI_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `FRONTEND_ORIGINS`, and cache settings as service variables. Never commit secrets.
6. Configure `AUTH_JWT_SECRET` and `APPROVAL_API_TOKEN` as separate, cryptographically random secrets, each at least 32 characters long. Set `AUTH_JWT_ISSUER` and `AUTH_JWT_AUDIENCE` to the expected values. The application validates these security settings at startup in staging/production and refuses to start if they are missing or insecure. Keep real secrets in the hosting provider's secret-variable settings, never in Git.
7. Configure the health check path `/health`; validate `/ready`, `/docs`, and a demo `/api/v1/chat` call.
8. Run migrations/schema creation as a controlled release step. Do not rely on application startup to create production tables.

### Vercel (optional frontend)
A frontend is not included in this backend-first scaffold. Create a Next.js app, configure `NEXT_PUBLIC_API_BASE_URL` to the Railway URL, add the Vercel origin to `FRONTEND_ORIGINS`, deploy, and verify browser CORS. Never put server secrets in `NEXT_PUBLIC_*` variables.

### Langfuse Cloud
Set the three Langfuse environment variables. The included helper attempts a workflow span; expand instrumentation to per-node spans, model calls, tool calls, cache outcomes, token usage, and cost. The current workflow uses deterministic mock logic and does not make an LLM call, so no model token/cost telemetry will appear yet.

## Security and design trade-offs

- High-risk actions never execute automatically; mock refund and deletion functions fail closed.
- SQL validation is a defense-in-depth helper only. The application exposes no free-form SQL tool; use parameterized repository queries and database least privilege.
- The current cache uses a deterministic token-hash vector to keep offline tests runnable. It is not a semantic embedding model and must be replaced with real embeddings plus a vector index before production.
- The included knowledge answer is a demo fixture, not a complete RAG pipeline. Add document ingestion, chunking, retrieval, source-level ACLs, and confidence calibration.
- PostgreSQL models are defined, but writes, migrations, conversation persistence, and LangGraph checkpointer are not wired yet.
- `/metrics` currently documents the intended schema but does not aggregate telemetry. Add Prometheus/OpenTelemetry metrics and load-test the service.
- Approval endpoints require a configured bearer token and persist approval decisions. Full identity integration, role-based authorization, and comprehensive audited execution remain areas for further hardening.

## Evaluation

The current pytest suite covers basic order lookup, refund/account-deletion escalation, unknown intent, injection blocking, and destructive SQL rejection. It is a smoke suite, not the requested 30-case benchmark. Expand `tests/` with a versioned 30+ case fixture and report intent accuracy, block precision/recall, escalation accuracy, cache false-positive rate, latency, and cost after connecting the production LLM/retrieval pipeline.

## Screenshots

Add actual screenshots after deployment: Langfuse traces, cache hit/miss dashboard, and the deployed chat flow. No screenshots or public URLs are fabricated in this scaffold.

## License

Choose and add a license before publishing publicly.
