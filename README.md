# Pricehunt 🎯
### Autonomous voucher-hunting agent · LangGraph · MCP · Claude · Render

> An autonomous AI agent that scans the web for discount codes, tests them at real checkouts, and returns the best saving — in under 8 seconds.

---

## What it does

Pricehunt is not a scraper with a UI. It is an **autonomous LangGraph agent** that:

1. **Plans** — reads its own memory to decide which sources to check and in what order
2. **Hunts** — fans out to scraper, search, and cache MCP tool servers in parallel
3. **Enriches** — pulls Bonial/kaufDA weekly leaflets for in-store EU promotions
4. **Validates** — uses a headless Playwright browser to test codes at real checkouts
5. **Reflects** — evaluates its own output and retries with a different plan if needed
6. **Learns** — writes success rates per merchant to Redis, gets smarter every run
7. **Talks** — stays in a chat loop so users can refine results in plain language

---

## Architecture

```
React UI (Vite)
    │
    ├── POST /vouchers          ← main agent search
    ├── POST /chat              ← human-in-the-loop chat
    └── POST /vouchers/stream   ← live SSE progress events
            │
         FastAPI
            │
       LangGraph agent
       (agent.py)
            │
    ┌───────┼────────────┐
    │       │            │
 Scraper  Search      Cache
 MCP srv  MCP srv     MCP srv
    │       │            │
Retailme  Brave API   Redis
Not,Honey Reddit      Postgres
Idealo
            │
         Validator
         MCP server
         (Playwright)
            │
         Bonial MCP server
         (kaufDA leaflets)
```

---

## The LangGraph agent — how it is built and how it runs

[LangGraph](https://langchain-ai.github.io/langgraph/) is a framework for building
stateful, multi-step AI agents as directed graphs. Each node in the graph is a Python
async function. Edges connect nodes, and conditional edges let the agent branch or loop
based on what it has found so far.

Pricehunt's graph lives in `backend/agent.py` and has five nodes:

```
extract_merchant
      │
   planner  ◄─────────────────────────┐
      │                               │ (retry if reflection says so)
  run_tools                           │
      │                               │
  validator                           │
      │                               │
 reflection ────────────────────────► END
```

### Node 1 — `extract_merchant`

Normalises the user's raw input into a clean merchant name.

```python
async def extract_merchant_node(state: AgentState) -> AgentState:
    # "https://zalando.de/checkout" → "Zalando"
    # "about you" → "About You"
```

This runs first on every call. It strips URL parts, title-cases the name, and stamps
`start_time` so latency can be measured at the end.

### Node 2 — `planner`

The brain of the agent. Makes a Claude Sonnet API call with a prompt that includes:
- The merchant name and category
- The full history from Redis (which sources worked last time, their hit rates)
- What tools were already tried if this is a retry

It returns a **JSON plan** — not prose, not a decision tree hardcoded by a developer:

```json
{
  "tools": ["cache", "scraper", "search"],
  "parallel": true,
  "queries": ["Zalando promo code June 2025", "Zalando 20% discount"],
  "include_bonial": true,
  "reasoning": "First run, no history. Full parallel fan-out."
}
```

This is where autonomy starts: you do not tell the agent which tools to use.
It reads the situation and decides. On a return visit where the cache has an 80% hit
rate, it may skip scraping entirely and just check the cache.

### Node 3 — `run_tools`

Executes the plan by calling MCP tool servers. Runs them in parallel or sequence
depending on the `parallel` flag the planner set.

```python
async def run_tools_node(state: AgentState) -> AgentState:
    if parallel:
        results = await asyncio.gather(*[run_tool(t) for t in tools_to_run])
    else:
        for t in tools_to_run:
            codes.extend(await run_tool(t))
```

Each `run_tool(name)` call dispatches to the relevant MCP server:

| Tool name | MCP server | What it does |
|---|---|---|
| `cache` | cache-mcp-server | Redis lookup — instant, no network cost |
| `scraper` | scraper-mcp-server | Playwright scrape of RetailMeNot, Honey, Idealo |
| `search` | search-mcp-server | Brave Search + Reddit, then Haiku extracts codes |
| `bonial` | bonial-mcp-server | kaufDA weekly leaflet scraper |

After all tools finish, codes are deduplicated by code string and stored in `state.raw_codes`.

### Node 4 — `validator`

The most expensive node. Calls the validator MCP server which uses a headless
Playwright browser to apply each candidate code to a real checkout and read the price delta.

Before sending codes to the browser, the agent **pre-scores** them with a heuristic
to avoid wasting browser time on obvious duds:

```python
def _score_codes(codes, merchant):
    # Penalise codes with old years (XMAS2022 → -0.40)
    # Boost codes that appear on multiple sources (+0.20)
    # Boost codes that contain the merchant name fragment (+0.10)
    # Returns top N sorted by score
```

Only the top 5 candidates are sent to Playwright. This keeps total latency under 8 seconds
even when 20+ raw codes were found.

### Node 5 — `reflection`

After validation, the agent evaluates its own output. This is the self-reflection loop
that makes Pricehunt an agent rather than a script.

A Claude Haiku call receives the full run context and must respond with a JSON decision:

```json
{"decision": "return", "reason": "Found 2 valid codes. Best saves €18. Good enough."}
```

or:

```json
{"decision": "retry", "reason": "0 codes found. Search tool not tried yet. Retry."}
```

If the decision is `retry`, LangGraph routes back to the **planner** node — not back to
the start. The planner receives the retry context, knows what already failed, and writes
a different plan. Maximum 2 retries before the agent gives up and returns what it has.

### The conditional edge

```python
def route_after_reflection(state: AgentState) -> str:
    if state.reflection_decision == "retry":
        return "planner"   # loop back
    return END             # finish
```

This single function is what turns a linear pipeline into a reasoning loop.
LangGraph calls it after every reflection node execution to decide where to go next.

### State object

All data flows through a single `AgentState` Pydantic model — no global variables,
no side effects between nodes. Each node receives the state, returns an updated copy,
and LangGraph handles the rest.

```python
class AgentState(BaseModel):
    merchant: str
    plan: dict                  # written by planner, read by run_tools
    raw_codes: list[dict]       # written by run_tools, read by validator
    validated_codes: list[dict] # written by validator, read by reflection
    retry_count: int            # incremented by reflection on retry
    tools_used: list[str]       # accumulated across retries
    reflection_decision: str    # "return" | "retry"
    bonial_deal: Optional[str]  # enrichment from kaufDA
    merchant_history: dict      # read from Redis before planner runs
```

### How a full run flows

```
User: POST /vouchers {"merchant_url": "zalando.de"}

1. extract_merchant  →  merchant = "Zalando", start_time = now()

2. planner           →  reads Redis: "last 5 runs, RetailMeNot hit rate 80%"
                        LLM decides: {"tools":["cache","scraper"], "parallel":true}

3. run_tools         →  cache: miss (6h TTL expired)
                        scraper: RetailMeNot returns [SUMMER18, WELCOME10, FLASH5]
                        bonial: "Jeans –20% in-store until Sunday"

4. validator         →  pre-scores 3 codes, sends top 3 to Playwright
                        SUMMER18: valid, saves €18.00 ✅
                        WELCOME10: valid, saves €10.00 ✅
                        FLASH5: invalid, code expired ✗

5. reflection        →  "Found 2 valid codes. Best €18. Good enough."
                        decision = "return"

Response: {"codes":[{"code":"SUMMER18","saving_eur":18.0,...},...], "latency_ms": 4100}
```

If step 3 had returned 0 codes, reflection would have set `decision = "retry"`,
the graph would route back to the planner, and the planner would write a new plan
that includes the `search` tool — which it skipped on the first pass because history
showed RetailMeNot was reliable. The agent self-corrects without any human intervention.

---

## Where MCP is used

MCP (Model Context Protocol) is the communication layer between the **LangGraph agent**
and each **tool server**. Instead of hardcoding scraping logic inside the agent, each
data source runs as an independent MCP server. The agent discovers available tools at
startup and calls them by name over JSON-RPC.

```
agent.py  ──MCP──►  scraper-mcp-server   (scrape_retailmenot, scrape_honey)
          ──MCP──►  search-mcp-server    (brave_search, reddit_search)
          ──MCP──►  cache-mcp-server     (get_cached_codes, write_validated_code)
          ──MCP──►  validator-mcp-server (validate_code_at_checkout)
          ──MCP──►  bonial-mcp-server    (get_bonial_deals)
```

**Why MCP matters here:**
- Each server is independently deployable and testable
- Adding a new source (e.g. Coupert) means adding one MCP server — agent picks it up automatically
- The agent reads tool descriptions to decide which to call — no hardcoded routing
- Swap the scraper implementation without touching a single line of agent code
- Standard protocol used by production AI systems in 2025

See `.claude/tools/` for the tool definition files and `.claude/skills/` for the skill guides.

---

## APIs — what, why, and how to get them

### 🧠 Anthropic API
**What:** The LLM powering the agent. Two models used:
- `claude-sonnet-4-6` — planner node, reflection node, chat responses. The main brain.
- `claude-haiku-4-5-20251001` — code extraction from raw search text. Fast and cheap.

**Why Anthropic over OpenAI:** Claude follows complex structured instructions reliably,
produces clean JSON plans without hallucinating tool names, and handles long tool-result
contexts better for this use case.

**How to get:**
1. Go to https://platform.anthropic.com
2. Sign up → API Keys → Create Key
3. Free $5 credit on signup — enough for hundreds of agent runs

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

---

### 🔍 Brave Search API
**What:** Independent web search index. Returns structured JSON results for any query.
Used by the search MCP server to find codes buried in blog posts, deal forums, and
news articles that scraping aggregators like RetailMeNot miss.

**Why Brave over Google:** Google's Custom Search API costs $5 per 1,000 queries and
heavily rate-limits free use. Brave offers 2,000 free requests/month, has no Google
tracking overhead, and returns cleaner structured snippets for code extraction.

**Why not SerpAPI:** SerpAPI costs $50/month minimum. Good for production but overkill
for an MVP. Brave covers the same use case for free.

**How to get:**
1. Go to https://api.search.brave.com
2. Sign up → Developer Dashboard → Create Subscription (Free tier)
3. Copy the API key from the dashboard

```
BRAVE_API_KEY=BSA...
```

---

### 🤖 Reddit API
**What:** Access to Reddit posts and comments. Used to search r/deals, r/promo_codes,
r/frugal, and merchant-specific subreddits for codes that haven't reached aggregators yet.

**Why Reddit:** Reddit is often 24–48 hours ahead of RetailMeNot for fresh codes.
Users post codes the moment they find them. Especially powerful for flash sales and
limited-time codes that expire before scrapers catch up.

**How to get:**
1. Go to https://www.reddit.com/prefs/apps
2. Click "create another app" at the bottom
3. Choose type: **script**
4. Name: `pricehunt-agent`
5. Redirect URI: `http://localhost`
6. Submit → copy `client_id` (under the app name) and `client_secret`

```
REDDIT_CLIENT_ID=abc123...
REDDIT_CLIENT_SECRET=xyz789...
```

---

### 🛒 Rakuten Advertising API
**What:** Affiliate network API. Provides structured cashback rates and occasionally
exclusive promo codes for 2,500+ merchants in the EU and US.

**Why Rakuten:** Unlike scraping, Rakuten gives you structured data with confirmed
merchant IDs, exact cashback percentages, and programme terms. It also opens the door
to a cashback revenue model — if users click through Pricehunt's tracked links, the
app earns a small commission per purchase.

**Why not Commission Junction or Awin:** Rakuten has the best EU merchant coverage
for fashion and electronics. Awin is a good alternative for DE-specific merchants.

**How to get:**
1. Go to https://rakutenadvertising.com
2. Sign up as a Publisher (free)
3. Wait for approval (1–2 business days)
4. API Keys section → generate key

```
RAKUTEN_API_KEY=...
```

---

### 🌐 Browserbase API *(optional)*
**What:** Managed cloud browser service. Runs Playwright sessions in the cloud with
built-in anti-bot handling, residential proxies, and CAPTCHA solving.

**Why:** Many merchant checkout pages detect and block headless Playwright browsers.
Browserbase solves this transparently — the validation MCP server calls Browserbase
instead of running Playwright locally, and checkout pages see a real browser session.

**Why optional for MVP:** Local Playwright works fine on most merchants. Add Browserbase
if you get blocked on specific sites.

**How to get:**
1. Go to https://browserbase.com
2. Sign up → Create Project → copy API key and project ID

```
BROWSERBASE_API_KEY=bb_...
BROWSERBASE_PROJECT_ID=prj_...
```

---

### 🗄 Redis *(auto-configured on Render)*
**What:** In-memory key-value store. Used for:
- Code cache with 6h TTL per merchant
- Agent memory: which source worked best per merchant
- User preferences from chat history

**Why Redis over Postgres for caching:** Redis is orders of magnitude faster for
key-value lookups (sub-millisecond). The agent reads merchant history before every
run — it needs to be instant.

**How to get locally:**
```bash
brew install redis && redis-server   # macOS
# or
docker run -p 6379:6379 redis:alpine
```
On Render: add the Redis add-on in your dashboard → it injects `REDIS_URL` automatically.

```
REDIS_URL=redis://localhost:6379
```

---

### 🐘 PostgreSQL *(auto-configured on Render)*
**What:** Relational database. Used for long-term run history per merchant, code
success/failure logs, and user session data.

**How to get locally:**
```bash
brew install postgresql && pg_ctl start   # macOS
# or
docker run -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres:16
```
On Render: add the Postgres add-on → injects `DATABASE_URL` automatically.

```
DATABASE_URL=postgresql://user:pass@localhost:5432/pricehunt
```

---

## Full `.env` file

Copy `.env.example` to `.env` and fill in your values:

```bash
# ── LLM ──────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-...       # platform.anthropic.com

# ── Search ───────────────────────────────────────────────────────
BRAVE_API_KEY=BSA...                     # api.search.brave.com (free 2k/mo)
REDDIT_CLIENT_ID=abc123...               # reddit.com/prefs/apps
REDDIT_CLIENT_SECRET=xyz789...           # reddit.com/prefs/apps

# ── Affiliate / cashback ─────────────────────────────────────────
RAKUTEN_API_KEY=...                      # rakutenadvertising.com (publisher)

# ── Validation browser (optional) ────────────────────────────────
BROWSERBASE_API_KEY=bb_...               # browserbase.com
BROWSERBASE_PROJECT_ID=prj_...           # browserbase.com

# ── Cache & DB ───────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379         # Render auto-fills in production
DATABASE_URL=postgresql://...            # Render auto-fills in production

# ── App ──────────────────────────────────────────────────────────
FRONTEND_URL=http://localhost:5173       # Render auto-fills in production
```

Priority for getting keys:
1. `ANTHROPIC_API_KEY` — get this first, nothing works without it
2. `BRAVE_API_KEY` — 2 minutes, free
3. `REDDIT_CLIENT_ID` + `SECRET` — 5 minutes, free
4. `RAKUTEN_API_KEY` — apply early, takes 1–2 days for approval

---

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Redis running locally (or Docker)

### 1. Clone the repo

```bash
git clone https://github.com/your-username/pricehunt-autonomous-voucher-agent.git
cd pricehunt-autonomous-voucher-agent
```

### 2. Backend — Python virtual environment

Always use a virtual environment. This keeps Pricehunt's dependencies isolated from
your system Python and prevents version conflicts.

```bash
cd backend

# Create the virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# Your prompt should now show (.venv)
# Install dependencies inside the venv
pip install -r requirements.txt

# Install Playwright's browser binary (Chromium)
playwright install chromium

# Copy env file and fill in your API keys
cp .env.example .env
```

To deactivate the virtual environment when you're done:

```bash
deactivate
```

To reactivate in a new terminal session:

```bash
cd backend
source .venv/bin/activate
```

> **Note:** The `.venv` folder is in `.gitignore` — never commit it.
> Anyone cloning the repo runs the setup steps above to recreate it locally.

### 3. Start Redis (if not already running)

```bash
# macOS
brew services start redis

# Docker (any OS)
docker run -d -p 6379:6379 --name pricehunt-redis redis:alpine
```

### 4. Run the backend

```bash
# Make sure .venv is active
source backend/.venv/bin/activate

uvicorn main:app --reload --port 8000
# → http://localhost:8000
# → http://localhost:8000/docs  (auto-generated API docs)
```

### 5. Frontend

```bash
cd frontend
npm install
cp .env.example .env          # sets VITE_API_URL=http://localhost:8000
npm run dev
# → http://localhost:5173
```

### 6. Quick start with Make

A `Makefile` at the repo root wraps all of the above:

```bash
make setup        # create venv, install deps, install Chromium
make dev          # start backend + frontend in parallel
make test         # run pytest inside the venv
make clean        # remove .venv and node_modules
```

---

## Sample questions the chat can answer

### Finding codes
```
"Find voucher codes for Zalando"
"I'm about to checkout on Nike.com — any codes?"
"Best discount code for About You right now"
"Any codes for MediaMarkt Germany this week?"
"Find a student discount for ASOS"
```

### Refining results
```
"Only show me codes that save more than €15"
"Filter out anything expired"
"Which code works best for a €120 cart?"
"Is there a free shipping code for H&M?"
```

### Understanding the agent
```
"Why did WELCOME10 only save €10?"
"Why is this code showing low confidence?"
"Why did the agent skip Google search this time?"
"How confident are you this code still works?"
"What sources did you check?"
```

### Asking for more effort
```
"Search Reddit for fresher Zalando codes"
"Re-run the search, I think there's a better code"
"Try all sources in parallel"
"Check if there's a first-order discount"
```

### Switching context
```
"Try Adidas instead"
"Find codes for both Nike and Zalando"
"Now check About You"
```

### Bonial / in-store
```
"Any in-store deals for H&M in Frankfurt this week?"
"What does the Lidl leaflet say this week?"
"Combine online codes with Bonial deals for MediaMarkt"
```

### Teaching preferences
```
"Remember I only care about codes over €10"
"Always search Reddit first for fashion brands"
"Don't show codes under €5"
```

---

## Project structure

```
pricehunt-autonomous-voucher-agent/
├── README.md
├── Makefile                         # dev shortcuts
├── render.yaml                      # one-file Render deployment
├── .gitignore
├── .claude/
│   ├── skills/
│   │   ├── voucher-extraction.md    # how to extract codes from raw text
│   │   ├── checkout-validation.md   # how to validate codes with Playwright
│   │   └── bonial-scraping.md       # how to parse kaufDA leaflet pages
│   └── tools/
│       ├── brave-search.md          # tool definition: brave_search
│       ├── reddit-search.md         # tool definition: reddit_search
│       ├── retailmenot-scraper.md   # tool definition: scrape_retailmenot
│       ├── code-validator.md        # tool definition: validate_code_at_checkout
│       └── bonial-deals.md          # tool definition: get_bonial_deals
├── backend/
│   ├── .venv/                       # virtual environment (git-ignored)
│   ├── .env                         # your secrets (git-ignored)
│   ├── .env.example                 # template to copy
│   ├── main.py                      # FastAPI app — all endpoints
│   ├── agent.py                     # LangGraph graph — all five nodes
│   ├── memory.py                    # Redis cache + run history
│   ├── requirements.txt             # pinned Python dependencies
│   └── tools/
│       ├── scraper.py               # MCP scraper server
│       ├── search.py                # MCP search server
│       ├── cache.py                 # MCP cache server
│       ├── validator.py             # MCP validator server
│       └── bonial.py               # MCP Bonial/kaufDA server
└── frontend/
    ├── .env                         # VITE_API_URL (git-ignored)
    ├── .env.example
    ├── src/
    │   ├── App.jsx                  # main layout — search + chat
    │   ├── components/
    │   │   ├── VoucherCard.jsx
    │   │   ├── ChatPanel.jsx
    │   │   └── StatsBar.jsx
    │   └── api.js                   # fetch helpers for /vouchers and /chat
    └── package.json
```

---

## Deploy to Render

Push to GitHub, then create a **Blueprint** deployment using the `render.yaml` at the repo root:

```yaml
services:
  - type: web
    name: pricehunt-backend
    runtime: python
    rootDir: backend
    buildCommand: pip install -r requirements.txt && playwright install chromium
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: BRAVE_API_KEY
        sync: false
      - key: REDDIT_CLIENT_ID
        sync: false
      - key: REDDIT_CLIENT_SECRET
        sync: false
      - key: REDIS_URL
        fromService:
          name: pricehunt-redis
          property: connectionString

  - type: static
    name: pricehunt-frontend
    rootDir: frontend
    buildCommand: npm install && npm run build
    staticPublishPath: dist
    envVars:
      - key: VITE_API_URL
        fromService:
          name: pricehunt-backend
          property: host

  - type: redis
    name: pricehunt-redis
    plan: free
```

---

## Built with

- **[LangGraph](https://langchain-ai.github.io/langgraph/)** — stateful agent graph with reflection loop
- **[Claude](https://anthropic.com)** — Sonnet 4 for planning/reflection, Haiku for extraction
- **[MCP](https://modelcontextprotocol.io)** — each tool is an independent MCP server
- **[Playwright](https://playwright.dev)** — headless browser for checkout validation
- **[FastAPI](https://fastapi.tiangolo.com)** — async Python backend
- **[React + Vite](https://vitejs.dev)** — frontend
- **[Render](https://render.com)** — deployment
