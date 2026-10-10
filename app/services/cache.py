import json, hashlib
from redis.asyncio import Redis
from app.core.config import settings

class SemanticCache:
    """Redis-backed cosine cache. Embeddings are stored as JSON for portability; use Redis vector search at scale."""
    def __init__(self, redis: Redis):
        self.redis = redis
    @staticmethod
    def embed(text: str) -> list[float]:
        # Deterministic fallback embedding for offline demo. Replace with OpenAI embeddings in production.
        tokens = text.lower().split()
        vector = [0.0] * 128
        for token in tokens:
            idx = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % len(vector)
            vector[idx] += 1.0
        norm = sum(x*x for x in vector) ** 0.5 or 1.0
        return [x/norm for x in vector]
    async def lookup(self, text: str) -> dict | None:
        q = self.embed(text)
        keys = await self.redis.keys("sf:cache:*")
        best, best_score = None, 0.0
        for key in keys[:1000]:
            raw = await self.redis.get(key)
            if not raw: continue
            item = json.loads(raw); vec = item.get("embedding", [])
            score = sum(a*b for a,b in zip(q, vec)) if len(vec) == len(q) else 0.0
            if score > best_score: best, best_score = (item, key), score
        if best and best_score >= settings.semantic_cache_threshold:
            item, key = best
            item["cache_hit_count"] = item.get("cache_hit_count", 0) + 1
            await self.redis.set(key, json.dumps(item), ex=settings.semantic_cache_ttl_seconds)
            return {**item["response"], "cache_hit": True, "cache_similarity": best_score}
        return None
    async def store(self, text: str, response: dict) -> None:
        # Never cache approvals, destructive-action results, or escalations.
        if response.get("escalation_required") or response.get("blocked_actions"): return
        key = "sf:cache:" + hashlib.sha256(text.lower().strip().encode()).hexdigest()
        item = {"embedding": self.embed(text), "response": response, "model_version": settings.openai_model, "cache_hit_count": 0}
        await self.redis.set(key, json.dumps(item), ex=settings.semantic_cache_ttl_seconds)
