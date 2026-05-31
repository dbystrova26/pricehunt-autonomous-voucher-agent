import { useState } from 'react'
import styles from './VoucherCard.module.css'

export default function VoucherCard({ result, onApply }) {
  const { merchant, codes = [], bonial_deal, cached, latency_ms, agent_reasoning } = result
  const [appliedCode, setAppliedCode] = useState(null)
  const [copying, setCopying]         = useState(null)
  const [showReason, setShowReason]   = useState(false)

  // Initials for the merchant icon
  const initials = merchant.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()

  function handleCopy(code) {
    navigator.clipboard?.writeText(code).catch(() => {})
    setCopying(code)
    setTimeout(() => setCopying(null), 2000)
  }

  function handleApply(code, saving) {
    setAppliedCode(code)
    onApply?.(`Applied ${code} — saved €${saving}!`)
    setTimeout(() => setAppliedCode(null), 4000)
  }

  if (!codes.length) return (
    <div className={styles.card}>
      <div className={styles.head}>
        <div className={styles.icon}>{initials}</div>
        <div className={styles.meta}>
          <div className={styles.name}>{merchant}</div>
          <div className={styles.sub}>No valid codes found this run</div>
        </div>
      </div>
      {agent_reasoning && (
        <div className={styles.reasonStrip}>
          🧠 {agent_reasoning}
        </div>
      )}
    </div>
  )

  const best = codes[0]

  return (
    <div className={styles.card}>
      {/* Header row */}
      <div className={styles.head}>
        <div className={styles.icon}>{initials}</div>
        <div className={styles.meta}>
          <div className={styles.name}>{merchant}</div>
          <div className={styles.sub}>
            {codes.length} code{codes.length > 1 ? 's' : ''} found
            {cached ? ' · ⚡ cached' : ''}
            {latency_ms ? ` · ${(latency_ms / 1000).toFixed(1)}s` : ''}
          </div>
          {bonial_deal && (
            <div className={styles.bonialChip}>📰 Bonial: {bonial_deal}</div>
          )}
        </div>
        <div className={styles.savings}>–€{best.saving_eur.toFixed(0)}</div>
      </div>

      <hr className={styles.divider} />

      {/* Code rows */}
      {codes.map((c, i) => (
        <div key={c.code} className={styles.codeRow}
          style={i > 0 ? { paddingTop: 0, paddingBottom: i === codes.length - 1 ? 8 : 0 } : {}}>
          <div className={styles.codeLeft}>
            {i === 0 && <span className={styles.bestTag}>Best</span>}
            <span className={i === 0 ? styles.code : styles.codeDim}>{c.code}</span>
            <span className={styles.confidence}>
              {Math.round(c.confidence * 100)}%
            </span>
          </div>
          <button
            className={`${styles.copyBtn} ${copying === c.code ? styles.copied : ''}`}
            onClick={() => handleCopy(c.code)}
          >
            {copying === c.code ? '✅ Copied!' : '📋 Copy'}
          </button>
        </div>
      ))}

      {/* Apply button */}
      <button
        className={`${styles.applyBtn} ${appliedCode ? styles.applied : ''}`}
        onClick={() => handleApply(best.code, best.saving_eur)}
        disabled={!!appliedCode}
      >
        {appliedCode
          ? `✅ Applied! Saved €${best.saving_eur.toFixed(0)}`
          : '⚡ Auto-apply best code'}
      </button>

      {/* Bonial in-store strip */}
      {bonial_deal && (
        <div className={styles.bonialStrip}>
          <span>📰</span>
          <span>{bonial_deal}</span>
          <div className={styles.bonialTag}>kaufDA</div>
        </div>
      )}

      {/* Agent reasoning toggle */}
      {agent_reasoning && (
        <div className={styles.reasonWrap}>
          <button className={styles.reasonToggle} onClick={() => setShowReason(v => !v)}>
            🧠 {showReason ? 'Hide' : 'How the agent found this'}
          </button>
          {showReason && <div className={styles.reasonText}>{agent_reasoning}</div>}
        </div>
      )}
    </div>
  )
}
