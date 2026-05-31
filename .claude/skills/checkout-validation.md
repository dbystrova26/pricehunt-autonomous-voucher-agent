# Skill: Checkout Validation with Playwright
**Status:** ⏭ Future milestone — `validator.py` currently uses heuristics (70% mock pass rate). This skill documents the real Playwright implementation plan.
**Used by:** `validator.py` → `validate_code_at_checkout()` — called for each
candidate code before returning results to the user.

---

## What this skill teaches

How to programmatically apply a discount code to a merchant's checkout page
using a headless Playwright browser and reliably read the resulting price delta.

---

## General validation flow

```
1. Navigate to merchant cart URL
2. Add a dummy product (if cart is empty)
3. Locate the promo code input field
4. Type the code and submit
5. Read the new total or discount line
6. Calculate saving = original_price - new_price
7. Return {valid, saving_eur, error_message}
```

---

## Selector strategies (in order of reliability)

Try these selectors in order. Stop at the first one that works.

### Promo code input field
```python
selectors = [
    'input[name*="coupon"]',
    'input[name*="promo"]',
    'input[name*="discount"]',
    'input[placeholder*="code" i]',
    'input[placeholder*="coupon" i]',
    'input[aria-label*="promo" i]',
    '[data-testid*="coupon"]',
    '[data-testid*="promo"]',
]
```

### Submit / apply button
```python
submit_selectors = [
    'button[type="submit"]:near(input[name*="coupon"])',
    'button:has-text("Apply")',
    'button:has-text("Redeem")',
    'button:has-text("Add code")',
    '[data-testid*="apply"]',
]
```

### Discount / saving amount
```python
discount_selectors = [
    '[data-testid*="discount"]',
    '[class*="discount"]',
    '[class*="saving"]',
    '[class*="promo"]',
    'text=/−€[\d.]+/',       # regex match on price delta
    'text=/−[\d.]+€/',
    'text=/-[\d]+%/',
]
```

---

## Reading the price delta

After applying the code, compare the order total before and after:

```python
async def get_price(page) -> float:
    # Try structured total elements first
    for sel in ['[data-testid="order-total"]', '.order-total', '#cart-total']:
        el = page.locator(sel).first
        if await el.is_visible():
            text = await el.inner_text()
            return parse_price(text)
    # Fallback: find any element containing €
    return None

def parse_price(text: str) -> float:
    # Strip currency symbols and parse
    import re
    match = re.search(r'[\d]+[.,][\d]{2}', text.replace(',', '.'))
    return float(match.group()) if match else 0.0
```

---

## Error handling

| Error type | How to detect | What to return |
|---|---|---|
| Code not found / invalid | Error message appears near input | `{valid: false, error: "invalid_code"}` |
| Code already used | "already redeemed" message | `{valid: false, error: "already_used"}` |
| Minimum order not met | "minimum order" message | `{valid: false, error: "min_order"}` |
| Input field not found | Selector timeout | `{valid: false, error: "selector_timeout"}` |
| Anti-bot block | CAPTCHA or redirect | `{valid: false, error: "blocked"}` |

---

## Performance rules

- Set a **5 second timeout** per validation attempt — abort if exceeded
- Run validations in **parallel** for up to 3 codes at once
- Never validate more than **5 codes per merchant per run**
- Cache successful validations immediately — do not re-validate known working codes
- If `error: "blocked"` appears twice in a row → switch to Browserbase API

---

## Merchants with known selector quirks

| Merchant | Known issue | Workaround |
|---|---|---|
| Zalando | Cart requires login for full total | Use guest checkout URL |
| H&M | Promo input hidden behind accordion | Click "Add promo code" first |
| About You | SPA re-renders after code apply | Wait for network idle |
| MediaMarkt | Anti-bot on headless browsers | Use Browserbase |
