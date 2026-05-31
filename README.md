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
Retailme  Tavily     Redis
Not,Honey Reddit     Postgres
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
| `search` | search-mcp-server | Tavily Search + Reddit → Sonnet extracts codes |
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

A Claude Sonnet call receives the full run context and must respond with a JSON decision:

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
          ──MCP──►  search-mcp-server    (tavily_search, reddit_search)
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

> **TL;DR — you only need 2 keys to run Pricehunt.**
> Scraping (RetailMeNot, Honey, Idealo, Bonial) requires no API keys at all —
> it is plain Playwright loading public web pages. The only keys needed are the
> LLM brain and the web search layer.

---

## ✅ Required APIs (just these two)

### 🧠 Anthropic API
**What:** The LLM powering every part of the agent. One model, used everywhere:
- `claude-sonnet-4-6` — planner, reflection, code extraction, and chat responses.

A single model keeps the codebase simple and reasoning quality consistent across
all agent nodes.

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

### 🔍 Tavily Search API
**What:** A search API built specifically for AI agents. Returns clean, LLM-optimised
snippets with no SEO noise. Used to find codes buried in blog posts, deal forums,
and news articles that scraping aggregators like RetailMeNot miss.

**Why Tavily over alternatives:**

| | Tavily | Brave Search | Google CSE |
|---|---|---|---|
| Free tier | 1,000 req/mo, no credit card | ~1,000 req/mo but requires billing setup | 100/day then $5/1k |
| Built for AI | ✅ Pre-structured for LLMs | ❌ Raw results | ❌ Raw results |
| Official Python SDK | ✅ `pip install tavily-python` | ❌ Manual HTTP client | ❌ Manual HTTP client |
| Setup friction | Sign up, get key, done | Requires payment method on file | Requires Google Cloud project |

**How to get:**
1. Go to https://app.tavily.com
2. Sign up — email only, no credit card
3. Overview (left sidebar) → copy your `tvly-dev-...` key

```
TAVILY_API_KEY=tvly-...
```

> **Cost estimate:** Each agent run fires 2–3 Tavily queries.
> 1,000 free requests/month = ~300–500 full agent runs before any charge.

---

## ⏭ Future development — APIs that would enrich the data

These were researched and evaluated during development. None are required for
the MVP but each adds a meaningful data layer. Limitations encountered are noted
so future contributors know what to expect.

---

### 🤖 Reddit API
**What it would add:** Access to r/deals, r/promo_codes, r/frugal and
merchant-specific subreddits. Reddit is often 24–48 hours ahead of RetailMeNot
for fresh codes — users post flash sale codes the moment they go live, before
aggregators catch up.

**How to get:**
1. Go to https://www.reddit.com/prefs/apps
2. Choose type: **script**, redirect URI: `http://localhost`
3. Copy `client_id` and `client_secret`

```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
```

**⚠️ Limitation encountered:** Reddit introduced a mandatory
[Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564)
in 2026 which requires explicit approval before creating API apps. The approval
process was not instant during development. Tavily partially covers this gap as
it indexes Reddit pages in its web search results.

---

### 🛒 Rakuten Advertising API
**What it would add:** Structured cashback rates and affiliate links for 2,500+
EU and US merchants. Unlocks a revenue model — if users click through Pricehunt's
tracked links, the app earns a commission per purchase (same model Joko uses).
Also provides exclusive promo codes from direct merchant partnerships not
available on public aggregators.

**How to get:**
1. Sign up as a Publisher at https://rakutenadvertising.com
2. Wait for approval (1–2 business days)
3. Account → API Access → generate key

```
RAKUTEN_API_KEY=...
```

**⚠️ Limitation encountered:** Rakuten requires full account setup including
address, tax declaration, and channel verification before granting API access.
This is a multi-step process designed for established publishers — not a quick
signup. Apply early if you need this for production.

---

### 🌐 Browserbase API
**What it would add:** Managed cloud browser sessions with built-in anti-bot
handling, residential proxies, and CAPTCHA solving. Replaces local Playwright
for the checkout validation step — merchant checkout pages see a real browser
session instead of a detectable headless one.

**How to get:**
1. Sign up at https://browserbase.com
2. Create Project → copy API key and project ID

```
BROWSERBASE_API_KEY=bb_...
BROWSERBASE_PROJECT_ID=prj_...
```

**⚠️ Limitation encountered:** Not needed for most merchants during development.
Local Playwright worked on Zalando, About You, H&M. Add Browserbase only if
you see `error: "blocked"` responses from the validator on specific sites.
Usage-based pricing — cost scales with number of validations.

---

### 📰 Bonial / kaufDA Partnership API
**What it would add:** Structured weekly leaflet feed from 500+ EU retailers
instead of scraping. Push notifications when new leaflets go live. Full
merchant catalogue with IDs. Currently the agent scrapes kaufDA.de directly
which works but is fragile to site changes.

**How to get:** Contact partner@bonial.com — this is a business partnership,
not a self-serve API. Bonial's platform (kaufDA in DE, Bonial in FR) is the
EU market leader for digital leaflets.

**⚠️ Limitation encountered:** No public API exists. Scraping works for MVP
but a formal partnership would give structured data and remove scraping
maintenance overhead.

---

## Full `.env` file

Copy `backend/.env.example` to `backend/.env` and fill in your values.

**Minimum to run the agent (just these two):**

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...       # platform.anthropic.com
TAVILY_API_KEY=tvly-...                  # app.tavily.com → Overview
```

**Full file with all optional keys:**

```bash
# ── REQUIRED ─────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-...       # platform.anthropic.com
TAVILY_API_KEY=tvly-...                  # app.tavily.com (1k free/mo, no credit card)

# ── FUTURE DEVELOPMENT — add when needed ─────────────────────────
# Reddit API — fresh codes from r/deals (blocked by new policy in 2026)
REDDIT_CLIENT_ID=                        # reddit.com/prefs/apps → script app
REDDIT_CLIENT_SECRET=                    # same page

# Rakuten Affiliate — cashback rates + revenue model (requires full account setup)
RAKUTEN_API_KEY=                         # rakutenadvertising.com → publisher signup

# Browserbase — managed cloud browsers if Playwright gets blocked
BROWSERBASE_API_KEY=                     # browserbase.com
BROWSERBASE_PROJECT_ID=                  # browserbase.com

# ── INFRASTRUCTURE ────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379         # Render auto-fills in production
DATABASE_URL=postgresql://...            # Render auto-fills in production
FRONTEND_URL=http://localhost:5173       # Render auto-fills in production
```

> **Note on scraping:** RetailMeNot, Honey, Idealo, and Bonial/kaufDA are scraped
> directly using Playwright — no API key required. These are public websites.
> The agent loads them like a browser and parses the HTML.

---

## Local setup

### Prerequisites

- Python 3.11+ — https://www.python.org/downloads/
- A modern browser (Chrome, Firefox, Edge)
- `ANTHROPIC_API_KEY` — from https://platform.anthropic.com
- `TAVILY_API_KEY` — from https://app.tavily.com

> **Node.js is NOT required.** The frontend is a plain HTML file — no build step.

> **Windows users:** Git Bash (comes with Git for Windows) is the easiest terminal
> for these commands. All commands below work in Git Bash as written.

---

### Step 1 — Clone the repo

```bash
git clone https://github.com/dbystrova26/pricehunt-autonomous-voucher-agent.git
cd pricehunt-autonomous-voucher-agent
```

---

### Step 2 — Create the virtual environment

```bash
cd backend
python -m venv .venv
```

Activate it:

```bash
# Git Bash / macOS / Linux:
source .venv/Scripts/activate

# Windows Command Prompt:
# .venv\Scriptsctivate.bat

# Windows PowerShell:
# .venv\Scripts\Activate.ps1
```

Your prompt should now show `(.venv)`.

```bash
# Install dependencies (use --prefer-binary to avoid compiler errors on Windows)
pip install -r requirements.txt --prefer-binary

# Install the Chromium browser for Playwright checkout validation
playwright install chromium
```

> **Note:** The `.venv` folder is gitignored — never commit it.
> Anyone cloning the repo runs these steps to recreate it locally.

To reactivate in a new terminal:
```bash
cd backend
source .venv/Scripts/activate
```

---

### Step 3 — Set up your `.env` file

```bash
# Copy the template
cp .env.example .env
```

Open `backend/.env` and fill in your two required keys:

```bash
ANTHROPIC_API_KEY=sk-ant-...    # platform.anthropic.com → API Keys → Create Key
TAVILY_API_KEY=tvly-dev-...     # app.tavily.com → Overview → copy key
```

Leave everything else as-is for local development:

```bash
REDDIT_CLIENT_ID=               # optional — skip for now
REDDIT_CLIENT_SECRET=           # optional — skip for now
RAKUTEN_API_KEY=                 # optional — skip for now
BROWSERBASE_API_KEY=             # optional — skip for now
BROWSERBASE_PROJECT_ID=          # optional — skip for now
REDIS_URL=redis://localhost:6379 # leave as-is
DATABASE_URL=                    # leave empty
FRONTEND_URL=http://localhost:5173
```

---

### Step 4 — Start the backend

Make sure your venv is active, then:

```bash
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

Check it's working: open http://localhost:8000/docs in your browser —
FastAPI auto-generates interactive API docs showing all endpoints.

---

### Step 5 — Start the frontend

Open a **second terminal** (keep the backend running in the first):

```bash
cd frontend
python -m http.server 5173
```

Open http://localhost:5173 in your browser.

---

## How to use the app

Once both servers are running:

### 1. Check the agent is online
The header should show **⚡ Agent online**. If it shows ❌ offline, check
that `uvicorn` is running in your first terminal.

### 2. Search for voucher codes
Paste a merchant URL or name into the search box and press Enter:
```
zalando.de
https://www.aboutyou.de/checkout
Nike
MediaMarkt Germany
```

The agent will:
- Check its cache (instant if seen before)
- Scrape RetailMeNot, Honey, Idealo in parallel
- Search Tavily for fresh codes in blogs and forums
- Check Bonial/kaufDA for EU in-store deals
- Validate the top codes at real checkout with Playwright
- Return the best codes ranked by saving

### 3. Copy or apply a code
- Click **📋 Copy** to copy a code to clipboard
- Click **⚡ Auto-apply best code** to simulate auto-applying at checkout

### 4. Refine results using the chat
The right panel is a live chat with the agent. Try:
```
Only show codes saving more than €15
Search Reddit for fresher Zalando codes
Why did WELCOME10 only save €10?
Try H&M instead
Any in-store deals near Frankfurt this week?
```

The agent re-runs tools or filters results based on your message and
updates the left panel automatically.

### 5. Ask how the agent thinks
```
What sources did you check?
Why did you skip the search tool this time?
How confident are you this code still works?
How does the agent work?
```

The agent explains its own reasoning — this is the reflection node in action.

---

### Quick start with Make

```bash
make setup        # create venv, install Python deps, install Chromium
make redis-start  # start Redis (auto-detects Linux/macOS/WSL2)
make backend      # start FastAPI on port 8000
make clean        # remove .venv
```

Then in a second terminal:
```bash
cd frontend && python -m http.server 5173
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
│       ├── tavily-search.md         # tool definition: tavily_search
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
    ├── index.html                   # ★ THE DEPLOYED FILE — plain HTML, real API calls
    ├── .env.example                 # local dev only (not needed for deploy)
    └── src/                         # React reference implementation (not deployed)
        ├── main.jsx                 # React root mount
        ├── index.css                # global CSS design tokens
        ├── App.jsx                  # main layout — search + results + tabs
        ├── App.module.css
        ├── api.js                   # all backend calls in one place
        └── components/
            ├── VoucherCard.jsx      # one merchant result card
            ├── VoucherCard.module.css
            ├── ChatPanel.jsx        # chat with history, quick replies, streaming
            ├── ChatPanel.module.css
            ├── StatsBar.jsx         # saved / codes / merchants counters
            └── StatsBar.module.css
```

---

## Frontend — why plain HTML, not React

The frontend is a single `index.html` file. No build step, no npm, no framework.

This is a deliberate choice. React and Vite are powerful but they add complexity
that this project does not need:

| | Plain HTML (`index.html`) | React + Vite |
|---|---|---|
| Deploy | Copy one file | Run `npm install && npm run build` first |
| Dependencies | Zero | ~200 packages in `node_modules` |
| Debug | Open in browser directly | Need dev server running |
| Render config | `buildCommand: ""` | `buildCommand: npm install && npm run build` |
| What Render actually serves | The file as-is | The compiled `dist/` folder |

The key insight: **React compiles down to plain HTML/CSS/JS anyway.**
Render never runs React itself — it just serves the compiled output.
So for a single-page tool like Pricehunt, skipping the compilation step
and writing that plain HTML/CSS/JS directly is strictly simpler.

The `frontend/src/` React components are included in the repo as a reference
implementation showing how the app would scale if it grew to multiple pages.
But the actual deployed file is `frontend/index.html`.

---

## How the frontend talks to the backend

The `index.html` uses plain `fetch()` to call the FastAPI backend.
The backend URL is configured in one place at the top of the script block:

```javascript
// In frontend/index.html
const BACKEND = window.__BACKEND_URL__ || 'http://localhost:8000';
```

In **local development** this defaults to `http://localhost:8000` — your
FastAPI server running locally. Open `index.html` directly in a browser or
serve it with Python:

```bash
cd frontend
python3 -m http.server 5173
# → open http://localhost:5173
```

In **production on Render**, the `render.yaml` injects the real backend URL
via a sed command in the build step (see below).

---

## Deploy to Render — step by step

### What you will have after deploying

```
https://pricehunt-backend.onrender.com   ← FastAPI agent (Python web service)
https://pricehunt-frontend.onrender.com  ← index.html    (static site, free)
```

Both are free tier. Render connects them automatically.

### Step 1 — push to GitHub

```bash
git init
git add .
git commit -m "feat: scaffold full-stack MVP — LangGraph agent, FastAPI backend, vanilla HTML frontend"
git remote add origin https://github.com/your-username/pricehunt-autonomous-voucher-agent.git
git push -u origin main
```

### Step 2 — create a Render Blueprint

Go to https://render.com → New → Blueprint → connect your GitHub repo.
Render reads `render.yaml` and creates all three services automatically.

### Step 3 — add your secret API keys

Render will pause and ask you to fill in the keys marked `sync: false`.
Enter them one by one in the Render dashboard:

```
ANTHROPIC_API_KEY   → your sk-ant-... key
TAVILY_API_KEY      → your tvly-... key
REDDIT_CLIENT_ID    → from reddit.com/prefs/apps
REDDIT_CLIENT_SECRET
RAKUTEN_API_KEY     → optional, for cashback
```

Click **Apply** — Render deploys both services and the Redis instance.

### Step 4 — done

Render gives you two URLs. Open the frontend URL in a browser.
The health check in `index.html` pings the backend on load and shows
"⚡ Agent online" in the header when everything is connected.

---

## render.yaml explained line by line

```yaml
services:

  # ── Backend: Python web service ───────────────────────────────────────────
  - type: web
    name: pricehunt-backend
    runtime: python
    rootDir: backend          # Render looks for requirements.txt here
    buildCommand: >
      pip install -r requirements.txt &&
      playwright install chromium
      # Installs Python deps then downloads the Chromium browser binary
      # needed by the Playwright checkout validator
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
      # $PORT is injected by Render — never hardcode a port number
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false           # "sync: false" = you type this in the dashboard
      - key: TAVILY_API_KEY
        sync: false
      - key: REDDIT_CLIENT_ID
        sync: false
      - key: REDDIT_CLIENT_SECRET
        sync: false
      - key: REDIS_URL
        fromService:          # Render wires this automatically from the
          name: pricehunt-redis   # Redis instance below — no copy-paste needed
          property: connectionString

  # ── Frontend: static site (plain HTML) ────────────────────────────────────
  - type: static
    name: pricehunt-frontend
    rootDir: frontend
    buildCommand: >
      sed -i "s|http://localhost:8000|https://pricehunt-backend.onrender.com|g" index.html
      # This is the entire "build" step.
      # It replaces the localhost URL in index.html with the real backend URL.
      # No npm, no node_modules, no compilation — one sed command.
    staticPublishPath: .      # serve the folder as-is after the sed command
    headers:
      - path: /*
        name: Cache-Control
        value: no-cache       # always serve fresh HTML (important for an agent app)

  # ── Redis: free 25MB instance ─────────────────────────────────────────────
  - type: redis
    name: pricehunt-redis
    plan: free                # 25MB — enough for code cache + agent memory
    maxmemoryPolicy: allkeys-lru   # evict oldest keys when full
```

### Why `sed` instead of a build tool

The only thing that differs between local and production is one URL string.
Using `sed` to swap it at deploy time is simpler than setting up a bundler,
environment variables in JavaScript, or a build pipeline.

`sed -i "s|OLD|NEW|g" file` replaces every occurrence of OLD with NEW
in-place (`-i`) in the file. One command, zero dependencies.

---

## Built with

- **[LangGraph](https://langchain-ai.github.io/langgraph/)** — stateful agent graph with reflection loop
- **[Claude](https://anthropic.com)** — Sonnet 4 throughout: planning, reflection, and extraction
- **[MCP](https://modelcontextprotocol.io)** — each tool is an independent MCP server
- **[Playwright](https://playwright.dev)** — headless browser for checkout validation
- **[FastAPI](https://fastapi.tiangolo.com)** — async Python backend
- **[Vanilla HTML/CSS/JS](https://developer.mozilla.org/en-US/docs/Web/HTML)** — frontend (no framework, no build step)
- **[Render](https://render.com)** — deployment
