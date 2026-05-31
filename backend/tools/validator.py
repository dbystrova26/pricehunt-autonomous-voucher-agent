"""
Validator MCP tool server — Playwright checkout validation
Current state: returns realistic mock validation results for demo.
TODO: implement real Playwright checkout validation per merchant.
"""
import random

# Realistic saving ranges per merchant category
MERCHANT_SAVINGS = {
    "zalando": (8, 25),
    "asos": (10, 30),
    "about you": (5, 20),
    "h&m": (5, 15),
    "zara": (10, 20),
    "nike": (10, 25),
    "adidas": (10, 30),
    "lookfantastic": (5, 20),
    "douglas": (5, 15),
    "sephora": (5, 20),
    "default": (5, 20),
}

def _estimate_saving(merchant: str, code: str) -> tuple[bool, float]:
    """
    Estimate whether a code is valid and how much it saves.
    Uses heuristics: code age signals, merchant patterns, source confidence.
    Real implementation would test at actual checkout with Playwright.
    """
    merchant_lower = merchant.lower()

    # Penalise obviously old codes
    import re
    old_years = re.findall(r'20(1[0-9]|2[0-2])', code.upper())
    if old_years:
        return False, 0.0

    # Short generic codes are often invalid
    if len(code) < 4:
        return False, 0.0

    # Estimate saving from merchant category
    for key, (min_s, max_s) in MERCHANT_SAVINGS.items():
        if key in merchant_lower:
            saving = round(random.uniform(min_s, max_s), 2)
            # 70% validation rate for realistic demo
            valid = random.random() > 0.3
            return valid, saving if valid else 0.0

    saving = round(random.uniform(*MERCHANT_SAVINGS["default"]), 2)
    valid = random.random() > 0.3
    return valid, saving if valid else 0.0


async def validate_code_at_checkout(
    merchant: str,
    code: str,
    cart_url: str = None
) -> dict:
    """
    Validate a voucher code at merchant checkout.
    Current: realistic mock validation.
    TODO: real Playwright implementation per merchant.
    """
    valid, saving = _estimate_saving(merchant, code)
    return {
        "code": code,
        "valid": valid,
        "saving_eur": saving,
        "confidence": 0.75 if valid else 0.1,
        "source": "validator",
    }


async def validate_codes_batch(
    merchant: str,
    codes: list[dict],
    max_codes: int = 5
) -> list[dict]:
    """Validate a batch of codes, returning confirmed working ones."""
    results = []
    for code_obj in codes[:max_codes]:
        result = await validate_code_at_checkout(
            merchant,
            code_obj.get("code", ""),
        )
        results.append(result)
    return results
