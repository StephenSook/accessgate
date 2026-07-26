/**
 * ReviewWorkbench — the event-sourced, natural-language-drivable conformance
 * review session, made clickable.
 *
 * A QC lead accepts / dismisses / flags each finding as reversible typed ops
 * against an append-only log (server-computed inverses -> deterministic undo,
 * replayable audit trail). The whole session is drivable in plain English
 * ("dismiss all reading-speed flags after 2:00 as acceptable for this title"),
 * compiled by watsonx Granite and re-grounded to the report's real findings.
 * Findings and the gated fix also export to editor-native files.
 */
import { useEffect, useState } from 'react'
import type { ReviewSessionView, ReviewStatus } from '../api/client'
import {
  createReviewSession, reviewNL, applyReviewOp, reviewUndo, exportUrl,
} from '../api/client'
import { fmtTime } from '../utils/format'

interface Props {
  reportId: string
}

const STATUS_COLOR: Record<ReviewStatus, string> = {
  open: 'var(--ag-text-muted)',
  accepted: 'var(--ag-green)',
  dismissed: 'var(--ag-blue-light)',
  flagged: 'var(--ag-amber)',
}

export function ReviewWorkbench({ reportId }: Props) {
  const [session, setSession] = useState<ReviewSessionView | null>(null)
  const [phrase, setPhrase] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAudit, setShowAudit] = useState(false)

  useEffect(() => {
    let cancelled = false
    createReviewSession(reportId)
      .then((s) => { if (!cancelled) setSession(s) })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'session failed') })
    return () => { cancelled = true }
  }, [reportId])

  // Run a review action, resilient to Render free-tier evicting the in-memory
  // session: on a 404 (session not found) we recreate the session and retry once.
  async function perform(fn: (sid: string) => Promise<ReviewSessionView>) {
    setBusy(true); setError(null)
    try {
      const s = session ?? await createReviewSession(reportId)
      try {
        setSession(await fn(s.session_id))
      } catch (e: unknown) {
        if (e instanceof Error && e.message.includes('404')) {
          const fresh = await createReviewSession(reportId)
          setSession(await fn(fresh.session_id))
        } else { throw e }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'request failed')
    } finally { setBusy(false) }
  }

  const nl = session?.nl

  return (
    <section aria-label="Conformance review workbench"
      style={{ background: 'var(--ag-surface)', border: '1px solid var(--ag-border)', padding: 20, marginTop: 24 }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--ag-text-muted)', marginBottom: 4 }}>
        Event-sourced · natural-language · auditable
      </div>
      <h2 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 600 }}>Conformance Review</h2>
      <p style={{ margin: '0 0 16px', fontSize: 12, color: 'var(--ag-text-muted)', lineHeight: 1.5 }}>
        Decide each finding as a reversible, typed operation. Every action is grounded to a real
        finding, carries a deterministic inverse (undo), and lands in an append-only audit trail.
      </p>

      {error && <p role="alert" style={{ color: 'var(--ag-red)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>Error: {error}</p>}
      {!session && !error && <div style={{ color: 'var(--ag-text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>Opening review session…</div>}

      {session && (
        <>
          {/* summary + undo + exports */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 14 }}>
            {(['open', 'accepted', 'dismissed', 'flagged'] as ReviewStatus[]).map((s) => (
              <span key={s} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, padding: '4px 8px', border: `1px solid ${STATUS_COLOR[s]}55`, color: STATUS_COLOR[s] }}>
                {s}: {session.summary[s] ?? 0}
              </span>
            ))}
            <span style={{ flex: 1 }} />
            <button onClick={() => perform((s) => reviewUndo(s))} disabled={busy || session.version === 0}
              style={{ background: 'var(--ag-surface2)', color: 'var(--ag-text)', border: '1px solid var(--ag-border)', padding: '5px 12px', fontSize: 12, cursor: 'pointer' }}>
              ↶ Undo
            </button>
            <a href={exportUrl(reportId, 'findings.csv')} download
              style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ag-blue-light)', padding: '5px 8px', border: '1px solid var(--ag-border)', textDecoration: 'none' }}>
              ↓ findings.csv
            </a>
            <a href={exportUrl(reportId, 'markers.vtt')} download
              style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ag-blue-light)', padding: '5px 8px', border: '1px solid var(--ag-border)', textDecoration: 'none' }}>
              ↓ markers.vtt
            </a>
          </div>

          {/* natural-language command bar */}
          <form onSubmit={(e) => { e.preventDefault(); if (phrase.trim()) perform((s) => reviewNL(s, phrase.trim())) }}
            style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <input value={phrase} onChange={(e) => setPhrase(e.target.value)}
              aria-label="Natural-language review command"
              placeholder="e.g. dismiss all reading-speed flags after 2:00 as acceptable for this title"
              style={{ flex: 1, background: 'var(--ag-bg)', color: 'var(--ag-text)', border: '1px solid var(--ag-border)', padding: '8px 10px', fontSize: 12, fontFamily: 'var(--font-mono)' }} />
            <button type="submit" disabled={busy || !phrase.trim()}
              style={{ background: 'var(--ag-blue)', color: 'white', border: 'none', padding: '0 16px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
              Run
            </button>
          </form>

          {nl && (
            <div style={{ marginBottom: 14, padding: '8px 10px', background: 'var(--ag-surface2)', border: '1px solid var(--ag-border)', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ag-text-muted)' }}>
              <span style={{ color: 'var(--ag-blue-light)' }}>compiled by {nl.engine}</span>
              {' · '}{nl.intent}{' · '}{nl.reasoning}
              {nl.intent === 'mutate' && <> {' · '}applied {nl.applied} op(s) to {nl.matched.length} grounded finding(s)</>}
            </div>
          )}

          {/* findings list */}
          <div style={{ maxHeight: 320, overflowY: 'auto', border: '1px solid var(--ag-border)' }}>
            {Object.values(session.findings).map((f) => (
              <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderBottom: '1px solid var(--ag-border)' }}>
                <span title={f.review_status} style={{ width: 8, height: 8, borderRadius: 999, background: STATUS_COLOR[f.review_status], flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ag-text)' }}>
                    {f.rule_id}
                    <span style={{ color: 'var(--ag-text-muted)' }}>
                      {' · '}{f.level}{f.timecode != null ? ` · ${fmtTime(f.timecode, false)}` : ''}
                      {' · '}<span style={{ color: STATUS_COLOR[f.review_status] }}>{f.review_status}</span>
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--ag-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.message}</div>
                </div>
                {(['accept', 'dismiss', 'flag'] as const).map((act) => (
                  <button key={act} disabled={busy}
                    onClick={() => perform((s) => applyReviewOp(s, `${act}_finding`, f.key))}
                    aria-label={`${act} ${f.rule_id}`}
                    title={act}
                    style={{ background: 'var(--ag-surface2)', color: 'var(--ag-text-muted)', border: '1px solid var(--ag-border)', padding: '3px 8px', fontSize: 11, cursor: 'pointer' }}>
                    {act === 'accept' ? '✓' : act === 'dismiss' ? '✕' : '⚑'}
                  </button>
                ))}
              </div>
            ))}
          </div>

          {/* audit trail */}
          <button onClick={() => setShowAudit((v) => !v)}
            style={{ background: 'none', border: 'none', color: 'var(--ag-blue-light)', fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer', padding: '10px 0 0' }}>
            {showAudit ? '▾' : '▸'} audit trail ({session.audit_log.length})
          </button>
          {showAudit && (
            <div style={{ maxHeight: 180, overflowY: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ag-text-muted)', marginTop: 6 }}>
              {session.audit_log.map((op, i) => (
                <div key={i} style={{ padding: '2px 0' }}>
                  {String(op.seq).padStart(2, '0')}{'  '}
                  <span style={{ color: op.source === 'undo' ? 'var(--ag-amber)' : op.source === 'nl' ? 'var(--ag-blue-light)' : 'var(--ag-text-muted)' }}>{op.source}</span>
                  {'  '}{op.kind}{'  '}{op.target}{op.undo_of ? '  (undo)' : ''}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}
