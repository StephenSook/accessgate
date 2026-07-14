/**
 * AccessGate mobile API client — talks to the same live backend as the web app.
 * Types are the shared contract from the FastAPI backend (src/models.py).
 */

export const BASE = 'https://accessgate-api.onrender.com'

export interface RuleResult {
  rule_id: string
  status: 'pass' | 'fail' | 'flag' | 'skip'
  message: string
  timecode: number | null
  citation: string
  sarif_level: 'error' | 'warning' | 'note'
  confidence: number | null
  human_review_required: boolean
}

export interface GapRegion {
  start: number
  end: number
  duration: number
  max_words?: number
}

export interface NERResult {
  ner_score: number
  band_low: number
  band_high: number
  passes_98_threshold: boolean
  straddles_threshold: boolean
}

export interface ConformanceReport {
  report_id?: string
  profile: string
  results: RuleResult[]
  ner: NERResult | null
  gaps: GapRegion[]
  speech_regions: { start: number; end: number }[]
  error_count: number
  warning_count: number
  flag_count: number
}

export interface ReportSummary {
  summary: string
  model_id: string
  source: string
  error: string | null
}

export interface FixResult {
  gap: GapRegion
  draft_text: string
  dcmp_valid: boolean
  dcmp_issues: string[]
  guardian_cleared: boolean
  guardian_reason: string | null
  accepted: boolean
  word_count: number
  fits_gap: boolean
  draft_source?: string
}

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`)
  if (!resp.ok) throw new Error(`${path} failed: ${resp.status}`)
  return resp.json()
}

export const loadDemo = () => getJson<ConformanceReport>('/demo')
export const loadDemoSummary = () => getJson<ReportSummary>('/demo-summary')
export const loadJudges = () => getJson<Record<string, unknown>>('/judges')

export async function loadDemoFix(gapStart: number, gapEnd: number): Promise<FixResult> {
  const fd = new FormData()
  fd.append('gap_start', String(gapStart))
  fd.append('gap_end', String(gapEnd))
  const resp = await fetch(`${BASE}/demo-fix`, { method: 'POST', body: fd })
  if (!resp.ok) throw new Error(`/demo-fix failed: ${resp.status}`)
  return resp.json()
}

// Check a caption file the user picked on device (structural rules; no film).
export async function checkCaptions(uri: string, name: string, profile = 'netflix'): Promise<ConformanceReport> {
  const fd = new FormData()
  fd.append('captions', { uri, name, type: 'application/octet-stream' } as unknown as Blob)
  fd.append('profile', profile)
  const resp = await fetch(`${BASE}/check-captions`, { method: 'POST', body: fd })
  if (!resp.ok) throw new Error(`/check-captions failed: ${resp.status}`)
  return resp.json()
}
