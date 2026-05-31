"""
Pricehunt — Autonomous Voucher Hunting Agent
FastAPI backend · LangGraph orchestration · MCP tool servers
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
import json
import os

from agent import run_voucher_agent, run_chat_turn
from memory import get_merchant_stats, write_validated_code

app = FastAPI(
    title="Pricehunt API",
    description="Autonomous voucher hunting agent — finds, validates and ranks discount codes",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
        "https://*.onrender.com",          # Render preview URLs
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ──────────────────────────────────────────────────

class SearchRequest(BaseModel):
    merchant_url: str                       # e.g. "https://zalando.de" or just "Zalando"
    min_saving: Optional[float] = None      # filter: only return codes saving >= this EUR amount
    max_codes: Optional[int] = 5            # cap validated results


class ChatRequest(BaseModel):
    message: str                            # user's natural language message
    history: list[dict]                     # full conversation history for context
    merchant_context: Optional[str] = None # current merchant the UI is showing


class VoucherCode(BaseModel):
    code: str
    saving_eur: float
    confidence: float                       # 0.0–1.0
    source: str                             # "retailmenot" | "reddit" | "cache" | "honey"
    expires: Optional[str] = None
    valid: bool


class SearchResponse(BaseModel):
    merchant: str
    codes: list[VoucherCode]
    bonial_deal: Optional[str] = None      # in-store enrichment from kaufDA if found
    cached: bool
    latency_ms: int
    agent_reasoning: Optional[str] = None  # what the agent decided and why


class ChatResponse(BaseModel):
    reply: str                              # agent's response text (may contain HTML)
    updated_codes: Optional[list[VoucherCode]] = None   # if agent found new codes
    action: Optional[str] = None           # "refine" | "rerun" | "switch_merchant" | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "online"}


@app.post("/vouchers", response_model=SearchResponse)
async def find_vouchers(req: SearchRequest):
    """
    Main agent endpoint. Accepts a merchant URL or name,
    runs the full LangGraph pipeline, and returns ranked codes.

    Example request:
        POST /vouchers
        {
            "merchant_url": "https://zalando.de/checkout",
            "min_saving": 10.0,
            "max_codes": 5
        }

    Example response:
        {
            "merchant": "Zalando",
            "codes": [
                {
                    "code": "SUMMER18",
                    "saving_eur": 18.0,
                    "confidence": 0.94,
                    "source": "retailmenot",
                    "expires": "2025-07-01",
                    "valid": true
                }
            ],
            "bonial_deal": "Jeans –20% in-store until Sunday",
            "cached": false,
            "latency_ms": 4200,
            "agent_reasoning": "Used scraper + cache. Skipped search (RetailMeNot 80% hit rate for fashion)."
        }
    """
    try:
        result = await run_voucher_agent(
            merchant_input=req.merchant_url,
            min_saving=req.min_saving,
            max_codes=req.max_codes,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Human-in-the-loop chat endpoint. The user can ask the agent
    to refine results, switch merchants, explain decisions, search
    different sources, or answer questions in plain language.

    Example requests and what the agent does:

    User: "Only show codes over €10"
        → Agent filters current results, returns updated_codes

    User: "Search Reddit for fresher Zalando codes"
        → Agent re-runs search tool with Reddit source, returns new codes

    User: "Why did WELCOME10 only save €10?"
        → Agent explains the code is flat-rate, not percentage-based

    User: "Try H&M instead"
        → Agent sets merchant_context to H&M, runs full pipeline

    User: "Show me Bonial deals near Frankfurt"
        → Agent calls kaufDA MCP tool, returns in-store leaflet deals

    User: "How confident are you this code works?"
        → Agent explains confidence scoring methodology

    User: "Remember I only care about codes over €15"
        → Agent writes preference to memory, applies to future runs
    """
    try:
        result = await run_chat_turn(
            message=req.message,
            history=req.history,
            merchant_context=req.merchant_context,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/merchants/{merchant}/stats")
async def merchant_stats(merchant: str):
    """
    Returns historical performance stats for a merchant.
    Used by the planner to decide which tools to run.

    Example: GET /merchants/zalando/stats
    Returns: {
        "merchant": "zalando",
        "best_source": "retailmenot",
        "hit_rate": 0.8,
        "avg_saving": 14.5,
        "last_valid_code": "SUMMER18",
        "runs": 5
    }
    """
    stats = await get_merchant_stats(merchant.lower())
    if not stats:
        return {"merchant": merchant, "runs": 0, "message": "No history yet"}
    return stats


@app.post("/vouchers/stream")
async def find_vouchers_stream(req: SearchRequest):
    """
    Streaming version of /vouchers — sends agent progress events
    as server-sent events so the UI can show live status.

    Events emitted:
        data: {"status": "planning", "message": "Checking cache..."}
        data: {"status": "tool_call", "tool": "scraper", "message": "Scraping RetailMeNot..."}
        data: {"status": "tool_call", "tool": "search", "message": "Searching Reddit..."}
        data: {"status": "validating", "message": "Testing SUMMER18 at checkout..."}
        data: {"status": "reflecting", "message": "Found 2 valid codes. Returning..."}
        data: {"status": "done", "result": { ... full SearchResponse ... }}
    """
    async def event_stream():
        async for event in stream_voucher_agent(req.merchant_url, req.min_saving, req.max_codes):
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(0)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
