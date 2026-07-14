/**
 * AccessGate API client — typed interface to the FastAPI backend.
 */

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

export interface SpeechRegion {
  start: number
  end: number
}

export interface NERResult {
  ner_score: number
  band_low: number
  band_high: number
  n_words: number
  recognition_errors: number
  edition_errors: number
  passes_98_threshold: boolean
  straddles_threshold: boolean
}

export interface ConformanceReport {
  report_id?: string
  film_path: string
  caption_path: string
  ad_path: string | null
  profile: string
  results: RuleResult[]
  ner: NERResult | null
  gaps: GapRegion[]
  speech_regions: SpeechRegion[]
  error_count: number
  warning_count: number
  flag_count: number
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
}

// In production (Vercel), VITE_API_URL is set to the Render backend URL.
// In dev, the Vite proxy forwards same-origin /check etc. to localhost:8000.
const BASE = import.meta.env.VITE_API_URL ?? ''

export async function checkConformance(
  film: File,
  captions: File,
  ad: File | null,
  profile = 'netflix',
): Promise<ConformanceReport> {
  const fd = new FormData()
  fd.append('film', film)
  fd.append('captions', captions)
  if (ad) fd.append('ad', ad)
  fd.append('profile', profile)

  const resp = await fetch(`${BASE}/check`, { method: 'POST', body: fd })
  if (!resp.ok) throw new Error(`/check failed: ${resp.status}`)
  return resp.json()
}

export async function requestFix(
  film: File,
  gapStart: number,
  gapEnd: number,
): Promise<FixResult> {
  const fd = new FormData()
  fd.append('film', film)
  fd.append('gap_start', String(gapStart))
  fd.append('gap_end', String(gapEnd))

  const resp = await fetch(`${BASE}/fix`, { method: 'POST', body: fd })
  if (!resp.ok) throw new Error(`/fix failed: ${resp.status}`)
  return resp.json()
}

export async function healthCheck(): Promise<{ status: string }> {
  const resp = await fetch(`${BASE}/health`)
  return resp.json()
}

export async function loadDemo(): Promise<ConformanceReport> {
  const resp = await fetch(`${BASE}/demo`)
  if (!resp.ok) throw new Error(`/demo failed: ${resp.status}`)
  return resp.json()
}

export async function loadJudges(): Promise<unknown> {
  const resp = await fetch(`${BASE}/judges`)
  if (!resp.ok) throw new Error(`/judges failed: ${resp.status}`)
  return resp.json()
}
