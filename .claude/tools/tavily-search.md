# Tool: tavily_search
**MCP Server:** `search-mcp-server`
**File:** `backend/tools/search.py`

---

## Description

Searches the web using the Tavily Search API for voucher codes, promo deals,
and discount information for a given merchant. Returns ranked snippets that
are then passed to `extract_codes_from_text` for code parsing.

Tavily is built specifically for AI agents — unlike general search APIs it
returns clean, LLM-optimised snippets with no SEO noise, directly structured
for downstream extraction.

Use this tool when:
- The cache returned no codes
- RetailMeNot scrape returned fewer than 2 results
- The user explicitly asked to search the web
- The merchant is a newer or niche brand not on aggregators

Do NOT use this tool when:
- The cache has high-confidence results from the last 6 hours
- The merchant history shows search has 0% hit rate for this brand

---

## Why Tavily over Brave Search

| | Tavily | Brave Search |
|---|---|---|
| Free tier | 1,000 req/mo — genuinely free, no credit card | $5 credit/mo (~1,000 req) — requires billing setup |
| Built for AI agents | ✅ Yes — responses pre-structured for LLMs | ❌ No — raw web results |
| Snippet quality | Clean, deduplicated, relevant | Raw HTML snippets, more noise |
| Setup | `pip install tavily-python` + API key | Custom HTTP client + auth headers |
| SDK | Official Python SDK | No official SDK |
| Rate limit | 1 req/sec free tier | 1 req/sec free tier |

The decisive factor: Tavily requires zero credit card details to get 1,000 free
requests per month. Brave requires billing setup even for the free credit tier.
For an open-source MVP, removing payment friction matters.

---

## Input schema

```json
{
  "query": "string",
  "max_results": "integer (default: 5)"
}
```

### Query writing guide

Write queries that maximise finding actual codes, not brand homepages:

```python
# Good queries
f"{merchant} promo code {current_year}"
f"{merchant} discount code site:reddit.com"
f"{merchant} voucher code working {current_month}"

# Bad queries (too generic — return brand homepages)
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
import os
from tavily import TavilyClient

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
_client = TavilyClient(api_key=TAVILY_API_KEY)

async def tavily_search(query: str, max_results: int = 5) -> dict:
    """
    Search Tavily for voucher codes.
    Returns LLM-optimised snippets ready for extract_codes_from_text().
    Rate limit: 1 req/sec on free tier (1,000/month).
    """
    import asyncio

    # Tavily SDK is synchronous — run in thread pool to stay async
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: _client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",   # deeper crawl, better for finding codes
            include_answer=False,      # we want raw snippets, not a synthesised answer
        )
    )

    snippets = [r.get("content", "") for r in response.get("results", [])]
    urls     = [r.get("url", "")     for r in response.get("results", [])]

    return {"snippets": snippets, "urls": urls, "query_used": query}
```

---

## Installation

```bash
# Inside the virtual environment
pip install tavily-python==0.3.9
```

Get your free API key:
1. Go to https://app.tavily.com
2. Sign up — no credit card required
3. Dashboard → API Keys → Create key

```
TAVILY_API_KEY=tvly-...
```

Free tier: **1,000 searches/month**. At 2–3 queries per agent run that covers
~300–500 full searches before any charge — well above MVP needs.

---

## Error handling

| Error | Cause | Action |
|---|---|---|
| `InvalidAPIKeyError` | Wrong or missing key | Log error, skip tool this run |
| `UsageLimitExceeded` | Monthly quota hit | Log warning, skip tool, rely on scraper |
| `httpx.TimeoutException` | Network timeout | Retry once after 1s |
| Empty results | No indexed pages for query | Return empty snippets, try reddit_search |
