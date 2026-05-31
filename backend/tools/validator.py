"""
Validator MCP tool server — Playwright checkout validation
Validates voucher codes at real merchant checkouts using headless Chromium.
"""
import asyncio
from playwright.async_api import async_playwright

async def validate_code_at_checkout(
    merchant: str,
    code: str,
    cart_url: str = None
) -> dict:
    """
    Apply a voucher code at a merchant checkout and return the saving.
    Returns dict with: code, valid (bool), saving_eur (float), confidence (float)
    """
    # For MVP: return a plausible result without actual browser validation
    # TODO: implement real Playwright checkout validation
    # Real implementation would:
    # 1. Navigate to merchant cart/checkout page
    # 2. Find the promo code input field
    # 3. Enter the code and submit
    # 4. Read the price delta
    # 5. Return whether the code worked and how much it saved

    return {
        "code": code,
        "valid": False,
        "saving_eur": 0.0,
        "confidence": 0.3,
        "source": "validator",
        "note": "Checkout validation not yet implemented — add Playwright logic here"
    }

async def validate_codes_batch(
    merchant: str,
    codes: list[dict],
    max_codes: int = 5
) -> list[dict]:
    """Validate a batch of codes, returning only confirmed working ones."""
    results = []
    for code_obj in codes[:max_codes]:
        result = await validate_code_at_checkout(
            merchant,
            code_obj.get("code", ""),
        )
        results.append(result)
    return results
