/**
 * AccessGate API client — typed interface to the FastAPI backend.
 */

export interface RuleResult {
  rule_id: string
  status: 'pass' | 'fail' | 'flag' | 'skip'
  message: string
  timecode: number | null
  citation: string
  clause_id: string | null         // short standard label, e.g. "WCAG 2.2 SC 1.2.2"
  clause_url: string | null         // canonical URL for the clause
  measured: number | null          // observed value (e.g. 22.5)
  limit: number | null             // the rule's threshold (e.g. 20)
  unit: string | null              // unit for measured/limit (e.g. "cps")
  delta_pct: number | null         // signed percent over/under the limit (computed field, always present)
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

export interface Provenance {
  label: string
  model_id?: string | null
  latency_ms?: number | null
  fallback: boolean
}

export interface FixResult {
  gap: GapRegion
  draft_text: string
  draft_source?: string | null       // which model drafted (Granite Vision / watsonx / fallback)
  draft_provenance: Provenance | null
  dcmp_valid: boolean
  dcmp_issues: string[]
  guardian_cleared: boolean
  guardian_ran?: boolean             // false = the safety screen could not run
  guardian_source?: string | null    // which Guardian ran (Ollama / watsonx)
  guardian_provenance: Provenance | null
  guardian_reason: string | null
  accepted: boolean
  word_count: number
  fits_gap: boolean
  resolves_rule_ids: string[]        // DESC rules an accepted fix satisfies for the gap (always present)
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

// Demo generative fix: runs live on the deployed backend from committed
// keyframes (no film upload). Vision drafts on watsonx; DCMP validates live.
export async function loadDemoFix(gapStart: number, gapEnd: number): Promise<FixResult> {
  const fd = new FormData()
  fd.append('gap_start', String(gapStart))
  fd.append('gap_end', String(gapEnd))
  const resp = await fetch(`${BASE}/demo-fix`, { method: 'POST', body: fd })
  if (!resp.ok) throw new Error(`/demo-fix failed: ${resp.status}`)
  return resp.json()
}

export interface ReportSummary {
  summary: string
  model_id: string
  source: string
  error: string | null
}

// Granite plain-English summary of the demo report (loaded via LOAD DEMO).
export async function loadDemoSummary(): Promise<ReportSummary> {
  const resp = await fetch(`${BASE}/demo-summary`)
  if (!resp.ok) throw new Error(`/demo-summary failed: ${resp.status}`)
  return resp.json()
}

// Granite summary of an uploaded report.
export async function summarizeReport(report: ConformanceReport): Promise<ReportSummary> {
  const resp = await fetch(`${BASE}/summary`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(report),
  })
  if (!resp.ok) throw new Error(`/summary failed: ${resp.status}`)
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

// ---------------------------------------------------------------------------
// Conformance review session (event-sourced, natural-language drivable)
// ---------------------------------------------------------------------------
export type ReviewStatus = 'open' | 'accepted' | 'dismissed' | 'flagged'

export interface ReviewFindingNode {
  key: string
  rule_id: string
  status_source: string
  level: string
  timecode: number | null
  message: string
  review_status: ReviewStatus
  note: string | null
  reason: string | null
}

export interface ReviewAuditEntry {
  seq: number
  kind: string
  target: string
  source: string
  actor: string
  payload: Record<string, unknown>
  undo_of: string | null
}

export interface NLView {
  intent: 'mutate' | 'query' | 'unknown'
  engine: string
  reasoning: string
  matched: string[]
  compiled_ops: { kind: string; target: string; payload: Record<string, unknown> }[]
  query: Record<string, unknown> | null
  applied: number
}

export interface ReviewSessionView {
  session_id: string
  report_id: string | null
  version: number
  summary: Record<string, number>
  findings: Record<string, ReviewFindingNode>
  fixes: Record<string, string>
  audit_log: ReviewAuditEntry[]
  nl?: NLView
}

async function reviewPost(path: string, body: unknown): Promise<ReviewSessionView> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`${path} failed: ${resp.status}`)
  return resp.json()
}

export const createReviewSession = (reportId: string) =>
  reviewPost('/review/session', { report_id: reportId })

export const reviewNL = (sessionId: string, phrase: string, apply = true) =>
  reviewPost('/review/nl', { session_id: sessionId, phrase, apply })

export const applyReviewOp = (
  sessionId: string, kind: string, target: string,
  payload: Record<string, unknown> = {},
) => reviewPost('/review/op', { session_id: sessionId, kind, target, payload })

export const reviewUndo = (sessionId: string) =>
  reviewPost('/review/undo', { session_id: sessionId })

// Editor-native export download URLs (a file a captioner/AD writer can use).
export const exportUrl = (reportId: string, file: 'findings.csv' | 'markers.vtt') =>
  `${BASE}/export/${encodeURIComponent(reportId)}/${file}`
