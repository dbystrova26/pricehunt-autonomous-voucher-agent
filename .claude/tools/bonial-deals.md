# Tool: get_bonial_deals
**MCP Server:** `bonial-mcp-server`
**File:** `backend/tools/bonial.py`
**Status:** ⏭ Stub — returns `None`. Real kaufDA scraping is a future milestone.

---

## Current implementation

```python
async def get_bonial_deals(merchant: str, city: str = "Frankfurt") -> str | None:
    # TODO: implement Playwright scraping of kaufda.de
    return None
```

The agent currently answers Frankfurt in-store questions using Claude's built-in
knowledge of EU retailers. When asked directly, it honestly discloses it did not
query kaufDA in real time.

---

## What this tool will do when implemented

Scrape kaufDA.de for the current week's in-store promotional deals for a given
merchant, returning a human-readable deal summary alongside online voucher codes.

This would be Pricehunt's key differentiator — bridging online discount codes
with offline in-store promotions.

---

## Target URL pattern

```python
SEARCH_URL = "https://www.kaufda.de/suche/{merchant_slug}"
```

---

## Output schema (future)

```json
{
  "merchant": "H&M",
  "source": "kaufDA",
  "deal_summary": "Summer collection –30% in-store until Sunday",
  "deals": [
    {
      "title": "Summer Collection –30%",
      "discount": "30%",
      "valid_until": "2025-07-06",
      "in_store": true,
      "online": false
    }
  ],
  "leaflet_url": "https://www.kaufda.de/..."
}
```

If no deals found: `{ "deal_summary": null, "deals": [] }`

---

## Partnership alternative

Contact **partner@bonial.com** for structured feed access instead of scraping.
Provides machine-readable JSON feed, push updates, and full retailer catalogue.

## Read also
`.claude/skills/bonial-scraping.md` — full selector strategy and implementation plan.
