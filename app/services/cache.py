
import hashlib
import json

from redis.asyncio import Redis

from app.core.config import settings


class SemanticCache:
    """Redis cache restricted to exact requests within a user scope."""

    @staticmethod
    def _key(text: str, user_id: str) -> str:
        user_hash = hashlib.sha256(user_id.encode()).hexdigest()
        request_hash = hashlib.sha256(text.strip().encode()).hexdigest()
        return f"sf:cache:v2:{user_hash}:{request_hash}"

    async def lookup(self, text: str, user_id: str) -> dict | None:
        raw = await self.redis.get(self._key(text, user_id))
        if not raw:
            return None

        item = json.loads(raw)
        return {**item["response"], "cache_hit": True}

    def __init__(self, redis: Redis):
        self.redis = redis

    async def store(self, text: str, user_id: str, response: dict) -> None:
        # Never cache escalations, blocked actions, or approval-related results.
        if (
            response.get("escalation_required")
            or response.get("blocked_actions")
            or response.get("approval_id")
        ):
            return

        item = {"response": response}
        await self.redis.set(
            self._key(text, user_id),
            json.dumps(item),
            ex=settings.semantic_cache_ttl_seconds,
        )
