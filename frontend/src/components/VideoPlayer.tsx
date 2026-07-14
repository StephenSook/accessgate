/**
 * VideoPlayer — Video.js-backed media player.
 *
 * Props:
 *   file            — File object to play (creates an object URL)
 *   activeTimecode  — external seek target; component seeks when this changes
 *   onTimeUpdate    — fires as playback progresses with the current time (s)
 *
 * Design: Carbon Gray 100 dark theme, IBM Plex Mono UI labels, 21hrs.space motif.
 */
import { useEffect, useRef } from 'react'
import videojs from 'video.js'
import type Player from 'video.js/dist/types/player'
import 'video.js/dist/video-js.css'

interface Props {
  file: File | null
  activeTimecode: number
  onTimeUpdate: (t: number) => void
}

export function VideoPlayer({ file, activeTimecode, onTimeUpdate }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const playerRef = useRef<Player | null>(null)
  const srcUrlRef = useRef<string | null>(null)
  // Track the last timecode we seeked to so we don't re-seek on every render
  const lastSeekRef = useRef<number>(-1)

  // Initialise Video.js once on mount; tear down on unmount
  useEffect(() => {
    if (!videoRef.current) return

    const player = videojs(videoRef.current, {
      controls: true,
      fluid: true,
      preload: 'auto',
      playbackRates: [0.5, 1, 1.25, 1.5, 2],
    })
    playerRef.current = player

    player.on('timeupdate', () => {
      onTimeUpdate(player.currentTime() ?? 0)
    })

    return () => {
      player.dispose()
      playerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // When file changes: revoke old URL, create new one, load into player
  useEffect(() => {
    const player = playerRef.current
    if (!player) return

    // Revoke previous URL
    if (srcUrlRef.current) {
      URL.revokeObjectURL(srcUrlRef.current)
      srcUrlRef.current = null
    }

    if (!file) {
      player.src('')
      return
    }

    const url = URL.createObjectURL(file)
    srcUrlRef.current = url
    player.src({ src: url, type: file.type || 'video/mp4' })
    lastSeekRef.current = -1
  }, [file])

  // Seek when activeTimecode prop changes (e.g. timeline click)
  useEffect(() => {
    const player = playerRef.current
    if (!player || !file) return
    if (activeTimecode === lastSeekRef.current) return
    lastSeekRef.current = activeTimecode

    // Use ready() to guard against seeking before metadata is loaded
    if (player.readyState() >= 1) {
      player.currentTime(activeTimecode)
    } else {
      player.one('loadedmetadata', () => {
        player.currentTime(activeTimecode)
      })
    }
  }, [activeTimecode, file])

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

      {file ? (
        <div data-vjs-player style={{ width: '100%' }}>
          <video
            ref={videoRef}
            className="video-js vjs-big-play-centered vjs-theme-ag"
            aria-label={`Video preview: ${file.name}`}
          />
        </div>
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
