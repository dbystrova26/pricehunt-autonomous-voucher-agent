import { useState, useRef, useEffect } from 'react'
import { sendChatMessage } from '../api.js'
import styles from './ChatPanel.module.css'

const QUICK_REPLIES = [
  'Find codes for Nike',
  'Only show savings over €10',
  'Search Reddit for fresher codes',
  'Why did WELCOME10 only save €10?',
  'Try H&M instead',
  'Show Bonial deals near me',
  'How confident are you this code works?',
  'How does the agent work?',
]

const WELCOME = {
  role: 'agent',
  content: `Hey! 👋 I'm your autonomous deal-hunting agent. Paste a merchant URL or name in the search box — or just tell me what you're shopping for and I'll find the best codes.

You can also ask things like:
• "Only show codes saving more than €15"
• "Search Reddit for fresher Zalando codes"
• "Why did this code only save €10?"`,
}

export default function ChatPanel({ merchantContext, onNewCodes }) {
  const [history, setHistory]   = useState([WELCOME])
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const bottomRef               = useRef(null)

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history])

  async function send(text) {
    if (!text.trim() || loading) return

    const userMsg = { role: 'user', content: text }
    const newHistory = [...history, userMsg]
    setHistory(newHistory)
    setInput('')
    setLoading(true)

    try {
      // Build conversation history in the format the backend expects
      const apiHistory = newHistory
        .filter(m => m.role !== 'agent' || m !== WELCOME)
        .map(m => ({ role: m.role === 'agent' ? 'assistant' : 'user', content: m.content }))

      const response = await sendChatMessage(text, apiHistory, merchantContext)

      const agentMsg = { role: 'agent', content: response.reply }
      setHistory(prev => [...prev, agentMsg])

      // If agent found new/updated codes, surface them in the left panel
      if (response.updated_codes?.length) {
        onNewCodes?.({
          merchant: merchantContext || 'Results',
          codes: response.updated_codes,
          agent_reasoning: response.reply,
        })
      }
    } catch (err) {
      setHistory(prev => [...prev, {
        role: 'agent',
        content: `Sorry, something went wrong: ${err.message}. Is the backend running?`,
        error: true,
      }])
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(input)
    }
  }

  function clearChat() {
    setHistory([WELCOME])
  }

  return (
    <div className={styles.panel}>

      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.avatar}>⚡</div>
          <div>
            <div className={styles.title}>Pricehunt Agent</div>
            <div className={styles.status}>
              <span className={`${styles.dot} ${loading ? styles.thinking : ''}`}/>
              {loading ? 'Thinking...' : 'Ready to hunt deals'}
            </div>
          </div>
        </div>
        <button className={styles.clearBtn} onClick={clearChat}>Clear</button>
      </div>

      {/* Messages */}
      <div className={styles.messages}>
        {history.map((msg, i) => (
          <div
            key={i}
            className={`${styles.msg} ${msg.role === 'user' ? styles.user : styles.agent} ${msg.error ? styles.error : ''}`}
          >
            {msg.role === 'agent' && <div className={styles.label}>Pricehunt Agent</div>}
            {/* Render newlines as line breaks */}
            {msg.content.split('\n').map((line, j) => (
              <span key={j}>
                {line}
                {j < msg.content.split('\n').length - 1 && <br />}
              </span>
            ))}
          </div>
        ))}

        {/* Typing indicator */}
        {loading && (
          <div className={`${styles.msg} ${styles.agent} ${styles.typing}`}>
            <div className={styles.label}>Pricehunt Agent</div>
            Agent is thinking
            <span className={styles.dots}>
              <span/><span/><span/>
            </span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Quick replies */}
      <div className={styles.quickReplies}>
        {QUICK_REPLIES.map(qr => (
          <button key={qr} className={styles.qr} onClick={() => send(qr)}>
            {qr}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className={styles.inputArea}>
        <div className={styles.inputRow}>
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask the agent anything, or describe what you need..."
            disabled={loading}
          />
          <button
            className={styles.sendBtn}
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
          >
            ↑
          </button>
        </div>
        <div className={styles.inputHint}>
          ⚡ Autonomous agent · finds, validates &amp; ranks codes in real time
        </div>
      </div>
    </div>
  )
}
