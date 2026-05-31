# Tool: scrape_retailmenot
**MCP Server:** `scraper-mcp-server`
**File:** `backend/tools/scraper.py`

---

## Description

Scrapes RetailMeNot for publicly listed voucher codes for a given merchant.
RetailMeNot is the largest English-language coupon aggregator and typically
has the highest hit rate for fashion and electronics merchants.

Also used as the template pattern for scraping Honey and Idealo — same
function signature, different target URL and selector set.

Use this tool when:
- No valid codes in cache
- First run for this merchant
- Planner history shows RetailMeNot as best source for this category

---

## Target URL pattern

```python
# RetailMeNot
URL = "https://www.retailmenot.com/view/{merchant_domain}"
# e.g. https://www.retailmenot.com/view/zalando.de

# Honey / Joinhoney
URL = "https://www.joinhoney.com/shop/{merchant_slug}"

# Idealo (EU-focused)
URL = "https://www.idealo.de/gutscheine/{merchant_slug}"
```

---

## Input schema

```json
{
  "merchant": "string — merchant name or domain, e.g. zalando or zalando.de"
}
```

---

## Output schema

```json
[
  {
    "code": "SUMMER18",
    "discount_hint": "18% off sitewide",
    "source": "retailmenot",
    "confidence": 0.75,
    "expires": "2025-07-01",
    "success_rate": "72%"
  }
]
```

---

## Key selectors (RetailMeNot, as of 2025)

```python
# Coupon cards on the page
COUPON_CARD      = '[data-id*="coupon"], .coupon-card, [class*="offerCard"]'

# Code reveal button (some codes are hidden behind a click)
REVEAL_BTN       = 'button:has-text("Get Code"), button:has-text("Show Code")'

# Code value after reveal
CODE_VALUE       = '[class*="code"], [data-testid*="code"], code'

# Discount description
DISCOUNT_DESC    = '[class*="description"], [class*="title"], h3'

# Expiry
EXPIRY           = '[class*="expir"], [class*="valid"]'

# Success rate badge
SUCCESS_RATE     = '[class*="success"], [class*="worked"]'
```

---

## Implementation sketch

```python
from playwright.async_api import async_playwright
import re

async def scrape_retailmenot(merchant: str) -> list[dict]:
    """
    Scrapes RetailMeNot for merchant codes.
    Read .claude/skills/checkout-validation.md for anti-bot notes.
    """
    domain = merchant.lower().replace(" ", "") + ".de"
    url = f"https://www.retailmenot.com/view/{domain}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # Set realistic user-agent to reduce bot detection
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

        codes = []
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=8000)
            cards = await page.query_selector_all(COUPON_CARD)

            for card in cards[:10]:   # cap at 10 cards
                code = await _extract_code_from_card(page, card)
                if code:
                    codes.append(code)

        except Exception as e:
            print(f"RetailMeNot scrape failed: {e}")
        finally:
            await browser.close()

    return codes
```

---

## Anti-bot notes

RetailMeNot occasionally serves a challenge page. Signs:
- Page title contains "Access Denied" or "Checking your browser"
- Response is under 1KB (probably a challenge redirect)

If this happens:
1. Add a 1–2 second delay before scraping
2. Rotate user-agent strings
3. Fall back to Brave Search for this merchant in this session
4. If persistent, route through Browserbase (see `.claude/tools/code-validator.md`)
