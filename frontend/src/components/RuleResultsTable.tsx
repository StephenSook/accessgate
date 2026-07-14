/**
 * RuleResultsTable — Carbon-style sortable table of conformance results.
 * Expandable rows show verbatim RAG-retrieved citations.
 * Color-coded status: error=red, warning=amber, flag=blue, pass=green.
 */
import React, { useState, useMemo } from 'react'
import type { RuleResult } from '../api/client'
import { fmtTime } from '../utils/format'

interface Props {
  results: RuleResult[]
  onTimecodeClick: (t: number) => void
  onRequestFix: (gap: { start: number; end: number }) => void
}

const STATUS_COLORS: Record<string, string> = {
  fail: '#da1e28',
  flag: '#f1c21b',
  pass: '#24a148',
  skip: '#525252',
}
const SARIF_BADGE: Record<string, string> = {
  error: '#da1e28',
  warning: '#f1c21b',
  note: '#4589ff',
}

type SortKey = 'rule_id' | 'status' | 'sarif_level'

export function RuleResultsTable({ results, onTimecodeClick, onRequestFix }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [sortKey, setSortKey] = useState<SortKey>('status')
  const [showPassSkip, setShowPassSkip] = useState(false)
  const [filter, setFilter] = useState('')

  const visible = useMemo(() => {
    let rows = results
    if (!showPassSkip) rows = rows.filter(r => r.status === 'fail' || r.status === 'flag')
    if (filter) rows = rows.filter(r =>
      r.rule_id.toLowerCase().includes(filter.toLowerCase()) ||
      r.message.toLowerCase().includes(filter.toLowerCase())
    )
    // Sort: fail first, then flag, then others
    const ORDER: Record<string, number> = { fail: 0, flag: 1, pass: 2, skip: 3 }
    return [...rows].sort((a, b) => {
      if (sortKey === 'status') return (ORDER[a.status] ?? 4) - (ORDER[b.status] ?? 4)
      return a[sortKey].localeCompare(b[sortKey])
    })
  }, [results, sortKey, showPassSkip, filter])

  function toggle(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const isAdRule = (rule_id: string) => rule_id.startsWith('DCMP-DESC')

  return (
    <section aria-label="Rule results">
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
        <input
          type="search"
          placeholder="Filter rules…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          aria-label="Filter rule results"
          style={{ background: 'var(--ag-surface)', color: 'var(--ag-text)', border: '1px solid var(--ag-border)', padding: '6px 10px', fontSize: 12, width: 200 }}
        />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ag-text-muted)', cursor: 'pointer' }}>
          <input type="checkbox" checked={showPassSkip} onChange={e => setShowPassSkip(e.target.checked)} />
          Show all
        </label>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ag-text-muted)', marginLeft: 'auto' }}>
          {visible.length} / {results.length} rules
        </span>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }} aria-label="Conformance rule results">
          <thead>
            <tr style={{ background: 'var(--ag-surface)', borderBottom: '2px solid var(--ag-border)' }}>
              {(['rule_id', 'status', 'sarif_level'] as SortKey[]).map(col => (
                <th key={col}
                  onClick={() => setSortKey(col)}
                  style={{ padding: '8px 12px', textAlign: 'left', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, color: sortKey === col ? 'var(--ag-text)' : 'var(--ag-text-muted)', userSelect: 'none', whiteSpace: 'nowrap' }}>
                  {col.replace('_', ' ')} {sortKey === col ? '↓' : ''}
                </th>
              ))}
              <th style={{ padding: '8px 12px', textAlign: 'left', fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--ag-text-muted)' }}>Message</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--ag-text-muted)' }}>Timecode</th>
              <th style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--ag-text-muted)' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r, idx) => {
              const rowKey = `${r.rule_id}-${idx}`
              const isExp = expanded.has(rowKey)
              return (
                <React.Fragment key={rowKey}>
                  <tr
                    style={{
                      borderBottom: '1px solid var(--ag-border)',
                      background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)',
                      transition: 'background 0.15s',
                    }}
                  >
                    {/* Rule ID */}
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, whiteSpace: 'nowrap' }}>
                      <button onClick={() => toggle(rowKey)}
                        aria-expanded={isExp}
                        aria-label={`Toggle citation for ${r.rule_id}`}
                        style={{ background: 'none', border: 'none', color: 'var(--ag-text)', cursor: 'pointer', padding: 0, fontFamily: 'inherit', fontSize: 'inherit', textAlign: 'left' }}>
                        {isExp ? '▾' : '▸'} {r.rule_id}
                      </button>
                    </td>
                    {/* Status */}
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{
                        display: 'inline-block', padding: '2px 8px', fontSize: 11, fontWeight: 600,
                        fontFamily: 'var(--font-mono)', textTransform: 'uppercase',
                        background: STATUS_COLORS[r.status] + '22',
                        color: STATUS_COLORS[r.status] || 'var(--ag-text-muted)',
                        border: `1px solid ${STATUS_COLORS[r.status] || 'var(--ag-border)'}44`,
                      }}>
                        {r.status}
                      </span>
                    </td>
                    {/* SARIF Level */}
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: SARIF_BADGE[r.sarif_level] || 'var(--ag-text-muted)' }}>
                        {r.sarif_level}
                      </span>
                    </td>
                    {/* Message */}
                    <td style={{ padding: '10px 12px', color: 'var(--ag-text-muted)', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.message}
                    </td>
                    {/* Timecode */}
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                      {r.timecode != null ? (
                        <button onClick={() => onTimecodeClick(r.timecode!)}
                          className="ag-timecode"
                          aria-label={`Seek to ${r.timecode.toFixed(2)}s`}
                          style={{ background: 'none', border: 'none', color: 'var(--ag-blue-light)', cursor: 'pointer', padding: 0, fontSize: 11 }}>
                          {fmtTime(r.timecode)}
                        </button>
                      ) : '—'}
                    </td>
                    {/* Action */}
                    <td style={{ padding: '10px 12px' }}>
                      {r.status === 'fail' && isAdRule(r.rule_id) && r.timecode != null && (
                        <button
                          onClick={() => onRequestFix({ start: r.timecode! - 0.5, end: r.timecode! + 7 })}
                          aria-label={`Request generative fix for ${r.rule_id}`}
                          style={{ background: 'var(--ag-blue)', color: 'white', border: 'none', padding: '3px 10px', fontSize: 11, cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
                          FIX
                        </button>
                      )}
                    </td>
                  </tr>

                  {/* Expanded citation row */}
                  {isExp && (
                    <tr style={{ background: 'var(--ag-surface)', borderBottom: '1px solid var(--ag-border)' }}>
                      <td colSpan={7} style={{ padding: '12px 16px 14px 36px' }}>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ag-text-muted)', textTransform: 'uppercase', marginBottom: 4, letterSpacing: 1 }}>
                          Source Citation
                        </div>
                        <blockquote style={{ margin: 0, padding: '8px 12px', borderLeft: '2px solid var(--ag-blue)', background: 'rgba(15,98,254,0.06)', fontSize: 12, color: 'var(--ag-text)', fontStyle: 'italic' }}>
                          {r.citation || '—'}
                        </blockquote>
                        {r.human_review_required && (
                          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--ag-amber)', fontFamily: 'var(--font-mono)' }}>
                            ⚠ Human review required
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
        {visible.length === 0 && (
          <p style={{ textAlign: 'center', color: 'var(--ag-text-muted)', padding: '24px 0', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            No results to display.
          </p>
        )}
      </div>
    </section>
  )
}

