# Tool: reddit_search
**MCP Server:** `search-mcp-server`
**File:** `backend/tools/search.py`

---

## Description

Searches Reddit for fresh voucher codes using the Reddit API.
Targets deal-focused subreddits where users post codes before they
reach aggregators like RetailMeNot or Honey.

Reddit is often **24–48 hours ahead** of traditional coupon sites for:
- Flash sale codes posted by brand accounts
- Employee or insider codes shared in brand subreddits
- Limited-use codes that expire before scrapers index them

Use this tool when:
- Brave Search or scraping returned 0 codes
- The user explicitly asks to "search Reddit"
- The merchant is a direct-to-consumer brand with an active subreddit
- You need codes posted within the last 24 hours

---

## Target subreddits

```python
SUBREDDITS = [
    "deals",           # r/deals — general deal sharing
    "promo_codes",     # r/promo_codes — dedicated code sharing
    "frugal",          # r/frugal — budget-conscious shoppers
    "beermoney",       # sometimes has referral + promo codes
]

# Also search merchant-specific subreddits when they exist
# e.g. r/Zalando, r/nikerunning
MERCHANT_SUBREDDIT_PATTERN = "r/{merchant_slug}"
```

---

## Input schema

```json
{
  "merchant": "string — merchant name, e.g. Zalando",
  "days_back": "integer (default: 7) — only return posts from last N days",
  "limit": "integer (default: 25)"
}
```

---

## Output schema

```json
{
  "snippets": [
    "[WORKING] Zalando SUMMER18 — 18% off, confirmed today",
    "Has anyone tried ZLFRESH20? Just posted in r/deals"
  ],
  "posts": [
    {
      "title": "[CODE] Zalando 18% off — SUMMER18",
      "subreddit": "deals",
      "score": 142,
      "created_utc": 1717200000,
      "url": "https://reddit.com/r/deals/comments/..."
    }
  ]
}
```

---

## Implementation

```python
import httpx
import os
import time

REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT    = "pricehunt-agent/1.0 (Ironhack project)"

async def _get_reddit_token() -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": REDDIT_USER_AGENT},
        )
        return r.json()["access_token"]

async def reddit_search(merchant: str, days_back: int = 7, limit: int = 25) -> dict:
    token = await _get_reddit_token()
    cutoff = int(time.time()) - (days_back * 86400)

    snippets, posts = [], []

    for subreddit in ["deals", "promo_codes"]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://oauth.reddit.com/r/{subreddit}/search",
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": REDDIT_USER_AGENT,
                },
                params={
                    "q": merchant,
                    "sort": "new",
                    "limit": limit,
                    "restrict_sr": "true",
                },
                timeout=6.0,
            )
            for post in r.json().get("data", {}).get("children", []):
                d = post["data"]
                if d.get("created_utc", 0) < cutoff:
                    continue
                snippets.append(f"{d['title']} — {d.get('selftext', '')[:200]}")
                posts.append({
                    "title": d["title"],
                    "subreddit": subreddit,
                    "score": d.get("score", 0),
                    "created_utc": d.get("created_utc"),
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                })

    return {"snippets": snippets, "posts": posts}
```

---

## Scoring boost

Posts from Reddit with score > 50 get a +0.10 confidence boost on
extracted codes — high upvotes signal community verification.
