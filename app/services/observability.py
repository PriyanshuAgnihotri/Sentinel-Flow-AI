from uuid import uuid4
from app.core.config import settings

def trace_ids() -> tuple[str, str]:
    return str(uuid4()), str(uuid4())

def observe(name: str, request_id: str, metadata: dict | None = None):
    """Best-effort Langfuse span; the API stays usable when telemetry is not configured."""
    try:
        if not (settings.langfuse_public_key and settings.langfuse_secret_key): return None
        from langfuse import Langfuse
        client = Langfuse(public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key, host=settings.langfuse_host)
        return client.start_span(name=name, metadata={"request_id": request_id, **(metadata or {})})
    except Exception:
        return None
