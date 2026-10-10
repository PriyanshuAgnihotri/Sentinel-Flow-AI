# SentinelFlow evaluation report

**Status: initial scaffold; full evaluation pending.** Do not interpret this document as production validation.

## Current automated coverage

The pytest smoke suite exercises 6 prompt-injection examples, 7 destructive SQL examples, read-only SQL acceptance, order-status happy path, refund escalation, account-deletion blocking/escalation, and unknown-intent clarification. This is more than 15 assertions/cases but does not yet represent the requested 30-case benchmark.

## Metrics status

| Metric | Result | Why |
|---|---|---|
| Intent-classification accuracy | Not measured | Need labeled 30+ case fixture and deterministic scorer |
| Guardrail block accuracy | Not measured | Need positive/negative attack and benign-near-match labels |
| Correct escalation rate | Not measured | Need policy-labeled high/low risk cases |
| False-positive cache hits | Not measured | Production semantic embeddings and labeled near-duplicate pairs not configured |
| Average / p95 latency | Not measured | Must run repeatable benchmark in target deployment |
| Cost per request | Not measured | No live model calls are made by the scaffold |

## Reproducible evaluation plan

1. Add 30+ labeled fixtures spanning normal, ambiguous, refunds, deletion, injection, tool failure, cache behavior, and approval decisions.
2. Freeze policy and model versions; run `pytest -q` and a separate evaluation runner.
3. Report confusion matrices for intent and guardrail labels; report precision/recall and escalation recall.
4. Test cache on paraphrase pairs and adversarial near-matches; fail closed for personalized, high-risk, or policy-sensitive results.
5. Benchmark at least 500 requests with cold/warm cache; report average/p95 latency and cost from provider usage metadata.
