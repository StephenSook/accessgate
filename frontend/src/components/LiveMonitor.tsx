/**
 * LiveMonitor — real-time CPS and WPM meters via WebSocket.
 * Shows a "LIVE" badge with pulse indicator when connected.
 */
import { useEffect, useRef, useState } from 'react'

interface LiveMetrics {
  cps: number
  wpm: number
  violations: string[]
  status: 'pass' | 'warn' | 'fail' | 'error'
  latency_ms: number
}

export function LiveMonitor() {
  const [connected, setConnected] = useState(false)
  const [metrics, setMetrics] = useState<LiveMetrics | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  function connect() {
    if (wsRef.current) return
    const ws = new WebSocket(`ws://${location.host}/live`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => { setConnected(false); wsRef.current = null }
    ws.onmessage = (e) => {
      try {
        setMetrics(JSON.parse(e.data))
      } catch { /* ignore */ }
    }
  }

  function disconnect() {
    wsRef.current?.close()
    wsRef.current = null
    setConnected(false)
    setMetrics(null)
  }

  useEffect(() => () => { wsRef.current?.close() }, [])

  const statusColor = metrics
    ? metrics.status === 'pass' ? 'var(--ag-green)'
    : metrics.status === 'fail' ? 'var(--ag-red)'
    : 'var(--ag-amber)'
    : 'var(--ag-text-muted)'

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {connected && metrics && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, display: 'flex', gap: 10, color: 'var(--ag-text-muted)' }}>
          <span style={{ color: statusColor }}>CPS {metrics.cps.toFixed(1)}</span>
          <span style={{ color: statusColor }}>WPM {metrics.wpm.toFixed(0)}</span>
        </div>
      )}
      <button
        onClick={connected ? disconnect : connect}
        aria-label={connected ? 'Disconnect live monitor' : 'Connect live monitor'}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'none',
          border: `1px solid ${connected ? 'var(--ag-green)' : 'var(--ag-border)'}`,
          color: connected ? 'var(--ag-green)' : 'var(--ag-text-muted)',
          padding: '4px 10px', fontSize: 11,
          fontFamily: 'var(--font-mono)', cursor: 'pointer',
          textTransform: 'uppercase', letterSpacing: 0.5,
        }}
      >
        {/* Pulse dot */}
        {connected && (
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--ag-green)',
            display: 'inline-block',
          }} aria-hidden="true" />
        )}
        {connected ? 'LIVE' : 'MONITOR'}
      </button>
    </div>
  )
}
