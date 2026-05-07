# backend/app/services/cache.py
"""
Redis cache wrapper.

Usage:
    from app.services.cache import cache

    text = await cache.get("company:https://example.com")
    if text is None:
        text = expensive_fetch()
        await cache.set("company:https://example.com", text, ttl=86400)

All values are stored as plain strings.
If Redis is unavailable the methods silently no-op — the app degrades
gracefully to uncached behaviour.

TTL conventions (seconds):
  86 400  =  24 h  — company website text (changes rarely)
  43 200  =  12 h  — prospect search results (social profiles update more often)
"""
from __future__ import annotations

import os

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# redis.asyncio is only available when the `redis` package (≥4.2) is installed.
# We lazy-import so the rest of the app boots even when Redis is absent.
try:
    import redis.asyncio as aioredis
    _client: aioredis.Redis | None = aioredis.from_url(
        _REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
    )
except Exception:
    _client = None


class _Cache:
    async def get(self, key: str) -> str | None:
        if _client is None:
            return None
        try:
            return await _client.get(key)
        except Exception:
            return None

    async def set(self, key: str, value: str, ttl: int = 86_400) -> None:
        if _client is None:
            return
        try:
            await _client.set(key, value, ex=ttl)
        except Exception:
            pass

    async def delete(self, key: str) -> None:
        if _client is None:
            return
        try:
            await _client.delete(key)
        except Exception:
            pass


cache = _Cache()
