"""
Pricehunt — Memory layer
Redis for hot code cache · Postgres for historical run data
"""

import os
import json
from typing import Optional

# In production these use actual Redis/Postgres clients.
# For local dev they fall back to in-memory dicts.
REDIS_URL = os.getenv("REDIS_URL", "")
HAS_REDIS = bool(REDIS_URL)
_redis = None

if HAS_REDIS:
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(REDIS_URL)
    except Exception:
        _redis = None
        HAS_REDIS = False

_local_cache: dict = {}         # fallback for local dev
_run_log: list = []             # fallback run history


# ── Redis helpers ──────────────────────────────────────────────────────────────

async def _rget(key: str) -> Optional[str]:
    if HAS_REDIS:
        return await _redis.get(key)
    return _local_cache.get(key)


async def _rset(key: str, value: str, ttl: int = 21600):  # 6h default
    if HAS_REDIS:
        await _redis.setex(key, ttl, value)
    else:
        _local_cache[key] = value


# ── Public API ─────────────────────────────────────────────────────────────────

async def get_cached_codes(merchant: str) -> dict:
    """
    Returns previously validated codes for a merchant if they exist in cache.
    TTL is 6 hours — codes are considered stale after that.
    """
    key = f"codes:{merchant.lower()}"
    raw = await _rget(key)
    if raw:
        return {"codes": json.loads(raw), "from_cache": True}
    return {"codes": [], "from_cache": False}


async def write_validated_code(
    merchant: str,
    code: str,
    saving_eur: float,
    source: Optional[str] = None,
    ttl: int = 21600,
):
    """
    Writes a confirmed working code to Redis.
    The planner reads this on the next run to skip re-validation.
    """
    key = f"codes:{merchant.lower()}"
    raw = await _rget(key)
    existing = json.loads(raw) if raw else []

    # Upsert — replace if code already present
    existing = [c for c in existing if c.get("code") != code]
    existing.append({
        "code": code,
        "saving_eur": saving_eur,
        "source": source or "unknown",
        "confidence": 0.9,  # validated = high confidence
    })

    await _rset(key, json.dumps(existing), ttl=ttl)


async def get_merchant_history(merchant: str) -> dict:
    """
    Returns aggregated stats for a merchant based on past runs.
    The planner uses this to decide which tools to call.

    Returns:
        {
            "best_source": "retailmenot",
            "hit_rate": 0.8,
            "avg_saving": 14.5,
            "failed_tools": ["search"],
            "runs": 5,
        }
    """
    key = f"history:{merchant.lower()}"
    raw = await _rget(key)
    if raw:
        return json.loads(raw)
    return {}


async def write_run_result(
    merchant: str,
    tools_used: list[str],
    codes_found: int,
    best_saving: float,
):
    """
    Logs the result of a run. Updates the rolling hit-rate stats
    the planner reads on future calls.
    """
    key = f"history:{merchant.lower()}"
    raw = await _rget(key)
    history = json.loads(raw) if raw else {
        "runs": 0,
        "total_codes": 0,
        "total_saving": 0.0,
        "source_hits": {},
        "failed_tools": [],
    }

    history["runs"] = history.get("runs", 0) + 1
    history["total_codes"] = history.get("total_codes", 0) + codes_found
    history["total_saving"] = history.get("total_saving", 0.0) + best_saving
    history["avg_saving"] = history["total_saving"] / history["runs"]
    history["hit_rate"] = history["total_codes"] / history["runs"]

    if codes_found > 0 and tools_used:
        best_tool = tools_used[0]
        sc = history.get("source_hits", {})
        sc[best_tool] = sc.get(best_tool, 0) + 1
        history["source_hits"] = sc
        history["best_source"] = max(sc, key=sc.get)

    # Keep a TTL of 30 days on history
    await _rset(key, json.dumps(history), ttl=60 * 60 * 24 * 30)

    _run_log.append({
        "merchant": merchant,
        "tools": tools_used,
        "codes_found": codes_found,
        "best_saving": best_saving,
    })


async def get_merchant_stats(merchant: str) -> dict:
    """
    Returns merchant history stats for the /merchants/{merchant}/stats endpoint.
    Alias for get_merchant_history with a friendlier response shape.
    """
    key = f"history:{merchant.lower()}"
    raw = await _rget(key)
    if raw:
        data = json.loads(raw)
        return {
            "merchant": merchant,
            "runs": data.get("runs", 0),
            "best_source": data.get("best_source", "unknown"),
            "hit_rate": round(data.get("hit_rate", 0.0), 2),
            "avg_saving": round(data.get("avg_saving", 0.0), 2),
        }
    return None
