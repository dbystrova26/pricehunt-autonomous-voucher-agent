"""
Bonial / kaufDA MCP tool server — EU in-store leaflet deals
Scrapes kaufDA.de for weekly in-store promotions near the user.
"""

async def get_bonial_deals(merchant: str, city: str = "Frankfurt") -> str | None:
    """
    Fetch current Bonial/kaufDA leaflet deals for a merchant in a city.
    Returns a short description string or None if no deals found.
    """
    # TODO: implement Playwright scraping of kaufda.de
    # Real implementation would:
    # 1. Navigate to kaufda.de/search?q={merchant}&city={city}
    # 2. Parse current leaflet deals
    # 3. Return the best offer as a short string
    # e.g. "Jeans –20% in-store until Sunday"

    return None

async def get_all_bonial_deals(city: str = "Frankfurt") -> list[dict]:
    """
    Fetch all current Bonial deals for a city across all merchants.
    Useful for enriching search results with nearby in-store offers.
    """
    # TODO: implement full kaufDA leaflet scraping
    return []
