"""
Search MCP tool server — Tavily + Reddit
Tavily search is live. Reddit stub until API access is approved.
"""
import os
from tavily import TavilyClient

_tavily = None

def _get_tavily():
    global _tavily
    if _tavily is None:
        key = os.getenv("TAVILY_API_KEY")
        if key:
            _tavily = TavilyClient(api_key=key)
    return _tavily

async def tavily_search(query: str, max_results: int = 5) -> dict:
    """Search Tavily for voucher codes. Returns LLM-optimised snippets."""
    import asyncio
    client = _get_tavily()
    if not client:
        return {"snippets": [], "urls": [], "query_used": query}
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.search(
                query=query,
                max_results=max_results,
                search_depth="advanced",
                include_answer=False,
            )
        )
        snippets = [r.get("content", "") for r in response.get("results", [])]
        urls     = [r.get("url", "")     for r in response.get("results", [])]
        return {"snippets": snippets, "urls": urls, "query_used": query}
    except Exception as e:
        print(f"Tavily search error: {e}")
        return {"snippets": [], "urls": [], "query_used": query}

async def reddit_search(query: str, subreddits: list[str] = None) -> list[dict]:
    """Search Reddit for voucher codes. Stub until API access approved."""
    # TODO: implement Reddit API search when access is granted
    # Reddit introduced Responsible Builder Policy in 2026 blocking new apps
    return []

async def extract_codes_from_text(text: str, merchant: str, llm) -> list[dict]:
    """Use Claude Sonnet to extract voucher codes from raw search snippets."""
    if not text.strip():
        return []
    try:
        prompt = f"""Extract all voucher/promo/discount codes from this text for {merchant}.
Return a JSON array of objects with keys: code, saving_description, source, confidence (0-1).
Only return the JSON array, nothing else.

Text:
{text[:3000]}"""
        response = await llm.ainvoke(prompt)
        import json, re
        content = response.content if hasattr(response, 'content') else str(response)
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"Code extraction error: {e}")
    return []
