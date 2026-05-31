# Tool: validate_code_at_checkout
**MCP Server:** `validator-mcp-server`
**File:** `backend/tools/validator.py`

---

## Description

Uses a headless Playwright browser to apply a discount code to a real merchant
checkout page and measure the actual price delta. This is the most expensive
and most accurate tool in the pipeline.

**This is what makes Pricehunt different from every other coupon site.**
RetailMeNot just lists codes. Pricehunt *proves* they work at the real checkout.

Use this tool when:
- Candidate codes have been collected and deduplicated
- Confidence score is above 0.4 (below that, not worth the browser overhead)
- The code has not been validated for this merchant in the last 6 hours

Do NOT call this tool:
- More than 5 times per merchant per agent run
- For codes with patterns clearly indicating expiry (e.g. `XMAS2022`)
- If `error: "blocked"` was returned on the previous attempt without Browserbase

---

## Input schema

```json
{
  "merchant_url": "string — full checkout URL or homepage",
  "code": "string — the voucher code to test"
}
```

---

## Output schema

```json
{
  "code": "SUMMER18",
  "valid": true,
  "saving_eur": 18.00,
  "original_price": 99.00,
  "discounted_price": 81.00,
  "error": null
}
```

On failure:
```json
{
  "code": "EXPIRED22",
  "valid": false,
  "saving_eur": 0,
  "error": "invalid_code"
}
```

---

## Implementation sketch

```python
from playwright.async_api import async_playwright
import asyncio

async def validate_code_at_checkout(
    merchant_url: str,
    code: str,
    timeout_ms: int = 5000,
) -> dict:
    """
    Opens merchant cart in headless browser, applies code, reads saving.
    See .claude/skills/checkout-validation.md for full selector strategy.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(merchant_url, timeout=timeout_ms)
            original = await _read_total(page)

            # Find and fill promo input
            await _apply_code(page, code, timeout_ms)

            discounted = await _read_total(page)
            saving = round(original - discounted, 2)

            return {
                "code": code,
                "valid": saving > 0,
                "saving_eur": saving if saving > 0 else 0,
                "original_price": original,
                "discounted_price": discounted,
                "error": None if saving > 0 else "no_discount_applied",
            }

        except Exception as e:
            return {"code": code, "valid": False, "saving_eur": 0, "error": str(e)}

        finally:
            await browser.close()
```

---

## Latency expectations

| Merchant type | Expected latency |
|---|---|
| Fast SPA (About You, Zalando) | 2–4 seconds |
| Slower multi-page checkout | 4–7 seconds |
| Anti-bot detected, retrying | 8–12 seconds |
| Browserbase managed session | 3–6 seconds |

Target: validate 5 codes in parallel in under 8 seconds total.

---

## Related skill

Read `.claude/skills/checkout-validation.md` before implementing or
modifying this tool. It contains all selector strategies and merchant-specific quirks.
