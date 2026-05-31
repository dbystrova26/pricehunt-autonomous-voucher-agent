# Tool: scrape_retailmenot / scrape_honey / scrape_idealo
**MCP Server:** `scraper-mcp-server`
**File:** `backend/tools/scraper.py`
**Status:** ⏭ Stub — all three functions return `[]`. Real Playwright scraping is a future milestone.

---

## Current implementation

```python
async def scrape_retailmenot(merchant: str) -> list[dict]:
    # TODO: implement Playwright scraping of retailmenot.com
    return []

async def scrape_honey(merchant: str) -> list[dict]:
    # TODO: implement Playwright scraping of joinhoney.com
    return []

async def scrape_idealo(merchant: str) -> list[dict]:
    # TODO: implement Playwright scraping of idealo.de
    return []
```

Codes currently found by the agent come from **Tavily Search** only,
not from these scrapers.

---

## What these tools will do when implemented

Scrape RetailMeNot, Honey, and Idealo for publicly listed voucher codes
by loading their pages with a headless Playwright browser and parsing the HTML.

---

## Target URL patterns

```python
# RetailMeNot
"https://www.retailmenot.com/view/{merchant_domain}"

# Honey
"https://www.joinhoney.com/shop/{merchant_slug}"

# Idealo (EU-focused)
"https://www.idealo.de/gutscheine/{merchant_slug}"
```

---

## Output schema (future)

```json
[
  {
    "code": "SUMMER18",
    "discount_hint": "18% off sitewide",
    "source": "retailmenot",
    "confidence": 0.75,
    "expires": "2025-07-01"
  }
]
```

---

## Key selectors (RetailMeNot, as of 2025)

```python
COUPON_CARD   = '[data-id*="coupon"], .coupon-card, [class*="offerCard"]'
REVEAL_BTN    = 'button:has-text("Get Code"), button:has-text("Show Code")'
CODE_VALUE    = '[class*="code"], [data-testid*="code"], code'
DISCOUNT_DESC = '[class*="description"], [class*="title"], h3'
```

## Anti-bot notes
RetailMeNot may serve challenge pages. Signs: title contains "Access Denied",
response under 1KB. Fix: add delay, rotate user-agent, fall back to Tavily.
