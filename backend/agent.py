"""
Pricehunt — LangGraph Agent
Autonomous pipeline: planner → parallel MCP tools → validator → reflection → memory
"""

import time
import json
import re
from typing import Optional, AsyncIterator
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain.tools import tool
from pydantic import BaseModel

from tools.scraper import scrape_retailmenot, scrape_honey, scrape_idealo
from tools.search import tavily_search, reddit_search, extract_codes_from_text
from tools.cache import get_cached_codes, write_validated_code, get_merchant_history
from tools.validator import validate_code_at_checkout
from tools.bonial import get_bonial_deals
from memory import write_run_result

# ── Models ─────────────────────────────────────────────────────────────────────

class AgentState(BaseModel):
    merchant: str = ""
    merchant_url: str = ""
    min_saving: Optional[float] = None
    max_codes: int = 5

    # Planner output
    plan: dict = {}                     # {"tools": [...], "parallel": bool, "queries": [...]}

    # Collected raw codes (before validation)
    raw_codes: list[dict] = []

    # Validated results
    validated_codes: list[dict] = []

    # Bonial enrichment
    bonial_deal: Optional[str] = None

    # Agent memory
    merchant_history: dict = {}

    # Reflection
    retry_count: int = 0
    tools_used: list[str] = []
    reflection_decision: str = ""       # "return" | "retry"
    reflection_reason: str = ""

    # Timing
    start_time: float = 0.0

    # Chat context
    chat_history: list[dict] = []
    user_message: str = ""


# ── LLM instances ──────────────────────────────────────────────────────────────

# Single Sonnet instance used for all LLM calls:
# planner node, reflection node, code extraction, and chat turns
llm = ChatAnthropic(model="claude-sonnet-4-6", max_tokens=1000)


# ── Node: extract merchant from URL / name ─────────────────────────────────────

async def extract_merchant_node(state: AgentState) -> AgentState:
    """
    Normalises the user input to a clean merchant name.
    "https://zalando.de/checkout" → "Zalando"
    "about you" → "About You"
    """
    raw = state.merchant_url
    # Simple heuristic — strip URL parts
    domain = re.sub(r"https?://|www\.|/.*", "", raw).strip()
    parts = domain.split(".")
    merchant = parts[0].replace("-", " ").title() if domain else raw.title()

    state.merchant = merchant
    state.start_time = time.time()
    return state


# ── Node: planner ──────────────────────────────────────────────────────────────

async def planner_node(state: AgentState) -> AgentState:
    """
    The brain. Reads merchant history and decides which tools to run.
    Outputs a JSON plan the graph uses to fan out to tools.
    """
    history_summary = ""
    if state.merchant_history:
        h = state.merchant_history
        history_summary = f"""
Past runs for {state.merchant}:
- Best source: {h.get('best_source', 'unknown')}
- Hit rate: {h.get('hit_rate', 0) * 100:.0f}%
- Tools that failed last time: {h.get('failed_tools', [])}
- Avg saving found: €{h.get('avg_saving', 0):.0f}
- Already retried: {state.retry_count} time(s)
"""

    retry_note = ""
    if state.retry_count > 0:
        retry_note = f"""
This is retry #{state.retry_count}.
Tools already tried: {state.tools_used}
Codes found so far: {len(state.raw_codes)}
Previous reflection: {state.reflection_reason}
Try a DIFFERENT approach — different sources or broader queries.
"""

    prompt = f"""You are the planning brain of Pricehunt, an autonomous voucher-hunting agent.

Merchant: {state.merchant}
URL: {state.merchant_url}
Min saving required: €{state.min_saving or 0}
{history_summary}
{retry_note}

Available tools:
- scraper: Playwright scrape of RetailMeNot, Honey, Idealo. Slow (4–8s) but comprehensive.
- search: Tavily Search API + Reddit. Fast (1–2s), finds codes in blog posts and deal threads.
- cache: Redis lookup of previously validated codes. Instant. Always try this first.
- bonial: kaufDA/Bonial weekly leaflet scraper. Returns in-store EU promotions.

Decide:
1. Which tools to run (array, ordered by priority)
2. Whether to run them in parallel (true/false)
3. What search queries to use (2–3 specific queries)
4. Whether to include bonial enrichment (true for EU fashion/retail merchants)

Be strategic: if cache hit rate is high, start with cache only.
For a first run with no history, fan out all tools in parallel.

Respond ONLY with valid JSON, no other text:
{{
  "tools": ["cache", "scraper", "search"],
  "parallel": true,
  "queries": ["Zalando promo code June 2025", "Zalando 20% discount code"],
  "include_bonial": true,
  "reasoning": "First run, no history. Full parallel fan-out."
}}"""

    response = await llm.ainvoke(prompt)
    try:
        plan = json.loads(response.content)
    except json.JSONDecodeError:
        # Fallback safe plan
        plan = {
            "tools": ["cache", "scraper", "search"],
            "parallel": True,
            "queries": [f"{state.merchant} promo code", f"{state.merchant} discount code"],
            "include_bonial": True,
            "reasoning": "JSON parse failed, using safe fallback plan.",
        }

    state.plan = plan
    return state


# ── Node: run tools ─────────────────────────────────────────────────────────────

async def run_tools_node(state: AgentState) -> AgentState:
    """
    Executes the plan. Runs MCP tool servers in parallel or sequence
    depending on planner decision.
    """
    import asyncio

    plan = state.plan
    tools_to_run = plan.get("tools", ["scraper"])
    queries = plan.get("queries", [f"{state.merchant} promo code"])
    parallel = plan.get("parallel", True)
    include_bonial = plan.get("include_bonial", False)

    async def run_tool(tool_name: str) -> list[dict]:
        codes = []
        try:
            if tool_name == "cache":
                result = await get_cached_codes(state.merchant)
                codes = result if isinstance(result, list) else result.get("codes", [])

            elif tool_name == "scraper":
                # Fan out to all scraper sites
                results = await asyncio.gather(
                    scrape_retailmenot(state.merchant),
                    scrape_honey(state.merchant),
                    scrape_idealo(state.merchant),
                    return_exceptions=True,
                )
                for r in results:
                    if isinstance(r, list):
                        codes.extend(r)

            elif tool_name == "search":
                snippets = []
                for query in queries:
                    r = await tavily_search(query)
                    snippets.extend(r.get("snippets", []))
                reddit = await reddit_search(state.merchant)
                if isinstance(reddit, list):
                    snippets.extend(reddit)
                elif isinstance(reddit, dict):
                    snippets.extend(reddit.get("snippets", []))
                # Extract codes from raw text with Sonnet
                if snippets:
                    extracted = await extract_codes_from_text(
                        "\n".join(snippets), state.merchant, llm
                    )
                    codes = extracted

        except Exception as e:
            print(f"Tool {tool_name} failed: {e}")

        state.tools_used.append(tool_name)
        return codes

    # Run tools
    if parallel:
        results = await asyncio.gather(*[run_tool(t) for t in tools_to_run])
        all_codes = [code for batch in results for code in batch]
    else:
        all_codes = []
        for t in tools_to_run:
            codes = await run_tool(t)
            all_codes.extend(codes)

    # Deduplicate by code string
    seen = set()
    unique = []
    for c in all_codes:
        key = c.get("code", "").upper().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(c)

    state.raw_codes = unique

    # Bonial enrichment (non-blocking)
    if include_bonial:
        try:
            bonial = await get_bonial_deals(state.merchant)
            state.bonial_deal = bonial.get("deal_summary")
        except Exception:
            pass

    return state


# ── Node: validator ─────────────────────────────────────────────────────────────

async def validator_node(state: AgentState) -> AgentState:
    """
    Tests the top N codes at a real checkout using Playwright.
    Only sends the most plausible candidates to keep latency under 8s.
    """
    import asyncio

    if not state.raw_codes:
        state.validated_codes = []
        return state

    # Score each raw code for plausibility before expensive validation
    scored = _score_codes(state.raw_codes, state.merchant)
    top_candidates = scored[:state.max_codes]

    # Validate in parallel (capped at max_codes)
    results = await asyncio.gather(
        *[validate_code_at_checkout(state.merchant_url, c["code"]) for c in top_candidates],
        return_exceptions=True,
    )

    validated = []
    for candidate, result in zip(top_candidates, results):
        if isinstance(result, Exception):
            continue
        if result.get("valid"):
            validated.append({
                "code": candidate["code"],
                "saving_eur": result["saving_eur"],
                "confidence": candidate.get("confidence", 0.7),
                "source": candidate.get("source", "unknown"),
                "expires": candidate.get("expires"),
                "valid": True,
            })
            # Write back to cache
            await write_validated_code(
                merchant=state.merchant,
                code=candidate["code"],
                saving_eur=result["saving_eur"],
                source=candidate.get("source"),
            )

    # Sort by saving descending
    validated.sort(key=lambda x: x["saving_eur"], reverse=True)

    # Apply min_saving filter if set
    if state.min_saving:
        validated = [v for v in validated if v["saving_eur"] >= state.min_saving]

    state.validated_codes = validated
    return state


def _score_codes(codes: list[dict], merchant: str) -> list[dict]:
    """
    Heuristic scoring before validation — filters obvious duds cheaply.
    Avoids wasting Playwright calls on codes like 'EXPIRED2022'.
    """
    scored = []
    for c in codes:
        code_str = c.get("code", "").upper()
        score = c.get("confidence", 0.5)

        # Boost multi-source codes
        if c.get("source_count", 1) > 1:
            score += 0.15

        # Penalise obvious year-expired patterns
        if re.search(r"20(1[0-9]|2[0-3])", code_str):
            score -= 0.3

        # Boost codes mentioning the merchant name
        if merchant.upper()[:4] in code_str:
            score += 0.1

        # Penalise very short or very long codes
        if len(code_str) < 4 or len(code_str) > 16:
            score -= 0.2

        scored.append({**c, "confidence": min(max(score, 0.0), 1.0)})

    scored.sort(key=lambda x: x["confidence"], reverse=True)
    return scored


# ── Node: reflection ───────────────────────────────────────────────────────────

async def reflection_node(state: AgentState) -> AgentState:
    """
    The agent evaluates its own output.
    Decides: return, retry with new plan, or give up.
    """
    MAX_RETRIES = 2

    if state.retry_count >= MAX_RETRIES:
        state.reflection_decision = "return"
        state.reflection_reason = f"Reached max retries ({MAX_RETRIES}). Returning best available result."
        return state

    if state.validated_codes:
        best = state.validated_codes[0]["saving_eur"]
        if best >= (state.min_saving or 2.0):
            state.reflection_decision = "return"
            state.reflection_reason = f"Found {len(state.validated_codes)} valid code(s). Best saves €{best}. Good enough."
            return state

    # Ask the LLM to reflect
    prompt = f"""You are the reflection node of Pricehunt.

Merchant: {state.merchant}
Tools tried: {state.tools_used}
Raw codes found: {len(state.raw_codes)}
Validated codes: {len(state.validated_codes)}
Min saving required: €{state.min_saving or 0}
Retry count: {state.retry_count}

Should you:
(a) return — the result is good enough, or you've exhausted reasonable options
(b) retry — there are untried sources that might yield better results

Rules:
- If validated codes >= 1 and best saving >= €{state.min_saving or 2}: return
- If retry_count >= 2: return with explanation
- If no codes found AND search tool not tried yet: retry
- If scraper not tried: retry
- Otherwise: return with honest empty result

Respond ONLY with JSON:
{{"decision": "return" | "retry", "reason": "..."}}"""

    response = await llm.ainvoke(prompt)
    try:
        parsed = json.loads(response.content)
        state.reflection_decision = parsed.get("decision", "return")
        state.reflection_reason = parsed.get("reason", "")
    except Exception:
        state.reflection_decision = "return"
        state.reflection_reason = "Reflection parse failed, returning current result."

    if state.reflection_decision == "retry":
        state.retry_count += 1

    return state


# ── Routing function ───────────────────────────────────────────────────────────

def route_after_reflection(state: AgentState) -> str:
    if state.reflection_decision == "retry":
        return "planner"
    return END


# ── Build the graph ────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("extract_merchant", extract_merchant_node)
    graph.add_node("planner",          planner_node)
    graph.add_node("run_tools",        run_tools_node)
    graph.add_node("validator",        validator_node)
    graph.add_node("reflection",       reflection_node)

    graph.set_entry_point("extract_merchant")
    graph.add_edge("extract_merchant", "planner")
    graph.add_edge("planner",          "run_tools")
    graph.add_edge("run_tools",        "validator")
    graph.add_edge("validator",        "reflection")
    graph.add_conditional_edges("reflection", route_after_reflection)

    return graph.compile()


_graph = build_graph()


# ── Public API ─────────────────────────────────────────────────────────────────

async def run_voucher_agent(
    merchant_input: str,
    min_saving: Optional[float] = None,
    max_codes: int = 5,
) -> dict:
    """Called by main.py POST /vouchers"""
    history = await get_merchant_history(merchant_input)

    initial = AgentState(
        merchant_url=merchant_input,
        min_saving=min_saving,
        max_codes=max_codes,
        merchant_history=history or {},
    )

    raw = await _graph.ainvoke(initial)

    # LangGraph returns a dict — convert back to AgentState for easy access
    if isinstance(raw, dict):
        final = AgentState(**{k: v for k, v in raw.items() if k in AgentState.model_fields})
    else:
        final = raw

    elapsed_ms = int((time.time() - (final.start_time or time.time())) * 1000)

    await write_run_result(
        merchant=final.merchant or "unknown",
        tools_used=final.tools_used or [],
        codes_found=len(final.validated_codes or []),
        best_saving=final.validated_codes[0]["saving_eur"] if final.validated_codes else 0,
    )

    return {
        "merchant": final.merchant,
        "codes": final.validated_codes or [],
        "bonial_deal": final.bonial_deal,
        "cached": "cache" in (final.tools_used or []) and final.retry_count == 0,
        "latency_ms": elapsed_ms,
        "agent_reasoning": final.reflection_reason,
    }


async def run_chat_turn(
    message: str,
    history: list[dict],
    merchant_context: Optional[str] = None,
) -> dict:
    """
    Called by main.py POST /chat.
    The agent receives the user's message and conversation history,
    and decides whether to re-run tools, filter, explain, or just respond.
    """
    system = f"""You are the Pricehunt agent — an autonomous voucher-hunting AI.
You help users find, understand, and apply discount codes.
Current merchant context: {merchant_context or 'none'}

You can:
- Find codes for a merchant (set action: "rerun")
- Filter results by saving amount (set action: "refine")
- Switch to a different merchant (set action: "switch_merchant")
- Explain why a code works or doesn't
- Search Reddit or other specific sources (set action: "rerun")
- Show Bonial/kaufDA in-store deals
- Remember user preferences

Always be concise, friendly, and specific. If re-running the agent, say so.
Respond with valid JSON only:
{{
  "reply": "your response text here (HTML allowed: <strong>, <em>, <br>)",
  "action": null | "rerun" | "refine" | "switch_merchant",
  "new_merchant": null | "merchant name if switching",
  "filter": null | {{"min_saving": 10.0}}
}}"""

    messages = [{"role": "system", "content": system}]
    for h in history[-10:]:     # last 10 turns for context
        messages.append(h)
    messages.append({"role": "user", "content": message})

    response = await llm.ainvoke(messages)

    try:
        raw = response.content.strip()
        # Strip markdown code fences: ```json ... ``` or ``` ... ```
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"reply": response.content, "action": None}

    result = {
        "reply": parsed.get("reply", ""),
        "action": parsed.get("action"),
        "updated_codes": None,
    }

    # If agent decided to re-run, trigger the full pipeline
    if parsed.get("action") == "rerun" or parsed.get("action") == "switch_merchant":
        target = parsed.get("new_merchant") or merchant_context or ""
        if target:
            agent_result = await run_voucher_agent(
                merchant_input=target,
                min_saving=parsed.get("filter", {}).get("min_saving") if parsed.get("filter") else None,
            )
            result["updated_codes"] = agent_result.get("codes")

    return result


async def stream_voucher_agent(
    merchant_input: str,
    min_saving: Optional[float],
    max_codes: int,
) -> AsyncIterator[dict]:
    """Streaming version — yields status events for the SSE endpoint."""
    yield {"status": "planning", "message": f"Analysing {merchant_input}..."}
    await asyncio.sleep(0.1)

    yield {"status": "tool_call", "tool": "cache", "message": "Checking code cache..."}
    await asyncio.sleep(0.1)

    yield {"status": "tool_call", "tool": "scraper", "message": "Scraping RetailMeNot + Honey..."}
    await asyncio.sleep(0.1)

    yield {"status": "tool_call", "tool": "search", "message": "Searching web + Reddit..."}
    await asyncio.sleep(0.1)

    yield {"status": "validating", "message": "Validating top codes at checkout..."}

    result = await run_voucher_agent(merchant_input, min_saving, max_codes)

    yield {"status": "done", "result": result}
