import React, { useState } from 'react'
import type { ConformanceReport } from './api/client'
import { checkConformance, loadDemo } from './api/client'
import { ConformanceTimeline } from './components/ConformanceTimeline'
import { RuleResultsTable } from './components/RuleResultsTable'
import { GatedFixPanel } from './components/GatedFixPanel'
import { AxeScoreBadge } from './components/AxeScoreBadge'
import { LiveMonitor } from './components/LiveMonitor'
import './index.css'

export default function App() {
  const [report, setReport] = useState<ConformanceReport | null>(null)
  const [filmFile, setFilmFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedGap, setSelectedGap] = useState<{ start: number; end: number } | null>(null)
  const [activeTimecode, setActiveTimecode] = useState<number>(0)

  async function handleDemo() {
    setError(null)
    setLoading(true)
    setFilmFile(null)
    try {
      const result = await loadDemo()
      setReport(result)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const film = fd.get('film') as File | null
    const captions = fd.get('captions') as File | null
    const ad = fd.get('ad') as File | null
    const profile = (fd.get('profile') as string) || 'netflix'

    if (!film || !captions || !film.size || !captions.size) {
      setError('Film and caption files are required.')
      return
    }
    setError(null)
    setLoading(true)
    setFilmFile(film)
    try {
      const result = await checkConformance(film, captions, ad?.size ? ad : null, profile)
      setReport(result)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* Corner bracket frame decoration (21hrs.space motif) */}
      <div className="ag-frame" aria-hidden="true">
        <div className="ag-frame-corner" />
        <div className="ag-frame-corner" />
        <div className="ag-frame-corner" />
        <div className="ag-frame-corner" />
      </div>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 24px 80px' }}>

        {/* Header */}
        <header style={{ marginBottom: 32, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', color: 'var(--ag-text-muted)', letterSpacing: 2, marginBottom: 4 }}>
              IBM AI Builders Challenge 2026
            </div>
            <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: 'var(--ag-text)', letterSpacing: -0.5 }}>
              AccessGate
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--ag-text-muted)' }}>
              Film accessibility conformance pre-check engine
            </p>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <AxeScoreBadge />
            <LiveMonitor />
          </div>
        </header>

        <div className="ag-divider" style={{ marginBottom: 32 }} />

        {/* Upload form */}
        <section aria-label="Upload files for conformance check" style={{ marginBottom: 40 }}>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto auto', gap: 16, alignItems: 'end' }}>
              <FileField id="film" name="film" label="Film / Video" accept="video/*,audio/*" required />
              <FileField id="captions" name="captions" label="Captions (.srt / .vtt)" accept=".srt,.vtt" required />
              <FileField id="ad" name="ad" label="Audio Description (.vtt)" accept=".vtt" />
              <div>
                <label htmlFor="profile" style={{ display: 'block', fontSize: 12, color: 'var(--ag-text-muted)', marginBottom: 6, fontFamily: 'var(--font-mono)' }}>
                  PROFILE
                </label>
                <select id="profile" name="profile" defaultValue="netflix"
                  style={{ background: 'var(--ag-surface)', color: 'var(--ag-text)', border: '1px solid var(--ag-border)', padding: '8px 12px', fontSize: 13, width: '100%', cursor: 'pointer' }}>
                  <option value="netflix">Netflix</option>
                  <option value="dcmp">DCMP</option>
                  <option value="fcc">FCC</option>
                </select>
              </div>
              <button type="submit" disabled={loading}
                style={{ background: loading ? 'var(--ag-surface2)' : 'var(--ag-blue)', color: 'var(--ag-text)', border: 'none', padding: '10px 24px', fontSize: 13, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer', height: 38, whiteSpace: 'nowrap', letterSpacing: 0.5 }}>
                {loading ? 'CHECKING...' : 'RUN CHECK'}
              </button>
              <button type="button" disabled={loading} onClick={handleDemo}
                style={{ background: 'none', color: 'var(--ag-text-muted)', border: '1px solid var(--ag-border)', padding: '10px 18px', fontSize: 12, fontFamily: 'var(--font-mono)', cursor: loading ? 'not-allowed' : 'pointer', height: 38, whiteSpace: 'nowrap', letterSpacing: 0.5, textTransform: 'uppercase' }}>
                LOAD DEMO
              </button>
            </div>
            {loading && <div className="ag-loading-bar" role="progressbar" aria-label="Running conformance check" />}
          </form>
          {error && (
            <p role="alert" style={{ color: 'var(--ag-red)', marginTop: 12, fontSize: 13 }}>{error}</p>
          )}
        </section>

        {/* Results */}
        {report && (
          <>
            {/* Summary bar */}
            <section aria-label="Conformance summary" style={{ display: 'flex', gap: 24, marginBottom: 32, padding: '16px 20px', background: 'var(--ag-surface)', border: '1px solid var(--ag-border)' }}>
              <Metric label="ERRORS" value={report.error_count} color="var(--ag-red)" />
              <Metric label="WARNINGS" value={report.warning_count} color="var(--ag-amber)" />
              <Metric label="FLAGS" value={report.flag_count} color="var(--ag-blue-light)" />
              {report.ner && (
                <Metric
                  label="NER SCORE"
                  value={`${(report.ner.ner_score * 100).toFixed(1)}%`}
                  color={report.ner.passes_98_threshold ? 'var(--ag-green)' : 'var(--ag-amber)'}
                  sub={`band ${(report.ner.band_low * 100).toFixed(1)}%–${(report.ner.band_high * 100).toFixed(1)}%`}
                />
              )}
              <Metric label="GAPS" value={report.gaps.length} color="var(--ag-text-muted)" />
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ag-text-muted)', textTransform: 'uppercase' }}>
                  Profile: {report.profile.toUpperCase()}
                </span>
              </div>
            </section>

            {/* Conformance Timeline — the killer visual */}
            <ConformanceTimeline
              report={report}
              activeTimecode={activeTimecode}
              onTimecodeClick={setActiveTimecode}
              onGapClick={setSelectedGap}
            />

            <div style={{ marginTop: 32, display: 'grid', gridTemplateColumns: selectedGap ? '1fr 380px' : '1fr', gap: 24 }}>
              {/* Rule Results Table */}
              <RuleResultsTable
                results={report.results}
                onTimecodeClick={setActiveTimecode}
                onRequestFix={(gap) => setSelectedGap(gap)}
              />

              {/* Gated Fix Panel */}
              {selectedGap && filmFile && (
                <GatedFixPanel
                  gap={selectedGap}
                  filmFile={filmFile}
                  onClose={() => setSelectedGap(null)}
                  onAccepted={() => {
                    setSelectedGap(null)
                    // Would ideally refresh just that row
                  }}
                />
              )}
            </div>
          </>
        )}
      </div>
    </>
  )
}

function FileField({ id, name, label, accept, required }: {
  id: string; name: string; label: string; accept?: string; required?: boolean
}) {
  return (
    <div>
      <label htmlFor={id} style={{ display: 'block', fontSize: 12, color: 'var(--ag-text-muted)', marginBottom: 6, fontFamily: 'var(--font-mono)', textTransform: 'uppercase' }}>
        {label}{required && ' *'}
      </label>
      <input id={id} name={name} type="file" accept={accept} required={required}
        style={{ background: 'var(--ag-surface)', color: 'var(--ag-text)', border: '1px solid var(--ag-border)', padding: '6px 10px', fontSize: 12, width: '100%', cursor: 'pointer' }}
      />
    </div>
  )
}

function Metric({ label, value, color, sub }: { label: string; value: string | number; color: string; sub?: string }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', color: 'var(--ag-text-muted)', letterSpacing: 1, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ag-text-muted)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}
