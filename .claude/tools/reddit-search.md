# Tool: reddit_search
**MCP Server:** `search-mcp-server`
**File:** `backend/tools/search.py`
**Status:** ⏭ Stub — returns `[]`. Reddit API access blocked by 2026 Responsible Builder Policy.

---

## Current implementation

```python
async def reddit_search(query: str, subreddits: list[str] = None) -> list[dict]:
    # Reddit introduced Responsible Builder Policy in 2026 blocking new apps
    return []
```

Tavily Search partially covers Reddit as it indexes Reddit pages in web results.

---

## What this tool will do when access is granted

Search r/deals, r/promo_codes, r/frugal and merchant-specific subreddits
for codes posted within the last 7 days. Reddit is often 24–48 hours ahead
of aggregators for flash sale codes.

---

## Why Reddit access is blocked

Reddit's [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564)
introduced in 2026 requires explicit approval before creating API apps.
The approval flow was not completed during development.

---

## What Reddit would add (per agent's own analysis)

| Signal | Without Reddit | With Reddit |
|---|---|---|
| Code freshness | Unknown | Post timestamp |
| User verification | None | "Worked for me!" replies |
| Failure reports | Hidden | "Expired" warnings |
| Regional validity | Unknown | Users mention country |

Only surface codes with upvotes + positive replies in last 7 days.

---

## Target subreddits (future)

```python
SUBREDDITS = ["deals", "promo_codes", "frugal", "einkaufen"]
```

## Implementation plan

```python
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")

async def reddit_search(merchant: str, days_back: int = 7) -> list[dict]:
    token = await _get_reddit_token()
    # Search r/deals, r/promo_codes for merchant + code keywords
    # Filter by post age (cutoff = now - days_back * 86400)
    # Boost confidence for posts with score > 50
```
