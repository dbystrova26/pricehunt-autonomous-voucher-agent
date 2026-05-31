"""
Scraper MCP tool server — RetailMeNot, Honey, Idealo
Stub implementation: returns empty list until real scraping is wired up.
Real implementation uses Playwright to load pages and parse HTML.
"""

async def scrape_retailmenot(merchant: str) -> list[dict]:
    """Scrape RetailMeNot for voucher codes for a given merchant."""
    # TODO: implement Playwright scraping of retailmenot.com
    return []

async def scrape_honey(merchant: str) -> list[dict]:
    """Scrape Honey/Joinhoney for voucher codes."""
    # TODO: implement Playwright scraping of joinhoney.com
    return []

async def scrape_idealo(merchant: str) -> list[dict]:
    """Scrape Idealo.de for deals and codes."""
    # TODO: implement Playwright scraping of idealo.de
    return []
