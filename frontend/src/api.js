/**
 * Pricehunt API client
 * All calls go to FastAPI backend — POST /vouchers, POST /chat, GET /merchants/:name/stats
 * In local dev, Vite proxies these to http://localhost:8000 (see vite.config.js)
 * In production, VITE_API_URL is injected by Render from render.yaml
 */

const BASE = import.meta.env.VITE_API_URL || ''

// ── POST /vouchers ────────────────────────────────────────────────────────────
/**
 * Run the full autonomous agent for a merchant.
 * @param {string} merchantUrl  - URL or plain merchant name e.g. "zalando.de"
 * @param {number|null} minSaving - only return codes saving >= this EUR amount
 * @param {number} maxCodes     - cap validated results (default 5)
 * @returns {Promise<SearchResponse>}
 */
export async function findVouchers(merchantUrl, minSaving = null, maxCodes = 5) {
  const res = await fetch(`${BASE}/vouchers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      merchant_url: merchantUrl,
      min_saving:   minSaving,
      max_codes:    maxCodes,
    }),
  })
  if (!res.ok) throw new Error(`Agent error: ${res.status}`)
  return res.json()
}

// ── POST /chat ────────────────────────────────────────────────────────────────
/**
 * Send a chat message to the agent with full conversation history.
 * The agent may re-run tools, filter results, explain decisions, or just respond.
 * @param {string} message          - user's plain language message
 * @param {Array}  history          - [{role, content}, ...] full conversation so far
 * @param {string|null} merchantContext - merchant currently shown in the left panel
 * @returns {Promise<ChatResponse>}
 */
export async function sendChatMessage(message, history, merchantContext = null) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      history,
      merchant_context: merchantContext,
    }),
  })
  if (!res.ok) throw new Error(`Chat error: ${res.status}`)
  return res.json()
}

// ── POST /vouchers/stream ─────────────────────────────────────────────────────
/**
 * Streaming version of findVouchers — yields agent status events via SSE.
 * Each event has shape: {status, message?, tool?, result?}
 * @param {string} merchantUrl
 * @param {function} onEvent  - called for each parsed event
 * @param {function} onDone   - called with the final SearchResponse
 */
export async function streamVouchers(merchantUrl, onEvent, onDone) {
  const res = await fetch(`${BASE}/vouchers/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ merchant_url: merchantUrl }),
  })

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n\n')
    buffer = lines.pop()              // keep incomplete chunk

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const event = JSON.parse(line.slice(6))
      if (event.status === 'done') {
        onDone(event.result)
      } else {
        onEvent(event)
      }
    }
  }
}

// ── GET /merchants/:name/stats ────────────────────────────────────────────────
/**
 * Returns what the agent has learned about a merchant from past runs.
 * Used to show "Agent has run X times for this merchant" in the UI.
 */
export async function getMerchantStats(merchant) {
  const res = await fetch(`${BASE}/merchants/${encodeURIComponent(merchant)}/stats`)
  if (!res.ok) return null
  return res.json()
}

// ── GET /health ───────────────────────────────────────────────────────────────
export async function checkHealth() {
  try {
    const res = await fetch(`${BASE}/health`)
    return res.ok
  } catch {
    return false
  }
}
