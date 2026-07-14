/**
 * AxeScoreBadge — runs axe-core against the app's own DOM on mount.
 * Shows accessibility score as a badge. Target: ≥95 violations = 0.
 * The accessibility tool passes its own audit.
 */
import { useEffect, useState } from 'react'

interface AxeResult {
  violations: number
  passes: number
  score: number
}

export function AxeScoreBadge() {
  const [result, setResult] = useState<AxeResult | null>(null)

  useEffect(() => {
    let cancelled = false
    async function run() {
      try {
        const axe = await import('axe-core')
        const results = await axe.default.run(document.body)
        if (!cancelled) {
          const violations = results.violations.length
          const passes = results.passes.length
          const score = passes + violations > 0
            ? Math.round((passes / (passes + violations)) * 100)
            : 100
          setResult({ violations, passes, score })
        }
      } catch {
        // axe unavailable — skip silently
      }
    }
    run()
    return () => { cancelled = true }
  }, [])

  if (!result) return null

  const color = result.violations === 0 ? '#24a148' : result.violations < 3 ? '#f1c21b' : '#da1e28'

  return (
    <div
      title={`axe-core: ${result.violations} violation(s), ${result.passes} pass(es)`}
      aria-label={`Accessibility score: ${result.score}%`}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '4px 10px',
        background: `${color}22`,
        border: `1px solid ${color}55`,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
      }}
    >
      <span>♿</span>
      <span>A11Y {result.score}%</span>
    </div>
  )
}
