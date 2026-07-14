/**
 * GatedFixPanel — slide-in panel for the Granite Vision -> DCMP -> Guardian fix loop.
 *
 * Shows: gap region, draft text from Granite Vision, DCMP validation,
 * Guardian screen result. "Accept Fix" button flips row green.
 * Includes watsonx.ai Lite side-by-side when available.
 * This is the demo centerpiece.
 */
import React, { useState } from 'react'
import type { FixResult } from '../api/client'
import { requestFix, loadDemoFix } from '../api/client'

interface Props {
  gap: { start: number; end: number }
  filmFile: File | null
  demoMode?: boolean
  onClose: () => void
  onAccepted: () => void
}

export function GatedFixPanel({ gap, filmFile, demoMode, onClose, onAccepted }: Props) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<FixResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [accepted, setAccepted] = useState(false)

  async function runFix() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const fix = (demoMode || !filmFile)
        ? await loadDemoFix(gap.start, gap.end)
        : await requestFix(filmFile, gap.start, gap.end)
      setResult(fix)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Fix request failed')
    } finally {
      setLoading(false)
    }
  }

  function handleAccept() {
    setAccepted(true)
    onAccepted()
  }

  const duration = gap.end - gap.start

  return (
    <aside
      role="dialog"
      aria-label="Generative fix panel"
      aria-modal="true"
      style={{
        background: 'var(--ag-surface)',
        border: '1px solid var(--ag-border)',
        padding: 20,
        position: 'relative',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', color: 'var(--ag-text-muted)', letterSpacing: 1, marginBottom: 4 }}>
            Gated Generative Fix
          </div>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
            AD Gap Fix
          </h2>
        </div>
        <button onClick={onClose}
          aria-label="Close fix panel"
          style={{ background: 'none', border: 'none', color: 'var(--ag-text-muted)', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>
          ×
        </button>
      </div>

      {/* Gap info */}
      <div style={{ marginBottom: 16, padding: '10px 12px', background: 'var(--ag-surface2)', border: '1px solid var(--ag-border)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        <div style={{ color: 'var(--ag-text-muted)', marginBottom: 4, fontSize: 10, textTransform: 'uppercase' }}>Gap Region</div>
        <div>{fmtTime(gap.start)} → {fmtTime(gap.end)}</div>
        <div style={{ color: 'var(--ag-text-muted)', fontSize: 11 }}>{duration.toFixed(1)}s · max {Math.floor(duration / 60 * 150)} words at 150 wpm</div>
      </div>

      {/* Generate button */}
      {!result && !loading && (
        <button onClick={runFix}
          style={{ width: '100%', background: 'var(--ag-blue)', color: 'white', border: 'none', padding: '10px 0', fontSize: 13, fontWeight: 600, cursor: 'pointer', marginBottom: 12 }}>
          GENERATE AUDIO DESCRIPTION
        </button>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--ag-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          <div style={{ marginBottom: 8 }}>VISION MODEL DRAFTING...</div>
          <div style={{ width: '100%', height: 2, background: 'var(--ag-surface2)', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', left: '-40%', width: '40%', height: '100%', background: 'var(--ag-blue)', animation: 'none' }} />
          </div>
        </div>
      )}

      {error && (
        <p role="alert" style={{ color: 'var(--ag-red)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          Error: {error}
        </p>
      )}

      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Draft text */}
          <Stage label="1. Vision Draft" status="done">
            <p style={{ margin: 0, fontSize: 13, color: 'var(--ag-text)', fontStyle: 'italic', lineHeight: 1.5 }}>
              "{result.draft_text}"
            </p>
            <div style={{ marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: 11, color: result.fits_gap ? 'var(--ag-green)' : 'var(--ag-red)' }}>
              {result.word_count} words · {result.fits_gap ? '✓ fits gap' : '✗ too long for gap'}
            </div>
            {result.draft_source && (
              <div style={{ marginTop: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ag-text-muted)' }}>
                drafted by {result.draft_source}
              </div>
            )}
          </Stage>

          {/* DCMP validation */}
          <Stage label="2. DCMP Structure Check" status={result.dcmp_valid ? 'pass' : 'fail'}>
            {result.dcmp_valid ? (
              <div style={{ color: 'var(--ag-green)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>✓ All DCMP DESC rules pass</div>
            ) : (
              <ul style={{ margin: 0, padding: '0 0 0 16px', fontSize: 12, color: 'var(--ag-red)' }}>
                {result.dcmp_issues.map((issue, i) => <li key={i}>{issue}</li>)}
              </ul>
            )}
          </Stage>

          {/* Guardian screen */}
          <Stage label="3. Granite Guardian Screen" status={result.guardian_cleared ? 'pass' : 'fail'}>
            {result.guardian_cleared ? (
              <div style={{ color: 'var(--ag-green)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>✓ Content safety cleared</div>
            ) : (
              <div style={{ color: 'var(--ag-red)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>✗ {result.guardian_reason}</div>
            )}
          </Stage>

          {/* watsonx.ai Lite side-by-side (when WATSONX_API_KEY is set) */}
          {(result as FixResult & { watsonx_showcase?: { generated_text: string; word_count: number; error: string | null; source: string } }).watsonx_showcase && (() => {
            const wx = (result as FixResult & { watsonx_showcase?: { generated_text: string; word_count: number; error: string | null; source: string } }).watsonx_showcase!
            return (
              <Stage label="4. watsonx.ai Lite (ibm/granite-3-8b-instruct)" status="done">
                {wx.error ? (
                  <div style={{ color: 'var(--ag-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                    Not configured: {wx.error}
                  </div>
                ) : (
                  <>
                    <p style={{ margin: 0, fontSize: 13, color: 'var(--ag-text)', fontStyle: 'italic', lineHeight: 1.5 }}>
                      "{wx.generated_text}"
                    </p>
                    <div style={{ marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ag-text-muted)' }}>
                      {wx.word_count} words · {wx.source}
                    </div>
                  </>
                )}
              </Stage>
            )
          })()}

          {/* Accept/Reject */}
          {!accepted && (
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <button
                onClick={handleAccept}
                disabled={!result.accepted}
                aria-label="Accept this fix"
                style={{
                  flex: 1,
                  background: result.accepted ? 'var(--ag-green)' : 'var(--ag-surface2)',
                  color: result.accepted ? 'white' : 'var(--ag-text-muted)',
                  border: 'none', padding: '10px 0', fontSize: 13, fontWeight: 600,
                  cursor: result.accepted ? 'pointer' : 'not-allowed',
                }}>
                {result.accepted ? 'ACCEPT FIX' : 'CANNOT ACCEPT'}
              </button>
              <button onClick={onClose}
                style={{ flex: 1, background: 'var(--ag-surface2)', color: 'var(--ag-text-muted)', border: 'none', padding: '10px 0', fontSize: 13, cursor: 'pointer' }}>
                DISCARD
              </button>
            </div>
          )}

          {accepted && (
            <div style={{ padding: '12px', background: 'rgba(36,161,72,0.15)', border: '1px solid var(--ag-green)', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ag-green)' }}>
              ✓ FIX ACCEPTED — ROW FLIPPED GREEN
            </div>
          )}
        </div>
      )}
    </aside>
  )
}

function Stage({ label, status, children }: { label: string; status: 'done' | 'pass' | 'fail'; children: React.ReactNode }) {
  const colors = { done: 'var(--ag-blue-light)', pass: 'var(--ag-green)', fail: 'var(--ag-red)' }
  return (
    <div style={{ padding: '10px 12px', border: `1px solid ${colors[status]}44`, background: `${colors[status]}11` }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, color: colors[status], marginBottom: 6 }}>
        {label}
      </div>
      {children}
    </div>
  )
}

function fmtTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
