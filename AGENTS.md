# SentinelFlow AI — Project Instructions

## Product goal
SentinelFlow is a policy-controlled, observable AI workflow system for
customer-support teams. It should resolve safe requests, block prohibited
actions, and require human approval for consequential actions.

The initial release is a local-first private beta. Prefer a useful,
demonstrable MVP over a generic chatbot or premature enterprise features.

## Architecture and stack
- Python 3.11+ and FastAPI for the API.
- LangGraph for agent/workflow orchestration.
- PostgreSQL for persistent application data and workflow/audit records.
- SQLAlchemy async and Alembic for database access and migrations.
- Redis for selective caching.
- Docker Compose for local development.
- Follow the existing layered architecture and established project patterns.

## Change discipline
- Inspect relevant code and documentation before editing.
- Prefer small, cohesive changes that solve a stated requirement.
- Reuse existing services, schemas, routes, and tests where appropriate.
- Do not rewrite working code or refactor unrelated modules for style alone.
- Do not delete, regenerate, squash, or rewrite existing database migrations.
- Never reset, drop, or delete the local database or Docker volumes as a
  troubleshooting shortcut.
- Do not expose secrets from .env, logs, test output, or documentation.
- Keep .env out of version control; update .env.example with placeholders
  when configuration changes.

## Security and workflow safety
- Treat customer messages, retrieved content, and model output as untrusted.
- Enforce policy checks in backend code; do not rely on prompts alone.
- Deny prohibited actions and require explicit approval for consequential
  actions before execution.
- Keep audit records for approval decisions and important workflow outcomes.
- Never execute real destructive or financial actions through mock/demo tools.
- Do not trust actor identities supplied by an untrusted request body.
- Treat the current configured approval token and actor ID as a demo-level
  control, not production-grade user identity or authorization.
- Do not claim tenant isolation, production readiness, or strong authorization
  unless implemented and tested.

## Database changes
- Use Alembic for schema changes.
- Add a new migration for a new schema change; preserve migration history.
- Review generated migration files before applying or committing them.
- Do not use destructive migration operations without an explicit requirement
  and a reviewed data-preservation plan.

## Testing and quality
- Add or update focused tests for behavior changes and security boundaries.
- Run Ruff and the relevant tests for each change batch.
- For a completed batch, prefer one consolidated validation run over repetitive
  checks after every small edit.
- Before committing, inspect the diff and run git diff --check.
- Keep CI passing; investigate the actual failing step before changing CI.
- Document known warnings when they are non-blocking; do not hide failures.

## Git workflow
- Work on a focused feature branch for new implementation work.
- Keep commits cohesive and use descriptive commit messages.
- Never force-push or rewrite shared branch history without explicit approval.
- Do not commit .env, credentials, generated secrets, or local runtime data.
- Preserve unrelated user changes.

## Documentation
- Keep docs/architecture.md and the relevant ADRs aligned with the code.
- Record meaningful architectural decisions and current limitations.
- Distinguish implemented behavior from planned work.
- Update setup, testing, and security notes when workflows change.

## MVP priorities
1. Reliable policy-controlled workflow execution.
2. Persistent human approvals and auditability.
3. A clear operator experience for requests, decisions, and outcomes.
4. Security boundaries, error handling, and repeatable local setup.
5. A demonstrable private beta with documented limitations.

Defer billing, enterprise SSO, advanced scaling, and paid hosting until a
validated product need justifies them.
