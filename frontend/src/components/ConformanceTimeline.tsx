/**
 * ConformanceTimeline — THE killer visual.
 *
 * Synchronized timeline showing:
 *   - Speech region bands (IBM Blue)
 *   - Dialogue-free gap bands (Carbon Gray 60)
 *   - Caption cue markers (small ticks, colored by SARIF level)
 *   - Conformance flag markers (error=red, warning=amber, note=blue)
 *
 * Clicking any marker seeks the timecode.
 * Design: 21hrs.space-inspired — fixed-size, mono labels, blur effects,
 * progress-bar-as-timeline motif.
 */
import React, { useRef, useCallback, useMemo } from 'react'
import type { ConformanceReport } from '../api/client'
import { fmtTime } from '../utils/format'

interface Props {
  report: ConformanceReport
  activeTimecode: number
  onTimecodeClick: (t: number) => void
  onGapClick: (gap: { start: number; end: number }) => void
}

const LEVEL_COLOR: Record<string, string> = {
  error: '#da1e28',
  warning: '#f1c21b',
  note: '#4589ff',
}

export function ConformanceTimeline({ report, activeTimecode, onTimecodeClick, onGapClick }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  // Total duration from last result timecode or last gap
  const totalDuration = useMemo(() => {
    const maxResult = Math.max(
      0,
      ...report.results.filter(r => r.timecode != null).map(r => r.timecode!)
    )
    const maxGap = report.gaps.length
      ? Math.max(...report.gaps.map(g => g.end))
      : 0
    const maxSpeech = report.speech_regions.length
      ? Math.max(...report.speech_regions.map(s => s.end))
      : 0
    return Math.max(maxResult, maxGap, maxSpeech, 30)
  }, [report])

  const pct = useCallback((t: number) => `${((t / totalDuration) * 100).toFixed(2)}%`, [totalDuration])

  const handleClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!ref.current) return
    const rect = ref.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const t = (x / rect.width) * totalDuration
    onTimecodeClick(Math.max(0, t))
  }, [totalDuration, onTimecodeClick])

  // Active position indicator
  const activePct = ((activeTimecode / totalDuration) * 100).toFixed(2)

  const failingResults = report.results.filter(r =>
    r.status === 'fail' && r.timecode != null
  )
  const flagResults = report.results.filter(r =>
    r.status === 'flag' && r.timecode != null
  )

  return (
    <section aria-label="Conformance timeline" style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', color: 'var(--ag-text-muted)', letterSpacing: 1 }}>
          Conformance Timeline
        </span>
        <span className="ag-timecode">{fmtTime(activeTimecode)}</span>
      </div>

      {/* Timeline canvas */}
      <div
        ref={ref}
        onClick={handleClick}
        role="slider"
        aria-label="Timeline scrubber"
        aria-valuenow={activeTimecode}
        aria-valuemin={0}
        aria-valuemax={totalDuration}
        tabIndex={0}
        style={{
          position: 'relative',
          height: 80,
          background: 'var(--ag-surface)',
          border: '1px solid var(--ag-border)',
          cursor: 'crosshair',
          userSelect: 'none',
          overflow: 'hidden',
        }}
      >
        {/* Speech region bands */}
        {report.speech_regions.map((s, i) => (
          <div key={`speech-${i}`}
            title={`Speech ${fmtTime(s.start)}–${fmtTime(s.end)}`}
            style={{
              position: 'absolute',
              left: pct(s.start),
              width: pct(s.end - s.start),
              top: 4, height: 28,
              background: 'rgba(15,98,254,0.18)',
              borderTop: '1px solid rgba(15,98,254,0.5)',
            }}
          />
        ))}

        {/* Gap bands */}
        {report.gaps.map((g, i) => (
          <div key={`gap-${i}`}
            onClick={(e) => { e.stopPropagation(); onGapClick(g) }}
            title={`Gap ${fmtTime(g.start)}–${fmtTime(g.end)} (${(g.duration ?? g.end - g.start).toFixed(1)}s) — click to fix AD`}
            style={{
              position: 'absolute',
              left: pct(g.start),
              width: pct(g.end - g.start),
              top: 4, height: 28,
              background: 'rgba(82,82,82,0.25)',
              border: '1px dashed rgba(82,82,82,0.6)',
              cursor: 'pointer',
            }}
          />
        ))}

        {/* Fail markers (red ticks) */}
        {failingResults.map((r, i) => (
          <div key={`fail-${i}`}
            onClick={(e) => { e.stopPropagation(); onTimecodeClick(r.timecode!) }}
            title={`${r.rule_id}: ${r.message.slice(0, 80)}`}
            role="button"
            aria-label={`Rule failure: ${r.rule_id} at ${fmtTime(r.timecode!)}`}
            tabIndex={0}
            style={{
              position: 'absolute',
              left: pct(r.timecode!),
              top: 36, height: 32,
              width: 2,
              background: LEVEL_COLOR[r.sarif_level] || '#da1e28',
              cursor: 'pointer',
            }}
          />
        ))}

        {/* Flag markers (amber diamonds) */}
        {flagResults.map((r, i) => (
          <div key={`flag-${i}`}
            onClick={(e) => { e.stopPropagation(); onTimecodeClick(r.timecode!) }}
            title={`${r.rule_id}: ${r.message.slice(0, 80)}`}
            role="button"
            aria-label={`Rule flag: ${r.rule_id} at ${fmtTime(r.timecode!)}`}
            tabIndex={0}
            style={{
              position: 'absolute',
              left: `calc(${pct(r.timecode!)} - 4px)`,
              top: 42, width: 8, height: 8,
              background: '#f1c21b',
              transform: 'rotate(45deg)',
              cursor: 'pointer',
            }}
          />
        ))}

        {/* Active playhead */}
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            left: `${activePct}%`,
            top: 0, bottom: 0, width: 1,
            background: 'var(--ag-text)',
            opacity: 0.7,
            pointerEvents: 'none',
          }}
        />

        {/* Timecode ruler */}
        <div style={{ position: 'absolute', bottom: 4, left: 0, right: 0, display: 'flex', justifyContent: 'space-between', padding: '0 4px' }}>
          {[0, 0.25, 0.5, 0.75, 1.0].map(f => (
            <span key={f} className="ag-timecode" style={{ fontSize: 9 }}>
              {fmtTime(f * totalDuration)}
            </span>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 20, marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ag-text-muted)', textTransform: 'uppercase' }}>
        <LegendItem color="rgba(15,98,254,0.5)" label="Speech" />
        <LegendItem color="rgba(82,82,82,0.6)" label="Gap (click to fix AD)" dashed />
        <LegendItem color="#da1e28" label="Error" />
        <LegendItem color="#f1c21b" label="Flag" />
      </div>
    </section>
  )
}

function LegendItem({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 16, height: 6,
        background: dashed ? 'transparent' : color,
        border: dashed ? `1px dashed ${color}` : 'none',
      }} />
      <span>{label}</span>
    </div>
  )
}

