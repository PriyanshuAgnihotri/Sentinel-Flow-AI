import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.routes.workflows import router
from app.core.config import settings
from app.db.session import engine
from app.services.cache import SemanticCache

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_deployment_security()
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


async def database_is_available() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("Database readiness check failed", exc_info=True)
        return False


@app.get("/ready")
async def ready():
    database_ok = await database_is_available()
    redis_ok = False

    redis = getattr(app.state, "redis", None)
    if redis:
        try:
            redis_ok = bool(await redis.ping())
        except Exception:
            logger.warning("Redis readiness check failed", exc_info=True)

    # PostgreSQL is required; Redis remains optional for the local demo.
    payload = {
        "status": "ready" if database_ok else "not_ready",
        "database": database_ok,
        "redis": redis_ok,
        "cache_enabled": getattr(app.state, "cache", None) is not None
        and redis_ok,
    }
    return payload if database_ok else JSONResponse(status_code=503, content=payload)


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
