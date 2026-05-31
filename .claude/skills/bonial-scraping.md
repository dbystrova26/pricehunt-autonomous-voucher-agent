# Skill: Bonial / kaufDA Leaflet Scraping
**Status:** ⏭ Future milestone — `bonial.py` currently returns `None`. This skill documents the implementation plan.
**Used by:** `bonial.py` → `get_bonial_deals()` — called by the agent's
`run_tools_node` when `include_bonial: true` in the plan.

---

## What this skill teaches

How to extract current in-store promotional deals from kaufDA.de (Bonial Germany)
and surface them alongside online voucher codes as enrichment data.

---

## What Bonial / kaufDA is

Bonial International GmbH (Berlin) operates:
- **kaufDA.de** — Germany's leading digital leaflet platform (10M+ downloads)
- **Bonial.fr** — French equivalent
- **MeinProspekt.de** — secondary DE aggregator

These platforms aggregate weekly promotional PDFs ("Prospekte") from 500+ EU
retailers including Zalando, H&M, MediaMarkt, Aldi, Lidl, and Kaufland.

This is **fundamentally different** from online voucher codes:
- Codes = discount at online checkout
- Bonial = in-store promotional pricing valid this week

Combining both = Pricehunt's main differentiator over Honey/Joko.

---

## Target URLs

```python
BASE_URLS = {
    "de": "https://www.kaufda.de",
    "fr": "https://www.bonial.fr",
}

# Search for a merchant's current leaflet
SEARCH_URL = "https://www.kaufda.de/suche/{merchant_slug}"

# Example: Zalando leaflets
# https://www.kaufda.de/suche/zalando
```

---

## Scraping flow

```
1. GET kaufda.de/suche/{merchant}
2. Find leaflet cards in search results
3. Extract: retailer name, offer headline, discount %, validity dates
4. Return structured deal summary
```

### Key selectors on kaufDA (as of 2025)

```python
# Leaflet cards
LEAFLET_CARD = '[data-testid="leaflet-card"]'
# Fallback
LEAFLET_CARD_FB = '.brochure-card, .leaflet-item'

# Offer headline inside card
OFFER_TEXT = '[data-testid="leaflet-title"], .brochure-title'

# Validity dates
VALIDITY = '[data-testid="validity-period"], .validity-period'

# Discount badge
DISCOUNT_BADGE = '.discount-badge, [class*="discount"]'
```

---

## Output format

```python
{
    "merchant": "Zalando",
    "source": "kaufDA",
    "deal_summary": "Jeans –20% in-store until Sunday",
    "deals": [
        {
            "title": "Jeans & Denim –20%",
            "discount": "20%",
            "valid_until": "2025-07-06",
            "in_store": True,
            "online": False,
        }
    ],
    "leaflet_url": "https://www.kaufda.de/...",
    "scraped_at": "2025-06-01T10:00:00Z"
}
```

---

## Caching strategy

Bonial data changes weekly — cache with a **24-hour TTL**, not 6h like codes.

```python
BONIAL_CACHE_TTL = 60 * 60 * 24   # 24 hours
KEY = f"bonial:{merchant.lower()}"
```

---

## Partnership alternative

For production use, contact **partner@bonial.com** to request structured
feed access. This avoids scraping entirely and provides:
- Machine-readable JSON feed of all current offers
- Push updates when new leaflets go live
- Full retailer catalogue with merchant IDs

For MVP / student project, scraping kaufDA.de is acceptable.

---

## Handling missing merchants

Not every merchant has a Bonial leaflet. Return gracefully:

```python
if not deals_found:
    return {
        "merchant": merchant,
        "deal_summary": None,   # UI hides the Bonial strip when None
        "deals": [],
    }
```
