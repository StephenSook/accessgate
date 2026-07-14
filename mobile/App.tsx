import React, { useState } from 'react'
import {
  ActivityIndicator, Modal, Pressable, ScrollView, StatusBar,
  StyleSheet, Text, View,
} from 'react-native'
import * as DocumentPicker from 'expo-document-picker'
import {
  ConformanceReport, FixResult, GapRegion, ReportSummary, RuleResult,
  checkCaptions, loadDemo, loadDemoFix, loadDemoSummary,
} from './src/api'

const C = {
  bg: '#161616', surface: '#262626', surface2: '#393939', border: '#525252',
  text: '#f4f4f4', muted: '#a8a8a8', blue: '#0f62fe', blueLight: '#4589ff',
  red: '#da1e28', amber: '#f1c21b', green: '#24a148', corner: '#e4b592',
}
const MONO = 'Courier'

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
const statusColor = (s: string) =>
  s === 'fail' ? C.red : s === 'flag' ? C.amber : s === 'pass' ? C.green : C.muted

export default function App() {
  const [report, setReport] = useState<ConformanceReport | null>(null)
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [gap, setGap] = useState<GapRegion | null>(null)

  async function demo() {
    setError(null); setLoading('Loading demo…'); setSummary(null)
    try {
      const r = await loadDemo(); setReport(r)
      loadDemoSummary().then(setSummary).catch(() => {})
    } catch (e) { setError(String(e)) } finally { setLoading(null) }
  }

  async function pick() {
    setError(null)
    const res = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true })
    if (res.canceled) return
    const a = res.assets[0]
    setLoading('Checking captions…'); setSummary(null)
    try {
      const r = await checkCaptions(a.uri, a.name); setReport(r)
    } catch (e) { setError(String(e)) } finally { setLoading(null) }
  }

  if (!report) {
    return (
      <View style={[s.screen, s.center]}>
        <StatusBar barStyle="light-content" />
        <View style={s.corner} />
        <Text style={s.eyebrow}>IBM AI BUILDERS CHALLENGE 2026</Text>
        <Text style={s.title}>AccessGate</Text>
        <Text style={s.sub}>Film accessibility conformance, in your pocket.</Text>
        <Text style={s.blurb}>
          Scores caption and audio-description files against WCAG 2.2, FCC 79.1, DCMP and
          Netflix rules, cites the exact standard behind every flag, and drafts a fix for
          each silent gap. Same live engine as the web app.
        </Text>
        <Pressable style={s.btnPrimary} onPress={demo}>
          <Text style={s.btnPrimaryText}>LOAD DEMO</Text>
        </Pressable>
        <Pressable style={s.btnGhost} onPress={pick}>
          <Text style={s.btnGhostText}>CHECK A CAPTION FILE</Text>
        </Pressable>
        {loading && <ActivityIndicator color={C.blueLight} style={{ marginTop: 20 }} />}
        {error && <Text style={s.error}>{error}</Text>}
      </View>
    )
  }

  const metrics = [
    { label: 'ERRORS', value: report.error_count, color: C.red },
    { label: 'WARNINGS', value: report.warning_count, color: C.amber },
    { label: 'FLAGS', value: report.flag_count, color: C.blueLight },
    ...(report.ner ? [{ label: 'NER', value: `${(report.ner.ner_score * 100).toFixed(1)}%`, color: report.ner.passes_98_threshold ? C.green : C.amber }] : []),
    { label: 'GAPS', value: report.gaps.length, color: C.muted },
  ]

  return (
    <View style={s.screen}>
      <StatusBar barStyle="light-content" />
      <ScrollView contentContainerStyle={{ padding: 16, paddingTop: 56, paddingBottom: 48 }}>
        <View style={s.rowBetween}>
          <Text style={s.h1}>AccessGate</Text>
          <Pressable onPress={() => { setReport(null); setSummary(null) }}>
            <Text style={s.link}>NEW</Text>
          </Pressable>
        </View>
        <Text style={s.profile}>Profile: {report.profile.toUpperCase()}</Text>

        <View style={s.metrics}>
          {metrics.map((m) => (
            <View key={m.label} style={s.metric}>
              <Text style={s.metricLabel}>{m.label}</Text>
              <Text style={[s.metricValue, { color: m.color }]}>{String(m.value)}</Text>
            </View>
          ))}
        </View>

        {summary?.summary ? (
          <View style={s.card}>
            <Text style={s.cardLabel}>EXECUTIVE SUMMARY · {summary.source.toUpperCase()}</Text>
            <Text style={s.cardText}>{summary.summary}</Text>
          </View>
        ) : null}

        {report.gaps.length > 0 && (
          <>
            <Text style={s.section}>DIALOGUE-FREE GAPS · TAP TO FIX</Text>
            {report.gaps.map((g, i) => (
              <Pressable key={i} style={s.gap} onPress={() => setGap(g)}>
                <Text style={s.gapTime}>{fmt(g.start)} → {fmt(g.end)}</Text>
                <Text style={s.gapMeta}>{g.duration.toFixed(1)}s · fix AD ›</Text>
              </Pressable>
            ))}
          </>
        )}

        <Text style={s.section}>RULE RESULTS · {report.results.length}</Text>
        {report.results
          .filter((r) => r.status === 'fail' || r.status === 'flag')
          .map((r, i) => <RuleRow key={i} r={r} />)}
      </ScrollView>

      <FixModal gap={gap} onClose={() => setGap(null)} />
    </View>
  )
}

function RuleRow({ r }: { r: RuleResult }) {
  const [open, setOpen] = useState(false)
  return (
    <Pressable style={s.rule} onPress={() => setOpen((v) => !v)}>
      <View style={s.rowBetween}>
        <Text style={[s.ruleId, { color: statusColor(r.status) }]}>{r.rule_id}</Text>
        <Text style={[s.ruleStatus, { color: statusColor(r.status) }]}>{r.status.toUpperCase()}</Text>
      </View>
      <Text style={s.ruleMsg}>{r.message}</Text>
      {open && <Text style={s.ruleCite}>“{r.citation}”</Text>}
    </Pressable>
  )
}

function FixModal({ gap, onClose }: { gap: GapRegion | null; onClose: () => void }) {
  const [loading, setLoading] = useState(false)
  const [fix, setFix] = useState<FixResult | null>(null)
  const [accepted, setAccepted] = useState(false)

  React.useEffect(() => { setFix(null); setAccepted(false) }, [gap])

  async function run() {
    if (!gap) return
    setLoading(true)
    try { setFix(await loadDemoFix(gap.start, gap.end)) } finally { setLoading(false) }
  }

  return (
    <Modal visible={!!gap} animationType="slide" transparent onRequestClose={onClose}>
      <View style={s.modalWrap}>
        <View style={s.modal}>
          <View style={s.rowBetween}>
            <Text style={s.cardLabel}>GATED GENERATIVE FIX</Text>
            <Pressable onPress={onClose}><Text style={s.close}>×</Text></Pressable>
          </View>
          {gap && <Text style={s.gapTime}>{fmt(gap.start)} → {fmt(gap.end)} · {gap.duration.toFixed(1)}s</Text>}

          {!fix && !loading && (
            <Pressable style={s.btnPrimary} onPress={run}>
              <Text style={s.btnPrimaryText}>GENERATE AUDIO DESCRIPTION</Text>
            </Pressable>
          )}
          {loading && <ActivityIndicator color={C.blueLight} style={{ marginVertical: 24 }} />}

          {fix && (
            <ScrollView style={{ marginTop: 8 }}>
              <Stage label="1. VISION DRAFT" color={C.blueLight}>
                <Text style={s.draft}>“{fix.draft_text}”</Text>
                <Text style={[s.small, { color: fix.fits_gap ? C.green : C.red }]}>
                  {fix.word_count} words · {fix.fits_gap ? '✓ fits gap' : '✗ too long'}
                </Text>
                {fix.draft_source && <Text style={s.small}>drafted by {fix.draft_source}</Text>}
              </Stage>
              <Stage label="2. DCMP STRUCTURE CHECK" color={fix.dcmp_valid ? C.green : C.red}>
                <Text style={[s.small, { color: fix.dcmp_valid ? C.green : C.red }]}>
                  {fix.dcmp_valid ? '✓ All DCMP DESC rules pass' : fix.dcmp_issues.join('; ')}
                </Text>
              </Stage>
              <Stage label="3. GRANITE GUARDIAN SCREEN" color={fix.guardian_cleared ? C.green : C.red}>
                <Text style={[s.small, { color: fix.guardian_cleared ? C.green : C.red }]}>
                  {fix.guardian_cleared ? '✓ Content safety cleared' : fix.guardian_reason}
                </Text>
              </Stage>
              {accepted ? (
                <View style={s.accepted}><Text style={s.acceptedText}>✓ FIX ACCEPTED — ROW FLIPPED GREEN</Text></View>
              ) : (
                <Pressable
                  style={[s.btnPrimary, { backgroundColor: fix.accepted ? C.green : C.surface2 }]}
                  disabled={!fix.accepted}
                  onPress={() => setAccepted(true)}
                >
                  <Text style={s.btnPrimaryText}>{fix.accepted ? 'ACCEPT FIX' : 'CANNOT ACCEPT'}</Text>
                </Pressable>
              )}
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  )
}

function Stage({ label, color, children }: { label: string; color: string; children: React.ReactNode }) {
  return (
    <View style={[s.stage, { borderColor: color + '55' }]}>
      <Text style={[s.stageLabel, { color }]}>{label}</Text>
      {children}
    </View>
  )
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  center: { justifyContent: 'center', alignItems: 'center', padding: 28 },
  corner: { position: 'absolute', top: 44, left: 20, width: 60, height: 60, borderTopWidth: 2, borderLeftWidth: 2, borderColor: C.corner, opacity: 0.5 },
  eyebrow: { fontFamily: MONO, fontSize: 10, letterSpacing: 2, color: C.muted, marginBottom: 8 },
  title: { fontSize: 40, fontWeight: '800', color: C.text, letterSpacing: -1 },
  sub: { fontSize: 15, color: C.muted, marginTop: 6, textAlign: 'center' },
  blurb: { fontSize: 13, color: C.muted, marginTop: 18, lineHeight: 20, textAlign: 'center' },
  btnPrimary: { backgroundColor: C.blue, paddingVertical: 14, paddingHorizontal: 28, marginTop: 24, alignSelf: 'stretch' },
  btnPrimaryText: { color: '#fff', fontWeight: '700', fontSize: 14, textAlign: 'center', letterSpacing: 0.5 },
  btnGhost: { borderWidth: 1, borderColor: C.border, paddingVertical: 13, paddingHorizontal: 24, marginTop: 12, alignSelf: 'stretch' },
  btnGhostText: { color: C.muted, fontFamily: MONO, fontSize: 12, textAlign: 'center', letterSpacing: 1 },
  error: { color: C.red, marginTop: 16, fontSize: 12 },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  h1: { fontSize: 26, fontWeight: '800', color: C.text },
  link: { fontFamily: MONO, fontSize: 12, color: C.blueLight, letterSpacing: 1 },
  profile: { fontFamily: MONO, fontSize: 10, color: C.muted, marginTop: 2, marginBottom: 16, letterSpacing: 1 },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 18, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, padding: 16 },
  metric: {},
  metricLabel: { fontFamily: MONO, fontSize: 9, color: C.muted, letterSpacing: 1 },
  metricValue: { fontSize: 22, fontWeight: '800', marginTop: 2 },
  card: { borderWidth: 1, borderColor: C.border, borderLeftWidth: 2, borderLeftColor: C.blueLight, padding: 14, marginTop: 16 },
  cardLabel: { fontFamily: MONO, fontSize: 10, color: C.blueLight, letterSpacing: 1, marginBottom: 8 },
  cardText: { fontSize: 14, color: C.text, lineHeight: 21 },
  section: { fontFamily: MONO, fontSize: 10, color: C.muted, letterSpacing: 1, marginTop: 24, marginBottom: 8 },
  gap: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  gapTime: { fontFamily: MONO, fontSize: 13, color: C.text },
  gapMeta: { fontFamily: MONO, fontSize: 11, color: C.corner },
  rule: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 8 },
  ruleId: { fontFamily: MONO, fontSize: 12, fontWeight: '700' },
  ruleStatus: { fontFamily: MONO, fontSize: 10 },
  ruleMsg: { fontSize: 13, color: C.text, marginTop: 6, lineHeight: 18 },
  ruleCite: { fontSize: 12, color: C.muted, marginTop: 8, fontStyle: 'italic', lineHeight: 17 },
  modalWrap: { flex: 1, backgroundColor: '#000000aa', justifyContent: 'flex-end' },
  modal: { backgroundColor: C.surface, borderTopWidth: 2, borderTopColor: C.corner, padding: 20, maxHeight: '85%' },
  close: { color: C.muted, fontSize: 26 },
  draft: { fontSize: 15, color: C.text, fontStyle: 'italic', lineHeight: 22 },
  small: { fontFamily: MONO, fontSize: 11, color: C.muted, marginTop: 6 },
  stage: { borderWidth: 1, padding: 12, marginTop: 12 },
  stageLabel: { fontFamily: MONO, fontSize: 10, letterSpacing: 1, marginBottom: 6 },
  accepted: { backgroundColor: '#24a14822', borderWidth: 1, borderColor: C.green, padding: 14, marginTop: 12 },
  acceptedText: { color: C.green, fontFamily: MONO, fontSize: 12, textAlign: 'center' },
})
