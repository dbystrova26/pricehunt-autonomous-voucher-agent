import { useState, useEffect } from 'react'
import { findVouchers, streamVouchers, checkHealth } from './api.js'
import VoucherCard from './components/VoucherCard.jsx'
import ChatPanel   from './components/ChatPanel.jsx'
import StatsBar    from './components/StatsBar.jsx'
import styles      from './App.module.css'

// ── Bolt SVG logo mark ───────────────────────────────────────────────────────
function Bolt({ size = 18, color = '#4ade80' }) {
  return (
    <svg width={size} height={size + 2} viewBox="0 0 18 20" fill="none">
      <path d="M10 1L1 12h7L6 19l11-11h-7L10 1z"
        fill={color} stroke={color} strokeWidth="0.3" strokeLinejoin="round"/>
    </svg>
  )
}

// ── Agent status messages shown during streaming ──────────────────────────────
const STATUS_LABELS = {
  planning:   '🧠 Planning which sources to use...',
  tool_call:  (e) => `🔍 ${e.message || 'Calling tool...'}`,
  validating: '✅ Validating codes at real checkout...',
  reflecting: '🤔 Evaluating results...',
}

export default function App() {
  const [urlInput,     setUrlInput]     = useState('')
  const [results,      setResults]      = useState([])   // array of SearchResponse
  const [loading,      setLoading]      = useState(false)
  const [agentStatus,  setAgentStatus]  = useState('')   // live streaming message
  const [activeTab,    setActiveTab]    = useState('codes')
  const [agentOnline,  setAgentOnline]  = useState(null) // null = checking
  const [stats,        setStats]        = useState({ saved: 47, codes: 12, merchants: 3 })

  // Check backend health on mount
  useEffect(() => {
    checkHealth().then(ok => setAgentOnline(ok))
  }, [])

  // Recalculate stats whenever results change
  useEffect(() => {
    const totalSaved  = results.reduce((sum, r) => sum + (r.codes?.[0]?.saving_eur || 0), 0)
    const totalCodes  = results.reduce((sum, r) => sum + (r.codes?.length || 0), 0)
    setStats({
      saved:     totalSaved > 0 ? Math.round(totalSaved) : 47,
      codes:     totalCodes > 0 ? totalCodes : 12,
      merchants: results.length > 0 ? results.length : 3,
    })
  }, [results])

  // ── Main search ─────────────────────────────────────────────────────────────
  async function handleSearch() {
    const query = urlInput.trim()
    if (!query || loading) return
    setLoading(true)
    setAgentStatus('🧠 Starting agent...')

    try {
      // Use streaming for live feedback if backend supports it
      let done = false
      await streamVouchers(
        query,
        (event) => {
          const label = typeof STATUS_LABELS[event.status] === 'function'
            ? STATUS_LABELS[event.status](event)
            : STATUS_LABELS[event.status] || event.message || ''
          setAgentStatus(label)
        },
        (result) => {
          done = true
          setResults(prev => {
            // Replace if same merchant already in results, otherwise prepend
            const existing = prev.findIndex(r =>
              r.merchant.toLowerCase() === result.merchant.toLowerCase())
            if (existing >= 0) {
              const updated = [...prev]
              updated[existing] = result
              return updated
            }
            return [result, ...prev]
          })
          setAgentStatus('')
        }
      ).catch(async () => {
        // Fallback: non-streaming call if SSE not supported
        if (!done) {
          const result = await findVouchers(query)
          setResults(prev => [result, ...prev])
          setAgentStatus('')
        }
      })
    } catch (err) {
      setAgentStatus(`❌ Error: ${err.message}`)
      setTimeout(() => setAgentStatus(''), 4000)
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSearch()
  }

  // Called by ChatPanel when agent finds updated codes via chat
  function handleNewCodes(result) {
    setResults(prev => {
      const existing = prev.findIndex(r =>
        r.merchant?.toLowerCase() === result.merchant?.toLowerCase())
      if (existing >= 0) {
        const updated = [...prev]
        updated[existing] = { ...updated[existing], ...result }
        return updated
      }
      return [result, ...prev]
    })
  }

  // Called when user applies a code — add to chat history as confirmation
  function handleApply(message) {
    // No-op here — ChatPanel handles its own history
    // Could trigger a POST to log the application in future
    console.log('Applied:', message)
  }

  const currentMerchant = results[0]?.merchant || null

  return (
    <div className={styles.layout}>

      {/* ── HEADER ─────────────────────────────────────────────────────────── */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.logoBolt}>
            <Bolt size={18} color="#4ade80" />
          </div>
          <div>
            <div className={styles.logoText}>Pricehunt</div>
            <div className={styles.logoSub}>Autonomous voucher agent</div>
          </div>
        </div>
        <div className={`${styles.headerTag} ${agentOnline === false ? styles.offline : ''}`}>
          {agentOnline === null  ? '⏳ Connecting...'  :
           agentOnline === false ? '❌ Agent offline'  :
           '⚡ Agent online'}
        </div>
      </div>

      {/* ── LEFT: APP PANEL ────────────────────────────────────────────────── */}
      <div className={styles.appCol}>

        {/* Nav */}
        <div className={styles.appNav}>
          <div className={styles.navBrand}>
            <div className={styles.navBolt}><Bolt size={13} color="#4ade80" /></div>
            <span className={styles.navName}>Pricehunt</span>
          </div>
          <div className={styles.navActions}>
            <button className={styles.navBtn}>🔔</button>
            <button className={styles.navBtn}>👤</button>
          </div>
        </div>

        {/* Hero search */}
        <div className={styles.appHero}>
          <div className={styles.heroEyebrow}>Autonomous deal agent</div>
          <div className={styles.heroTitle}>Hunt the price.<br/>Keep the savings.</div>
          <div className={styles.searchBox}>
            <span>🔍</span>
            <input
              type="text"
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Paste checkout URL or merchant name..."
              disabled={loading}
            />
            <button className={styles.searchGo} onClick={handleSearch} disabled={loading}>
              {loading ? '⏳' : '↵'}
            </button>
          </div>
          {/* Live agent status during search */}
          {agentStatus && (
            <div className={styles.agentStatus}>{agentStatus}</div>
          )}
        </div>

        {/* Body */}
        <div className={styles.appBody}>

          <StatsBar
            totalSaved={stats.saved}
            codesFound={stats.codes}
            merchants={stats.merchants}
          />

          {/* Tab bar */}
          <div className={styles.secLabel}>
            {activeTab === 'codes' ? 'Best codes found' : 'Cashback pending'}
          </div>

          {/* Results or empty state */}
          {activeTab === 'codes' && (
            results.length === 0 ? (
              <div className={styles.emptyState}>
                <div className={styles.emptyIcon}>🎯</div>
                <div className={styles.emptyTitle}>No hunts yet</div>
                <div className={styles.emptySub}>
                  Paste a merchant URL or name above and hit ↵
                </div>
              </div>
            ) : (
              results.map((r, i) => (
                <VoucherCard key={i} result={r} onApply={handleApply} />
              ))
            )
          )}

          {activeTab === 'cashback' && (
            <div className={styles.comingSoon}>
              💳 Cashback tracking coming soon
            </div>
          )}

        </div>

        {/* Bottom tab bar */}
        <div className={styles.botTab}>
          {[
            { id: 'codes',    icon: '🎫', label: 'Codes'    },
            { id: 'cashback', icon: '%',  label: 'Cashback' },
            { id: 'saved',    icon: '❤️', label: 'Saved'    },
            { id: 'profile',  icon: '👤', label: 'Profile'  },
          ].map(t => (
            <div
              key={t.id}
              className={`${styles.btab} ${activeTab === t.id ? styles.btabOn : ''}`}
              onClick={() => setActiveTab(t.id)}
            >
              <span>{t.icon}</span>
              {t.label}
            </div>
          ))}
        </div>
      </div>

      {/* ── RIGHT: CHAT PANEL ──────────────────────────────────────────────── */}
      <ChatPanel
        merchantContext={currentMerchant}
        onNewCodes={handleNewCodes}
      />

    </div>
  )
}
