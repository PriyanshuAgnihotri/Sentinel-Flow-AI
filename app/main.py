import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.routes.workflows import router
from app.core.config import settings
from app.services.cache import SemanticCache

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = None
    try:
        redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
        )
        await redis.ping()
        app.state.cache = SemanticCache(redis)
    except Exception:
        logger.warning(
            "Redis unavailable; continuing without cache",
            exc_info=True,
        )
        app.state.cache = None

    app.state.redis = redis
    yield

    if redis:
        try:
            await redis.aclose()
        except Exception:
            logger.debug("Redis shutdown failed", exc_info=True)


app = FastAPI(
    title="SentinelFlow API",
    version="0.1.0",
    description="Policy-controlled customer-support workflow orchestrator",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

app.include_router(router, prefix=settings.api_prefix)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "sentinel-flow"}


@app.get("/ready")
async def ready():
    redis_ok = False
    redis = getattr(app.state, "redis", None)

    if redis:
        try:
            redis_ok = bool(await redis.ping())
        except Exception:
            logger.warning("Redis readiness check failed", exc_info=True)

    # Redis is optional for the local demo; report its status explicitly.
    return {
        "status": "ready" if redis_ok else "degraded",
        "redis": redis_ok,
        "cache_enabled": getattr(app.state, "cache", None) is not None,
    }


@app.get("/metrics")
def metrics():
    # Replace placeholder metrics with Prometheus/OpenTelemetry before production.
    return {
        "requests_total": 0,
        "cache_hits": 0,
        "cache_hit_rate": 0.0,
        "average_latency_ms": None,
        "p95_latency_ms": None,
        "estimated_cost_saved_usd": 0.0,
        "tool_call_success_rate": None,
        "pending_approvals": None,
        "note": (
            "Metrics backend not yet wired; instrument with Prometheus/OpenTelemetry in deployment."
        ),
    }
