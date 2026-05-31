# Tool: get_bonial_deals
**MCP Server:** `bonial-mcp-server`
**File:** `backend/tools/bonial.py`

---

## Description

Scrapes kaufDA.de (Bonial Germany) for the current week's in-store
promotional deals for a given merchant. Returns a human-readable
deal summary and structured offer data.

This tool is Pricehunt's key differentiator — it bridges **online discount codes**
with **offline in-store promotions**, something no other voucher tool does.

Use this tool when:
- `include_bonial: true` in the planner's plan
- Merchant is a known EU brick-and-mortar retailer
- User asks about in-store deals or nearby promotions

Skip this tool when:
- Merchant is online-only (e.g. a pure DTC brand)
- Merchant is non-EU
- Bonial cache is fresh (under 24 hours)

---

## Input schema

```json
{
  "merchant": "string — merchant name, e.g. H&M, MediaMarkt, Zalando",
  "location": "string optional — city for geo-relevant results, e.g. Frankfurt"
}
```

---

## Output schema

```json
{
  "merchant": "H&M",
  "source": "kaufDA",
  "deal_summary": "Summer collection –30% in-store until Sunday",
  "deals": [
    {
      "title": "Summer Collection –30%",
      "discount": "30%",
      "valid_from": "2025-06-02",
      "valid_until": "2025-06-08",
      "in_store": true,
      "online": false,
      "category": "Fashion"
    }
  ],
  "leaflet_url": "https://www.kaufda.de/...",
  "cached": false,
  "scraped_at": "2025-06-01T10:00:00Z"
}
```

If no deals found:
```json
{
  "merchant": "SomeNicheShop",
  "deal_summary": null,
  "deals": []
}
```

---

## UI behaviour

When `deal_summary` is not null, the React frontend renders the
**Bonial enrichment strip** below the voucher card:

```
📰  H&M: Summer collection –30% in-store until Sunday  [kaufDA]
```

When `deal_summary` is null, the strip is hidden entirely.

---

## Caching

Cache Bonial results for **24 hours** (not 6h like codes — leaflets change weekly).

```python
BONIAL_TTL = 60 * 60 * 24   # 24h
CACHE_KEY  = f"bonial:{merchant.lower()}"
```

---

## Read before implementing

See `.claude/skills/bonial-scraping.md` for:
- Full selector strategy for kaufDA.de
- Output format details
- Partnership contact for structured feed access
- Handling missing merchants gracefully
