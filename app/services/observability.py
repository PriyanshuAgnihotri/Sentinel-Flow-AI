import logging
import math
from collections import Counter, deque
from threading import Lock
from uuid import uuid4

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_LATENCY_SAMPLES = 10_000
_metrics_lock = Lock()
_workflow_outcomes: Counter[str] = Counter()
_latency_samples: deque[float] = deque(maxlen=_MAX_LATENCY_SAMPLES)
_cache_hits = 0
_workflows_total = 0


def trace_ids() -> tuple[str, str]:
    return str(uuid4()), str(uuid4())


def observe(name: str, request_id: str, metadata: dict | None = None):
    """Best-effort Langfuse span; telemetry must not break the API."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None

    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        return client.start_span(
            name=name,
            metadata={"request_id": request_id, **(metadata or {})},
        )
    except Exception:
        logger.warning("Unable to initialize Langfuse span", exc_info=True)
        return None


def record_workflow_metric(
    *,
    outcome: str,
    duration_ms: float,
    cache_hit: bool = False,
) -> None:
    """Record one workflow execution in process-local metrics."""
    global _workflows_total, _cache_hits

    duration_ms = max(0.0, duration_ms)

    with _metrics_lock:
        _workflows_total += 1
        _workflow_outcomes[outcome] += 1
        _latency_samples.append(duration_ms)
        if cache_hit:
            _cache_hits += 1


def workflow_metrics_snapshot() -> dict:
    """Return a consistent snapshot of workflow metrics."""
    with _metrics_lock:
        total = _workflows_total
        hits = _cache_hits
        outcomes = dict(_workflow_outcomes)
        samples = sorted(_latency_samples)

    count = len(samples)
    average_latency = sum(samples) / count if count else None
    p95_latency = (
        samples[max(0, math.ceil(0.95 * count) - 1)]
        if count
        else None
    )

    return {
        "requests_total": total,
        "workflow_outcomes": outcomes,
        "cache_hits": hits,
        "cache_hit_rate": hits / total if total else 0.0,
        "average_latency_ms": (
            round(average_latency, 2) if average_latency is not None else None
        ),
        "p95_latency_ms": (
            round(p95_latency, 2) if p95_latency is not None else None
        ),
        "estimated_cost_saved_usd": None,
        "tool_call_success_rate": None,
        "pending_approvals": None,
        "metrics_scope": "current_process",
        "latency_sample_limit": _MAX_LATENCY_SAMPLES,
    }


def reset_workflow_metrics() -> None:
    """Reset process-local metrics for isolated tests and diagnostics."""
    global _workflows_total, _cache_hits

    with _metrics_lock:
        _workflows_total = 0
        _cache_hits = 0
        _workflow_outcomes.clear()
        _latency_samples.clear()
