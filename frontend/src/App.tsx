import React, { useState, useRef, useEffect } from 'react'
import type { ConformanceReport, ReportSummary } from './api/client'
import { checkConformance, loadDemo, loadDemoSummary, summarizeReport } from './api/client'
import { ConformanceTimeline } from './components/ConformanceTimeline'
import { RuleResultsTable } from './components/RuleResultsTable'
import { GatedFixPanel } from './components/GatedFixPanel'
import { AxeScoreBadge } from './components/AxeScoreBadge'
import { JudgesPage } from './components/JudgesPage'
import { VideoPlayer } from './components/VideoPlayer'
import { WaveformDisplay } from './components/WaveformDisplay'
import './index.css'

export default function App() {
  const [report, setReport] = useState<ConformanceReport | null>(null)
  const [filmFile, setFilmFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedGap, setSelectedGap] = useState<{ start: number; end: number } | null>(null)
  const [activeTimecode, setActiveTimecode] = useState<number>(0)
  const [showJudges, setShowJudges] = useState(false)
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [statusMsg, setStatusMsg] = useState('')
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null)

  // Move focus to the results heading after a run so a screen-reader user
  // lands on the results. The aria-live region below reads out the summary.
  useEffect(() => {
    if (report) resultsHeadingRef.current?.focus()
  }, [report])

  function announceReport(r: ConformanceReport) {
    const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`
    const parts = [plural(r.error_count, 'error'), plural(r.warning_count, 'warning'), plural(r.flag_count, 'flag')]
    if (r.ner) parts.push(`NER score ${(r.ner.ner_score * 100).toFixed(1)} percent`)
    parts.push(plural(r.gaps.length, 'gap'))
    setStatusMsg(`Conformance check complete. ${parts.join(', ')}. Results follow below.`)
  }

  async function handleDemo() {
    setError(null)
    setLoading(true)
    setFilmFile(null)
    setSummary(null)
    setStatusMsg('Running conformance check, please wait.')
    try {
      const result = await loadDemo()
      setReport(result)
      announceReport(result)
      loadDemoSummary().then(setSummary).catch(() => {})
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setStatusMsg('')
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
    setSummary(null)
    setStatusMsg('Running conformance check, please wait.')
    try {
      const result = await checkConformance(film, captions, ad?.size ? ad : null, profile)
      setReport(result)
      announceReport(result)
      summarizeReport(result).then(setSummary).catch(() => {})
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setStatusMsg('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* Skip link: first focusable element, jumps past the header to main. */}
      <a href="#main-content" className="ag-skip-link">Skip to main content</a>

      {/* Corner bracket frame decoration (21hrs.space motif) */}
      <div className="ag-frame" aria-hidden="true">
        <div className="ag-frame-corner" />
        <div className="ag-frame-corner" />
        <div className="ag-frame-corner" />
        <div className="ag-frame-corner" />
      </div>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 24px 80px' }}>

        {/* Live region: announces run start and completion to assistive tech. */}
        <div role="status" aria-live="polite" className="ag-sr-only">{statusMsg}</div>

        {/* Header */}
        <header style={{ marginBottom: 32, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', color: 'var(--ag-text-muted)', letterSpacing: 2, marginBottom: 4 }}>
              IBM AI Builders Challenge 2026
            </div>
            <h1 className="ag-title" style={{ margin: 0, fontSize: 28, fontWeight: 700, color: 'var(--ag-text)', letterSpacing: -0.5 }}>
              AccessGate
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--ag-text-muted)' }}>
              Film accessibility conformance pre-check engine
            </p>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <span className="ag-status" aria-label="Engine online">
              <span className="ag-status__dot" aria-hidden="true" />
              Engine online
            </span>
            <AxeScoreBadge />
            <button
              type="button"
              onClick={() => setShowJudges(v => !v)}
              aria-pressed={showJudges}
              style={{
                background: showJudges ? 'rgba(241,194,27,0.15)' : 'none',
                color: showJudges ? 'var(--ag-amber)' : 'var(--ag-text-muted)',
                border: `1px solid ${showJudges ? 'rgba(241,194,27,0.5)' : 'var(--ag-border)'}`,
                padding: '6px 14px',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                letterSpacing: 1,
                textTransform: 'uppercase',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              JUDGES
            </button>
          </div>
        </header>

        <div className="ag-divider" style={{ marginBottom: 32 }} />

        <main id="main-content" tabIndex={-1}>

        {/* Judges transparency panel */}
        {showJudges && <JudgesPage />}

        {/* Upload form */}
        <section aria-label="Upload files for conformance check" style={{ marginBottom: 40 }}>
          <h2 className="ag-sr-only">Upload a film to check</h2>
          <form onSubmit={handleSubmit}>
            <div className="ag-upload-grid">
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
          <p className="ag-mode-note">
            <b>Hosted demo</b> runs the 23-rule conformance engine live on your uploaded caption file.
            {' '}ASR accuracy scoring (Granite Speech / faster-whisper), Silero VAD gap detection, and the
            {' '}Granite Vision generative fix run in the <b>full local pipeline</b> — see the demo report for all of it.
          </p>
        </section>

        {/* Empty-state hero — one-loop explainer before a report loads */}
        {!report && !loading && !showJudges && (
          <section className="ag-hero" aria-label="What AccessGate does">
            <div className="ag-hero__eyebrow">Reimagine Creative Industries with AI · one loop</div>
            <p className="ag-hero__loop">
              A film's caption file has a 44-character line, a sub-2-second cue, and a
              {' '}240-wpm burst. Its audio-description file has a past-tense line and one that
              {' '}overlaps dialogue. AccessGate scores all of it against <b>WCAG 2.2</b>,
              {' '}<b>FCC 47 CFR 79.1</b>, <b>DCMP</b>, and <b>Netflix</b> standards, cites the exact
              {' '}rule text behind every flag, and never auto-fails a caption on ASR evidence alone.
              {' '}Click a failing gap and Granite Vision drafts a fix, the DCMP validator re-checks it,
              {' '}Granite Guardian screens it, and the row flips green.
            </p>
            <div className="ag-hero__chips">
              <span className="ag-chip ag-chip--live">Load demo to see it</span>
              <span className="ag-chip">23 coded rules</span>
              <span className="ag-chip">SARIF + OSCAL export</span>
              <span className="ag-chip ag-chip--local">API-deletion-proof engine</span>
            </div>
          </section>
        )}

        {/* Results */}
        {report && (
          <div className="ag-reveal">
            <h2 ref={resultsHeadingRef} tabIndex={-1} className="ag-sr-only">Conformance results</h2>
            {/* Summary bar */}
            {(() => {
              const metricsData = [
                { label: 'ERRORS', value: report.error_count, color: 'var(--ag-red)' },
                { label: 'WARNINGS', value: report.warning_count, color: 'var(--ag-amber)' },
                { label: 'FLAGS', value: report.flag_count, color: 'var(--ag-blue-light)' },
                ...(report.ner ? [{
                  label: 'NER SCORE',
                  value: `${(report.ner.ner_score * 100).toFixed(1)}%`,
                  color: report.ner.passes_98_threshold ? 'var(--ag-green)' : 'var(--ag-amber)',
                  sub: `band ${(report.ner.band_low * 100).toFixed(1)}%–${(report.ner.band_high * 100).toFixed(1)}%`,
                }] : []),
                { label: 'GAPS', value: report.gaps.length, color: 'var(--ag-text-muted)' },
              ]
              return (
                <section aria-label="Conformance summary" style={{ display: 'flex', gap: 24, marginBottom: 32, padding: '16px 20px', background: 'var(--ag-surface)', border: '1px solid var(--ag-border)' }}>
                  {metricsData.map((m, i) => (
                    <div key={m.label} className="ag-metric-appear" style={{ animationDelay: `${i * 60}ms` }}>
                      <Metric label={m.label} value={m.value} color={m.color} sub={m.sub} />
                    </div>
                  ))}
                  <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ag-text-muted)', textTransform: 'uppercase' }}>
                      Profile: {report.profile.toUpperCase()}
                    </span>
                  </div>
                </section>
              )
            })()}

            {/* Granite plain-English summary */}
            {summary && summary.summary && (
              <section aria-label="Report summary" className="ag-summary-card">
                <div className="ag-summary-card__label">Executive summary · {summary.source}</div>
                <p className="ag-summary-card__text">{summary.summary}</p>
              </section>
            )}

            {/* Conformance Timeline — the killer visual */}
            <h3 className="ag-sr-only">Conformance timeline</h3>
            <ConformanceTimeline
              report={report}
              activeTimecode={activeTimecode}
              onTimecodeClick={setActiveTimecode}
              onGapClick={setSelectedGap}
            />

            {/* Video + Waveform row — an uploaded file, or the demo clip synced
                to the timeline (the real public-domain film scrubs under the gaps) */}
            {(() => {
              const isDemo = report.report_id === 'demo-notld-2026'
              const demoSrc = isDemo && !filmFile ? '/notld-demo.mp4' : undefined
              if (!filmFile && !demoSrc) return null
              return (
                <div style={{ marginTop: 24, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
                  <VideoPlayer
                    file={filmFile}
                    src={demoSrc}
                    activeTimecode={activeTimecode}
                    onTimeUpdate={setActiveTimecode}
                  />
                  <WaveformDisplay
                    file={filmFile}
                    src={demoSrc}
                    gaps={report.gaps}
                    activeTimecode={activeTimecode}
                    onTimecodeClick={setActiveTimecode}
                  />
                </div>
              )
            })()}

            <div style={{ marginTop: 32, display: 'grid', gridTemplateColumns: selectedGap ? '1fr 380px' : '1fr', gap: 24 }}>
              {/* Rule Results Table */}
              <h3 className="ag-sr-only">Rule results</h3>
              <RuleResultsTable
                results={report.results}
                onTimecodeClick={setActiveTimecode}
                onRequestFix={(gap) => setSelectedGap(gap)}
              />

              {/* Gated Fix Panel — works for uploads (local Granite Vision) and
                  for the demo (live watsonx vision from committed keyframes) */}
              {selectedGap && (
                <GatedFixPanel
                  // Re-key per gap so switching gaps remounts the panel and
                  // clears the previous draft/DCMP/Guardian result (otherwise a
                  // new gap's header showed the prior gap's stale result).
                  key={`${selectedGap.start}-${selectedGap.end}`}
                  gap={selectedGap}
                  filmFile={filmFile}
                  demoMode={!filmFile}
                  onClose={() => setSelectedGap(null)}
                  onAccepted={() => {
                    // Keep the panel open so the "row flipped green" confirmation
                    // stays visible; the user dismisses it with the close button.
                  }}
                />
              )}
            </div>
          </div>
        )}

        </main>
      </div>
    </>
  )
}

function FileField({ id, name, label, accept, required }: {
  id: string; name: string; label: string; accept?: string; required?: boolean
}) {
  const [fileName, setFileName] = useState<string | null>(null)
  const [over, setOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function assign(files: FileList | null) {
    const f = files?.[0]
    if (!f || !inputRef.current) return
    // Mirror the dropped file into the hidden input so the form's FormData sees it.
    const dt = new DataTransfer()
    dt.items.add(f)
    inputRef.current.files = dt.files
    setFileName(f.name)
  }

  return (
    <div>
      <label htmlFor={id} style={{ display: 'block', fontSize: 12, color: 'var(--ag-text-muted)', marginBottom: 6, fontFamily: 'var(--font-mono)', textTransform: 'uppercase' }}>
        {label}{required && ' *'}
      </label>
      <div
        className={`ag-dropzone${over ? ' ag-dropzone--over' : ''}${fileName ? ' ag-dropzone--filled' : ''}`}
        role="button"
        tabIndex={0}
        aria-label={`${label}${required ? ' (required)' : ''} — drop a file or click to browse`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click() } }}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); assign(e.dataTransfer.files) }}
      >
        <span className="ag-dropzone__hint">{fileName ? '✓ Selected' : 'Drop or click'}</span>
        <span className="ag-dropzone__name">{fileName ?? (accept ?? 'any file')}</span>
      </div>
      <input
        ref={inputRef}
        id={id}
        name={name}
        type="file"
        accept={accept}
        required={required}
        onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
        style={{ position: 'absolute', width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
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
