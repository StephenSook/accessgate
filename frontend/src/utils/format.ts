/**
 * Shared timecode formatting used by the timeline, the rule table, and the fix
 * panel. Previously duplicated in three components.
 */
export function fmtTime(seconds: number, withMs = true): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  const base = `${m}:${String(s).padStart(2, '0')}`
  if (!withMs) return base
  const ms = Math.floor((seconds % 1) * 10)
  return `${base}.${ms}`
}
