/**
 * WaveformDisplay — WaveSurfer.js-backed audio waveform with gap overlays.
 *
 * Props:
 *   file            — File object to analyse
 *   gaps            — GapRegion[] from conformance report (amber overlays)
 *   activeTimecode  — external seek target
 *   onTimecodeClick — fires when user clicks the waveform with the new time (s)
 *
 * Design: Carbon Gray 100 dark theme, amber gap regions, IBM Blue waveform.
 */
import { useEffect, useRef } from 'react'
import WaveSurfer from 'wavesurfer.js'
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.js'
import type { GapRegion } from '../api/client'

interface Props {
  file: File | null
  gaps: GapRegion[]
  activeTimecode: number
  onTimecodeClick: (t: number) => void
}

// Semi-transparent amber for gap overlays — matches --ag-amber (#f1c21b)
const GAP_COLOR = 'rgba(241, 194, 27, 0.25)'
const GAP_BORDER = 'rgba(241, 194, 27, 0.6)'

export function WaveformDisplay({ file, gaps, activeTimecode, onTimecodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const wavesurferRef = useRef<WaveSurfer | null>(null)
  const regionsRef = useRef<RegionsPlugin | null>(null)
  const srcUrlRef = useRef<string | null>(null)
  const lastSeekRef = useRef<number>(-1)
  // Prevent feedback: when WS fires a seek event from our own programmatic seek
  const seekingProgrammaticallyRef = useRef(false)

  // Initialise WaveSurfer once
  useEffect(() => {
    if (!containerRef.current) return

    const regions = RegionsPlugin.create()
    regionsRef.current = regions

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#0f62fe',       // --ag-blue
      progressColor: '#4589ff',   // --ag-blue-light
      cursorColor: '#f4f4f4',     // --ag-text
      cursorWidth: 1,
      height: 80,
      normalize: true,
      interact: true,
      plugins: [regions],
    })
    wavesurferRef.current = ws

    // Seek clicks from the waveform
    ws.on('interaction', (newTime: number) => {
      if (!seekingProgrammaticallyRef.current) {
        onTimecodeClick(newTime)
      }
    })

    return () => {
      ws.destroy()
      wavesurferRef.current = null
      regionsRef.current = null
      if (srcUrlRef.current) {
        URL.revokeObjectURL(srcUrlRef.current)
        srcUrlRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Load file into WaveSurfer when it changes
  useEffect(() => {
    const ws = wavesurferRef.current
    if (!ws) return

    if (srcUrlRef.current) {
      URL.revokeObjectURL(srcUrlRef.current)
      srcUrlRef.current = null
    }

    if (!file) return

    const url = URL.createObjectURL(file)
    srcUrlRef.current = url
    lastSeekRef.current = -1
    ws.load(url)
  }, [file])

  // Redraw gap regions whenever gaps or the WaveSurfer instance changes
  useEffect(() => {
    const regions = regionsRef.current
    if (!regions) return

    regions.clearRegions()

    gaps.forEach((g, i) => {
      regions.addRegion({
        id: `gap-${i}`,
        start: g.start,
        end: g.end,
        color: GAP_COLOR,
        drag: false,
        resize: false,
        // Draw a custom left border to mimic the dashed gap style
        content: (() => {
          const el = document.createElement('div')
          el.style.cssText = [
            'position:absolute',
            'inset:0',
            `border:1px solid ${GAP_BORDER}`,
            'border-left-width:2px',
            'pointer-events:none',
          ].join(';')
          return el
        })(),
      })
    })
  }, [gaps])

  // Seek when activeTimecode prop changes
  useEffect(() => {
    const ws = wavesurferRef.current
    if (!ws || !file) return
    if (activeTimecode === lastSeekRef.current) return
    lastSeekRef.current = activeTimecode

    seekingProgrammaticallyRef.current = true
    ws.setTime(activeTimecode)
    // Reset the flag after the current event loop tick
    setTimeout(() => { seekingProgrammaticallyRef.current = false }, 0)
  }, [activeTimecode, file])

  // Revoke URL on unmount
  useEffect(() => {
    return () => {
      if (srcUrlRef.current) {
        URL.revokeObjectURL(srcUrlRef.current)
        srcUrlRef.current = null
      }
    }
  }, [])

  return (
    <div style={{ background: 'var(--ag-surface)', border: '1px solid var(--ag-border)' }}>
      <div style={{
        padding: '8px 12px',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        textTransform: 'uppercase',
        color: 'var(--ag-text-muted)',
        letterSpacing: 1,
        borderBottom: '1px solid var(--ag-border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>Waveform</span>
        {gaps.length > 0 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              display: 'inline-block',
              width: 12, height: 6,
              background: GAP_COLOR,
              border: `1px solid ${GAP_BORDER}`,
            }} />
            <span>{gaps.length} gap{gaps.length !== 1 ? 's' : ''}</span>
          </span>
        )}
      </div>

      {file ? (
        <div
          ref={containerRef}
          role="application"
          aria-label="Audio waveform — click to seek"
          style={{
            width: '100%',
            background: 'var(--ag-bg)',
            // Override WaveSurfer's default cursor/select
            cursor: 'crosshair',
          }}
        />
      ) : (
        <div style={{
          height: 96,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          color: 'var(--ag-text-muted)',
          letterSpacing: 0.5,
        }}>
          No audio loaded
        </div>
      )}
    </div>
  )
}
