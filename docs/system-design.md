# SentinelFlow System Design and Private Beta Readiness

## 1. Purpose

SentinelFlow is a policy-controlled AI workflow system for customer-support
teams. It should resolve safe requests, block prohibited actions, and route
consequential actions through human approval.

The initial target is a local-first private beta using mock tools. Production
integrations and real destructive or financial actions are out of scope.

## 2. Current architecture

- **API:** FastAPI routes expose workflow functionality and approval decisions.
- **Orchestration:** LangGraph coordinates the existing workflow nodes and
  bounded transitions.
- **Policy enforcement:** Backend guardrails inspect requests and enforce
  restrictions independently of model instructions.
- **Tools:** Mock adapters demonstrate workflow behavior without changing
  real customer systems.
- **Persistence:** PostgreSQL and SQLAlchemy models store application records.
  Alembic manages schema changes.
- **Approvals:** Approval service persists approval decisions and associated
  audit records. API endpoints support approve/reject decisions.
- **Cache:** Redis provides the existing cache adapter. Its current deterministic
  hashing approach is a scaffold, not a production semantic-search solution.
- **Observability:** Request IDs and application logging are present. End-to-end
  traces, operational dashboards, and production alerting need further work.
- **Interface:** A dedicated operator frontend is not yet implemented; the
  frontend directory currently contains a README.

See `architecture.md` for the current workflow diagram and
`adr-001-architecture-decisions.md` for architectural decisions.

## 3. Approval lifecycle

1. A workflow identifies an action that requires human review.
2. An approval request is created and persisted.
3. An authorized operator submits an approve or reject decision.
4. The service checks the approval state and records the decision and audit
   event transactionally.
5. Missing approvals and repeated decisions return explicit errors.
6. The workflow must not execute a consequential action merely because a
   request was approved; execution must also validate the target resource,
   applicable policy, and authorization.

The current approval API uses a configured bearer token and configured actor
ID. This is a useful initial control, not a complete production identity model.
Do not connect it to real financial or destructive operations yet.

## 4. Fifteen-layer readiness review

| Layer | Current status | Remaining work |
|---|---|---|
| 1. System design | Architecture and ADR exist | Keep implementation and intended design distinct |
| 2. Architecture | FastAPI, LangGraph, PostgreSQL, Redis | Complete and document workflow persistence boundaries |
| 3. Database/storage | Models and Alembic migrations exist | Validate retention, recovery, and operational backup procedures |
| 4. Authentication/permissions | Approval endpoint token check exists | Real identity, role-based authorization, and resource-level access |
| 5. API/backend | Workflow and approval routes exist | API contract, error behavior, and integration tests as features expand |
| 6. Frontend | README only | Build operator request, approval, and outcome screens |
| 7. CI/CD/version control | GitHub Actions CI passes | Keep branch checks required and review changes before merging |
| 8. Testing | 48 tests passed in the latest local run | Build a labeled evaluation set of at least 30 cases |
| 9. Hosting/cloud | Local Docker Compose | Choose hosting only after deployment and security needs are defined |
| 10. Security | Guardrails and token-protected approvals | Threat review, secrets handling, authorization, and tenant boundaries |
| 11. Rate limiting | Not confirmed as implemented | Add limits before exposing the API beyond a trusted local environment |
| 12. Caching/CDN | Redis cache adapter exists | Validate cache isolation, policy versioning, and sensitive-result behavior |
| 13. Error tracking/logs | Application logging and request IDs exist | Structured operational error tracking and actionable error reporting |
| 14. Monitoring/alerts | Not confirmed as implemented | Define health, failure, and latency indicators with alert thresholds |
| 15. Scaling | Not a current MVP objective | Defer until measured usage justifies it |

A status of "not confirmed" means the current project documentation does
not establish that the capability is implemented and validated.

## 5. Evaluation and acceptance

The current evaluation report says the requested 30-case benchmark and
performance metrics remain incomplete. Do not claim measured classification
accuracy, guardrail accuracy, escalation recall, cache false-positive rate,
p95 latency, or cost per request until those measurements exist.

Before private beta, prepare labeled cases covering:
- Normal and ambiguous support requests
- Prompt injection and prohibited requests
- Refunds, deletion, and other high-risk actions
- Approval, rejection, missing approval, and duplicate decisions
- Tool failures and cache edge cases

Run the test suite and a separate evaluation runner. Report failures and
limitations rather than treating passing unit tests as production validation.

## 6. Private beta scope

### Include
- Local repeatable startup with Docker Compose
- Safe request handling and policy enforcement
- Mock tool execution only
- Persistent approvals and audit events
- Clear workflow errors and observable outcomes
- Documented setup, test, and recovery instructions

### Defer
- Real refunds, account deletion, or other destructive integrations
- Production-grade user identity and enterprise SSO
- Claims of tenant isolation until implemented and tested
- Paid hosting, billing, advanced scaling, and CDN infrastructure
- Production semantic embeddings and vector retrieval until needed

## 7. Delivery sequence

1. Establish project instructions and document the current design.
2. Complete and test the end-to-end workflow, including approval gating and
   safe mock execution.
3. Build the smallest useful operator interface.
4. Add the labeled evaluation suite and address security gaps.
5. Run a documented local private-beta demonstration.
6. Reassess hosting and external integrations only after the local workflow
   and safety boundaries are validated.
