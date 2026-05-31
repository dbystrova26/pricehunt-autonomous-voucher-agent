# Tool: validate_code_at_checkout
**MCP Server:** `validator-mcp-server`
**File:** `backend/tools/validator.py`
**Status:** ⏭ Mock implementation — uses heuristics, not real Playwright checkout.

---

## Current implementation

The validator uses a heuristic scoring model — it does NOT visit real checkouts:

```python
def _estimate_saving(merchant: str, code: str) -> tuple[bool, float]:
    # Penalise obviously old codes (year patterns like 2022)
    # Score by merchant category savings range
    # Apply 70% pass rate for realistic demo results
    valid = random.random() > 0.3
    saving = round(random.uniform(min_s, max_s), 2)
    return valid, saving
```

This means codes shown as "validated" are scored estimates, not confirmed
at real checkouts. The agent discloses this honestly when asked about confidence.

---

## What this tool will do when implemented

Use a headless Playwright browser to apply a discount code to a real merchant
checkout page and measure the actual price delta. This is what makes Pricehunt
genuinely different from every static coupon site.

---

## Input schema

```json
{
  "merchant_url": "string — full checkout URL or homepage",
  "code": "string — the voucher code to test"
}
```

## Output schema

```json
{
  "code": "SUMMER18",
  "valid": true,
  "saving_eur": 18.00,
  "confidence": 0.95,
  "error": null
}
```

---

## Implementation plan (future)

```python
from playwright.async_api import async_playwright

async def validate_code_at_checkout(merchant_url: str, code: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(merchant_url)
        original = await _read_total(page)
        await _apply_code(page, code)
        discounted = await _read_total(page)
        saving = round(original - discounted, 2)
        return {"code": code, "valid": saving > 0, "saving_eur": saving}
```

Start with one merchant (ASOS or About You — simpler checkout flows).
Add anti-detection, then generalise.

## Read also
`.claude/skills/checkout-validation.md` — full selector strategy per merchant.
