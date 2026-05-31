# Skill: Voucher Code Extraction
**Used by:** `search.py` → `extract_codes_from_text()` — called after Brave Search
and Reddit return raw text snippets. Claude Haiku reads this skill before parsing.

---

## What this skill teaches

How to reliably extract discount codes from unstructured text — blog posts,
Reddit threads, search snippets, and HTML page content — without false positives.

---

## Code patterns to recognise

Valid voucher codes typically match these patterns:

```
[A-Z0-9]{4,16}          # Pure alphanumeric: SUMMER18, FLASH20, AY9OFF
[A-Z]+-[A-Z0-9]+        # Hyphenated: SAVE-10, EXTRA-20OFF
[A-Z0-9]+-[0-9]{4}      # With year: PROMO-2025 (check if year is current)
```

Common surrounding phrases that signal a code:
- "use code **X**"
- "promo code: **X**"
- "discount code **X**"
- "coupon **X**"
- "enter **X** at checkout"
- "copy code **X**"

---

## Rules for extraction

**Include:**
- Codes 4–16 characters long
- Mixed or all-caps alphanumeric
- Codes with hyphens if the pattern is recognisable
- Codes mentioned alongside a discount value (10%, €5 off, free shipping)

**Exclude:**
- Order IDs (too long, usually 20+ chars)
- Random strings with no surrounding discount context
- Codes containing the current year minus 2 or more (e.g. `DEAL2022` in 2025 = expired)
- URLs, email addresses, product SKUs
- Codes shorter than 4 characters

---

## Confidence scoring

Assign a confidence score (0.0–1.0) to each extracted code:

| Signal | Score boost |
|---|---|
| Appears on multiple sources | +0.20 |
| Accompanied by explicit % or € discount value | +0.15 |
| Posted within last 7 days | +0.10 |
| Contains merchant name fragment | +0.10 |
| Accompanied by expiry date | +0.05 |
| Year in code matches current year | +0.10 |
| Year in code is 2+ years ago | −0.40 |
| Only appears once, no context | −0.10 |

---

## Output format

Always return a JSON array. Never return prose.

```json
[
  {
    "code": "SUMMER18",
    "discount_hint": "18% off",
    "source": "reddit",
    "confidence": 0.85,
    "expires": "2025-07-01"
  },
  {
    "code": "FLASH5",
    "discount_hint": "€5 off",
    "source": "brave_search",
    "confidence": 0.60,
    "expires": null
  }
]
```

---

## Common mistakes to avoid

- Do not extract product names that look like codes (e.g. "NIKE AIR MAX")
- Do not confuse tracking IDs with discount codes
- Do not include codes from clearly satirical or outdated content
- If the same code appears in multiple snippets, include it once with `source_count` incremented
