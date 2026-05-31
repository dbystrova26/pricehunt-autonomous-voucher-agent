"""
Cache MCP tool server — Redis code cache
Gracefully falls back to no-op when Redis is not available.
"""
import os
import json

try:
    import redis.asyncio as aioredis
    _redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    HAS_REDIS = True
except Exception:
    _redis = None
    HAS_REDIS = False

CACHE_TTL = 60 * 60 * 6  # 6 hours

async def get_cached_codes(merchant: str) -> list[dict]:
    """Return cached validated codes for a merchant, or empty list."""
    if not HAS_REDIS or not _redis:
        return []
    try:
        key = f"codes:{merchant.lower()}"
        data = await _redis.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"Cache read error: {e}")
    return []

async def write_validated_code(merchant: str, codes: list[dict]) -> None:
    """Cache validated codes for a merchant with 6h TTL."""
    if not HAS_REDIS or not _redis:
        return
    try:
        key = f"codes:{merchant.lower()}"
        await _redis.setex(key, CACHE_TTL, json.dumps(codes))
    except Exception as e:
        print(f"Cache write error: {e}")

async def get_merchant_history(merchant: str) -> dict:
    """Return agent run history for a merchant (hit rates per source)."""
    if not HAS_REDIS or not _redis:
        return {}
    try:
        key = f"history:{merchant.lower()}"
        data = await _redis.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"History read error: {e}")
    return {}

async def write_merchant_history(merchant: str, history: dict) -> None:
    """Update agent run history for a merchant."""
    if not HAS_REDIS or not _redis:
        return
    try:
        key = f"history:{merchant.lower()}"
        await _redis.set(key, json.dumps(history))
    except Exception as e:
        print(f"History write error: {e}")
