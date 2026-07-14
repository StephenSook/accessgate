/**
 * VideoPlayer — Video.js-backed media player.
 *
 * Props:
 *   file            — File object to play (creates an object URL)
 *   src             — URL source (e.g. the committed demo clip)
 *   activeTimecode  — external seek target; component seeks when this changes
 *   onTimeUpdate    — fires as playback progresses with the current time (s)
 *
 * Design: Carbon Gray 100 dark theme, IBM Plex Mono UI labels, 21hrs.space motif.
 *
 * Note on the init pattern: video.js mutates the DOM around its media element,
 * which conflicts with a React-owned <video> node under StrictMode's
 * mount→unmount→mount cycle (the player disposes and never cleanly re-creates).
 * We follow the video.js React guidance instead: keep a plain wrapper div that
 * React owns, and create the <video-js> element imperatively inside it, guarded
 * by playerRef so re-invocation is idempotent.
 */
import { useEffect, useRef } from 'react'
import videojs from 'video.js'
import type Player from 'video.js/dist/types/player'
import 'video.js/dist/video-js.css'

interface Props {
  file: File | null
  src?: string            // URL source (e.g. the committed demo clip)
  activeTimecode: number
  onTimeUpdate: (t: number) => void
}

export function VideoPlayer({ file, src, activeTimecode, onTimeUpdate }: Props) {
  const hasMedia = !!file || !!src
  const containerRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<Player | null>(null)
  const srcUrlRef = useRef<string | null>(null)
  const onTimeUpdateRef = useRef(onTimeUpdate)
  // Track the last timecode we seeked to so we don't re-seek on every render
  const lastSeekRef = useRef<number>(-1)

  // Keep the latest callback without re-initialising the player
  useEffect(() => { onTimeUpdateRef.current = onTimeUpdate }, [onTimeUpdate])

  // Initialise Video.js once the container exists; tear down on unmount.
  useEffect(() => {
    if (playerRef.current || !containerRef.current) return

    // Create the media element imperatively so React never owns a node that
    // video.js rewrites underneath it.
    const videoEl = document.createElement('video-js')
    videoEl.classList.add('vjs-big-play-centered', 'vjs-theme-ag')
    videoEl.setAttribute('aria-label', file ? `Video preview: ${file.name}` : 'Demo film preview')
    containerRef.current.appendChild(videoEl)

    const player = videojs(videoEl, {
      controls: true,
      fluid: true,
      preload: 'auto',
      playbackRates: [0.5, 1, 1.25, 1.5, 2],
    })
    playerRef.current = player

    player.on('timeupdate', () => {
      onTimeUpdateRef.current(player.currentTime() ?? 0)
    })

    return () => {
      if (playerRef.current && !playerRef.current.isDisposed()) {
        playerRef.current.dispose()
      }
      playerRef.current = null
    }
    // aria-label is a one-time label; source swaps are handled by the load
    // effect below, so we deliberately only re-init when media appears/vanishes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasMedia])

  // When file/src changes: revoke old URL, load the new source into the player.
  useEffect(() => {
    const player = playerRef.current
    if (!player) return

    if (srcUrlRef.current) {
      URL.revokeObjectURL(srcUrlRef.current)
      srcUrlRef.current = null
    }

    if (file) {
      const url = URL.createObjectURL(file)
      srcUrlRef.current = url
      player.src({ src: url, type: file.type || 'video/mp4' })
      lastSeekRef.current = -1
    } else if (src) {
      player.src({ src, type: 'video/mp4' })
      lastSeekRef.current = -1
    } else {
      player.src('')
    }
  }, [file, src])

  // Seek when activeTimecode prop changes (e.g. timeline click)
  useEffect(() => {
    const player = playerRef.current
    if (!player || !hasMedia) return
    if (activeTimecode === lastSeekRef.current) return
    lastSeekRef.current = activeTimecode

    // Use readyState to guard against seeking before metadata is loaded
    if (player.readyState() >= 1) {
      player.currentTime(activeTimecode)
    } else {
      player.one('loadedmetadata', () => {
        player.currentTime(activeTimecode)
      })
    }
  }, [activeTimecode, hasMedia])

  // Revoke object URL on final unmount
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
      }}>
        Video Preview
      </div>

      {hasMedia ? (
        <div ref={containerRef} data-vjs-player style={{ width: '100%' }} />
      ) : (
        <div style={{
          height: 200,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          color: 'var(--ag-text-muted)',
          letterSpacing: 0.5,
        }}>
          Drop a video file to preview
        </div>
      )}
    </div>
  )
}
