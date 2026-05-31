# Tool: brave_search
**MCP Server:** `search-mcp-server`
**File:** `backend/tools/search.py`

---

## Description

Searches the web using the Brave Search API for voucher codes, promo deals,
and discount information for a given merchant. Returns ranked snippets that
are then passed to `extract_codes_from_text` for code parsing.

Use this tool when:
- The cache returned no codes
- RetailMeNot scrape returned fewer than 2 results
- The user explicitly asked to search the web
- The merchant is a newer or niche brand not on aggregators

Do NOT use this tool when:
- The cache has high-confidence results from the last 6 hours
- The merchant history shows search has 0% hit rate for this brand

---

## Input schema

```json
{
  "query": "string",
  "count": "integer (default: 10, max: 20)"
}
```

### Query writing guide

Write queries that maximise finding actual codes, not brand homepages:

```python
# Good queries
f"{merchant} promo code {current_year}"
f"{merchant} discount code site:reddit.com"
f"{merchant} voucher code working {current_month}"

# Bad queries (too generic)
f"{merchant} discount"
f"{merchant} deals"
```

---

## Output schema

```json
{
  "snippets": [
    "Use code SUMMER18 at Zalando for 18% off your order...",
    "Verified: WELCOME10 still working as of June 2025..."
  ],
  "urls": [
    "https://www.retailmenot.com/view/zalando.de",
    "https://reddit.com/r/deals/comments/..."
  ],
  "query_used": "Zalando promo code June 2025"
}
```

---

## Implementation

```python
import httpx
import os

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

async def brave_search(query: str, count: int = 10) -> dict:
    """
    Search Brave for voucher codes. Returns snippets for code extraction.
    Rate limit: 1 req/sec on free tier (2,000/month).
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            BRAVE_ENDPOINT,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
            params={"q": query, "count": count},
            timeout=8.0,
        )
        data = response.json()

    snippets = [
        r.get("description", "")
        for r in data.get("web", {}).get("results", [])
        if r.get("description")
    ]
    urls = [
        r.get("url", "")
        for r in data.get("web", {}).get("results", [])
    ]

    return {"snippets": snippets, "urls": urls, "query_used": query}
```

---

## Error handling

| Error | Cause | Action |
|---|---|---|
| 429 Too Many Requests | Rate limit hit | Wait 1s, retry once |
| 401 Unauthorized | Invalid API key | Log error, skip tool |
| Empty results | No indexed pages | Return empty snippets, try reddit_search |
