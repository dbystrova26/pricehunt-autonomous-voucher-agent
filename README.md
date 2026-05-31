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
Idealo    SerpAPI
            │
         Validator
         MCP server
         (Playwright)
            │
         Bonial MCP server
         (kaufDA leaflets)
```

---

## Where MCP is used

MCP (Model Context Protocol) is the communication layer between the **LangGraph agent** and each **tool server**. Instead of hardcoding scraping logic inside the agent, each data source runs as an independent MCP server. The agent discovers available tools at startup and calls them by name over JSON-RPC.

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

**Why not SerpAPI:** SerpAPI costs $50/month minimum. Good for production but
overkill for a student project. Brave covers the same use case for free.

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
Users post codes the moment they find them. It's especially powerful for flash sales
and limited-time codes that expire before scrapers catch up.

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
app earns a small commission per purchase, which is exactly how Joko monetises.

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

**Why optional for MVP:** For a demo and student project, local Playwright works fine
on most merchants. Add Browserbase if you get blocked on specific sites.

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
run — it needs to be instant. Postgres is used for slower historical analytics.

**How to get locally:**
```bash
brew install redis && redis-server   # macOS
# or
docker run -p 6379:6379 redis:alpine
```
On Render: add the Redis add-on in your dashboard → it injects `REDIS_URL` automatically.

```
REDIS_URL=redis://localhost:6379     # local
# Render sets this automatically in production
```

---

### 🐘 PostgreSQL *(auto-configured on Render)*
**What:** Relational database. Used for:
- Long-term run history per merchant (beyond Redis TTL)
- Code success/failure logs for analytics
- User session data

**How to get locally:**
```bash
brew install postgresql && pg_ctl start   # macOS
# or
docker run -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres:16
```
On Render: add the Postgres add-on → injects `DATABASE_URL` automatically.

```
DATABASE_URL=postgresql://user:pass@localhost:5432/pricehunt
# Render sets this automatically in production
```

---

## Full `.env` file

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
BROWSERBASE_PROJECT_ID=prj_...          # browserbase.com

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
pricehunt/
├── README.md
├── render.yaml
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
│   ├── main.py
│   ├── agent.py
│   ├── memory.py
│   ├── requirements.txt
│   └── tools/
│       ├── scraper.py
│       ├── search.py
│       ├── cache.py
│       ├── validator.py
│       └── bonial.py
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── components/
    │   │   ├── VoucherCard.jsx
    │   │   ├── ChatPanel.jsx
    │   │   └── StatsBar.jsx
    │   └── api.js
    └── package.json
```

---

## Local setup

```bash
# Backend
cd backend
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in your keys
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000" > .env
npm run dev
```

---

## Deploy to Render

```yaml
# render.yaml — place at repo root
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

---

*Built for Ironhack final project · Frankfurt 2025*
