/**
 * JudgesPage — Transparency tier breakdown for IBM AI Builders Challenge judges.
 * Fetches from GET /judges and renders the honesty moat: wired-live vs integration vs accelerator.
 */
import React, { useEffect, useState } from 'react'

const BASE = import.meta.env.VITE_API_URL ?? ''

interface TierItem {
  name: string
  evidence: string
  note?: string
  test_count?: number
  f1?: number
}

interface JudgesData {
  claim: string
  not_a: string[]
  tiers: {
    wired_live: TierItem[]
    integration: TierItem[]
    accelerator: TierItem[]
  }
  api_deletion_test: string
  github: string
  // These four are returned by /judges and were previously parsed and dropped,
  // so the strongest honesty material this project has, including the
  // disclosure about the recorded video's fix beat, existed only in the raw
  // API response and never reached the page titled "HONESTY MOAT".
  scope_boundaries?: { not_checked: string; why: string }[]
  generative_provenance?: string
  citation_provenance?: { active?: string | null; index_built_with?: string | null; note?: string }
  demo_transparency?: string
  // The build trace is the one piece of Bob evidence a judge can re-derive from
  // a clone instead of trusting a document we wrote about ourselves, so it gets
  // rendered rather than left in the raw JSON like the four fields above were.
  bob_usage?: {
    role?: string
    build_trace?: {
      note?: string
      window_et?: string
      commits_that_day?: number
      commits?: { time_et: string; commit: string; tests: number | null; subject: string }[]
    }
    artifacts_in_repo?: { what: string; where: string }[]
    not_in_repo?: string
  }
}

const TIER_CONFIG = {
  wired_live: {
    label: 'Wired Live',
    subtitle: 'Runs locally, zero hosted API calls',
    accent: '#24a148',      // --ag-green
    dimAccent: 'rgba(36,161,72,0.12)',
    border: 'rgba(36,161,72,0.35)',
  },
  integration: {
    label: 'Integration',
    subtitle: 'Calls a hosted or local model, degrades gracefully',
    accent: '#4589ff',      // --ag-blue-light
    dimAccent: 'rgba(69,137,255,0.10)',
    border: 'rgba(69,137,255,0.30)',
  },
  accelerator: {
    label: 'Accelerator',
    subtitle: 'IBM Bob tooling, not runtime product code',
    accent: '#f1c21b',      // --ag-amber
    dimAccent: 'rgba(241,194,27,0.10)',
    border: 'rgba(241,194,27,0.30)',
  },
} as const

type TierKey = keyof typeof TIER_CONFIG

export function JudgesPage() {
  const [data, setData] = useState<JudgesData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${BASE}/judges`)
      .then(r => {
        if (!r.ok) throw new Error(`/judges failed: ${r.status}`)
        return r.json() as Promise<JudgesData>
      })
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div style={styles.root}>
        <div className="ag-loading-bar" role="progressbar" aria-label="Loading judges data" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={styles.root}>
        <p style={{ color: 'var(--ag-red)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          {error ?? 'No data'}
        </p>
      </div>
    )
  }

  return (
    <div style={styles.root} role="region" aria-label="Judges transparency page">
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.headerLabel}>TRANSPARENCY · HONESTY MOAT</span>
        <a
          href={data.github}
          target="_blank"
          rel="noopener noreferrer"
          style={styles.githubLink}
        >
          ↗ github
        </a>
      </div>

      {/* Claim + NOT A */}
      <div style={styles.claimRow}>
        <div style={styles.claimBlock}>
          <span style={styles.claimTag}>CLAIM</span>
          <span style={styles.claimText}>{data.claim}</span>
        </div>
        <div style={styles.notABlock}>
          <span style={styles.claimTag}>NOT A</span>
          <span style={styles.notAList}>{data.not_a.join(' · ')}</span>
        </div>
      </div>

      <div className="ag-divider" style={{ margin: '16px 0' }} />

      {/* Three tier columns */}
      <div style={styles.tiersGrid}>
        {(Object.entries(TIER_CONFIG) as [TierKey, typeof TIER_CONFIG[TierKey]][]).map(([key, cfg]) => (
          <TierColumn
            key={key}
            config={cfg}
            items={data.tiers[key]}
          />
        ))}
      </div>

      <div className="ag-divider" style={{ margin: '16px 0' }} />

      {/* API deletion test */}
      <blockquote style={styles.blockquote}>
        <span style={styles.blockquoteIcon}>⚙</span>
        {data.api_deletion_test}
      </blockquote>

      {data.demo_transparency && (
        <blockquote style={{ ...styles.blockquote, marginTop: 12 }}>
          <span style={styles.blockquoteIcon}>◉</span>
          <span><b>What is and is not live in the demo. </b>{data.demo_transparency}</span>
        </blockquote>
      )}

      {data.generative_provenance && (
        <blockquote style={{ ...styles.blockquote, marginTop: 12 }}>
          <span style={styles.blockquoteIcon}>✎</span>
          <span><b>Provenance on every generated line. </b>{data.generative_provenance}</span>
        </blockquote>
      )}

      {data.citation_provenance?.active && (
        <blockquote style={{ ...styles.blockquote, marginTop: 12 }}>
          <span style={styles.blockquoteIcon}>❝</span>
          <span>
            <b>Citation encoder on this instance. </b>
            Active: <code>{data.citation_provenance.active}</code>
            {data.citation_provenance.index_built_with && (
              <> · index built with <code>{data.citation_provenance.index_built_with}</code></>
            )}
            {data.citation_provenance.note && <> · {data.citation_provenance.note}</>}
          </span>
        </blockquote>
      )}

      {data.scope_boundaries && data.scope_boundaries.length > 0 && (
        <div style={{ marginTop: 12 }}>
          {data.scope_boundaries.map((b, i) => (
            <blockquote key={i} style={{ ...styles.blockquote, marginTop: i ? 8 : 0 }}>
              <span style={styles.blockquoteIcon}>∅</span>
              <span><b>Not checked: {b.not_checked}. </b>{b.why}</span>
            </blockquote>
          ))}
        </div>
      )}

      {data.bob_usage && (
        <div style={{ marginTop: 20 }}>
          <div className="ag-divider" style={{ margin: '16px 0' }} />
          <h3 style={{ fontSize: 14, letterSpacing: '0.08em', textTransform: 'uppercase', opacity: 0.8 }}>
            How IBM Bob was used
          </h3>

          {data.bob_usage.role && (
            <blockquote style={{ ...styles.blockquote, marginTop: 12 }}>
              <span style={styles.blockquoteIcon}>◆</span>
              <span>{data.bob_usage.role}</span>
            </blockquote>
          )}

          {data.bob_usage.build_trace?.commits && data.bob_usage.build_trace.commits.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 13, opacity: 0.85, marginBottom: 8 }}>
                <b>Engine build trace, {data.bob_usage.build_trace.window_et} ET.</b>{' '}
                {data.bob_usage.build_trace.note}
              </div>
              {/* Wide on purpose: let the table scroll rather than the page. */}
              <div style={{ overflowX: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%', minWidth: 460 }}>
                  <thead>
                    <tr style={{ textAlign: 'left', opacity: 0.7 }}>
                      <th style={{ padding: '4px 10px 4px 0' }}>Time</th>
                      <th style={{ padding: '4px 10px 4px 0' }}>Commit</th>
                      <th style={{ padding: '4px 10px 4px 0' }}>What landed</th>
                      <th style={{ padding: '4px 0' }}>Tests</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.bob_usage.build_trace.commits.map((c) => (
                      <tr key={c.commit} style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                        <td style={{ padding: '4px 10px 4px 0', whiteSpace: 'nowrap' }}>{c.time_et}</td>
                        <td style={{ padding: '4px 10px 4px 0' }}><code>{c.commit}</code></td>
                        <td style={{ padding: '4px 10px 4px 0' }}>{c.subject}</td>
                        <td style={{ padding: '4px 0', whiteSpace: 'nowrap' }}>{c.tests ?? '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {data.bob_usage.artifacts_in_repo && data.bob_usage.artifacts_in_repo.length > 0 && (
            <ul style={{ marginTop: 12, fontSize: 12, opacity: 0.85, paddingLeft: 18 }}>
              {data.bob_usage.artifacts_in_repo.map((a) => (
                <li key={a.where} style={{ marginBottom: 4 }}>
                  {a.what} · <code>{a.where}</code>
                </li>
              ))}
            </ul>
          )}

          {data.bob_usage.not_in_repo && (
            <blockquote style={{ ...styles.blockquote, marginTop: 12 }}>
              <span style={styles.blockquoteIcon}>∅</span>
              <span><b>Not in the repo. </b>{data.bob_usage.not_in_repo}</span>
            </blockquote>
          )}
        </div>
      )}
    </div>
  )
}

function TierColumn({ config, items }: {
  config: typeof TIER_CONFIG[TierKey]
  items: TierItem[]
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {/* Column header */}
      <div style={{ ...styles.tierHeader, borderColor: config.border, background: config.dimAccent }}>
        <span style={{ ...styles.tierLabel, color: config.accent }}>{config.label}</span>
        <span style={styles.tierSubtitle}>{config.subtitle}</span>
      </div>
      {/* Cards */}
      {items.map((item, i) => (
        <div key={i} style={{ ...styles.card, borderColor: config.border, background: config.dimAccent }}>
          <div style={{ ...styles.cardName, color: config.accent }}>{item.name}</div>
          <div style={styles.cardEvidence}>{item.evidence}</div>
          {item.note && <div style={styles.cardNote}>{item.note}</div>}
          <div style={styles.cardMeta}>
            {item.test_count != null && (
              <span style={styles.metaTag}>{item.test_count} tests</span>
            )}
            {item.f1 != null && (
              <span style={styles.metaTag}>F1 {item.f1}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    padding: '20px 0 24px',
    fontFamily: 'var(--font-mono)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  headerLabel: {
    fontSize: 10,
    letterSpacing: 2,
    textTransform: 'uppercase' as const,
    color: 'var(--ag-text-muted)',
  },
  githubLink: {
    fontSize: 11,
    color: 'var(--ag-blue-light)',
    textDecoration: 'none',
    letterSpacing: 1,
  },
  claimRow: {
    display: 'flex',
    gap: 24,
    flexWrap: 'wrap' as const,
  },
  claimBlock: {
    display: 'flex',
    gap: 10,
    alignItems: 'baseline',
    flex: '1 1 auto',
  },
  notABlock: {
    display: 'flex',
    gap: 10,
    alignItems: 'baseline',
    flex: '0 1 auto',
  },
  claimTag: {
    fontSize: 9,
    letterSpacing: 1.5,
    textTransform: 'uppercase' as const,
    color: 'var(--ag-text-muted)',
    border: '1px solid var(--ag-border)',
    padding: '1px 5px',
    flexShrink: 0,
  },
  claimText: {
    fontSize: 12,
    color: 'var(--ag-text)',
  },
  notAList: {
    fontSize: 11,
    color: 'var(--ag-text-muted)',
  },
  tiersGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 14,
  },
  tierHeader: {
    border: '1px solid',
    padding: '8px 10px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 2,
    marginBottom: 2,
  },
  tierLabel: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 1,
    textTransform: 'uppercase' as const,
  },
  tierSubtitle: {
    fontSize: 10,
    color: 'var(--ag-text-muted)',
  },
  card: {
    border: '1px solid',
    padding: '7px 10px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 3,
  },
  cardName: {
    fontSize: 11,
    fontWeight: 600,
    lineHeight: 1.3,
  },
  cardEvidence: {
    fontSize: 10,
    color: 'var(--ag-text-muted)',
    wordBreak: 'break-all' as const,
  },
  cardNote: {
    fontSize: 10,
    color: 'var(--ag-text-muted)',
    fontStyle: 'italic',
    lineHeight: 1.4,
  },
  cardMeta: {
    display: 'flex',
    gap: 6,
    flexWrap: 'wrap' as const,
    marginTop: 2,
  },
  metaTag: {
    fontSize: 9,
    letterSpacing: 0.5,
    color: 'var(--ag-text-muted)',
    border: '1px solid var(--ag-border)',
    padding: '1px 4px',
  },
  blockquote: {
    margin: 0,
    padding: '12px 16px',
    borderLeft: '3px solid var(--ag-border)',
    background: 'var(--ag-surface)',
    fontSize: 11,
    color: 'var(--ag-text-muted)',
    lineHeight: 1.6,
    display: 'flex',
    gap: 10,
    alignItems: 'flex-start',
  },
  blockquoteIcon: {
    fontSize: 14,
    color: 'var(--ag-text-muted)',
    flexShrink: 0,
    marginTop: 1,
  },
}
