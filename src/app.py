"""
FastAPI application for AccessGate.

Endpoints:
  POST /check       - Full conformance pre-check (file upload)
  GET  /gaps        - Detect dialogue-free gaps in a film
  WS   /live        - Live caption monitoring (WebSocket streaming)
  GET  /health      - Health check (keepalive)
  GET  /report/{id} - Retrieve a cached report

Run: uvicorn src.app:app --reload --port 8000
"""
from __future__ import annotations
import json
import logging
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.standards_registry import enrich_report_dict

logger = logging.getLogger(__name__)


def _warm_citation_index_async() -> None:
    """
    Build the RAG citation index off the request path, in the background.

    On the hosted deploy the committed index was built with a different encoder
    than this environment resolves, so the first query would otherwise pay for a
    full rebuild (several sequential embedding calls) while a user waited. Render
    free-tier instances have an ephemeral filesystem and spin down when idle, so
    that cost recurs on every cold start.

    Runs in a daemon thread so startup, and therefore /health which the keepalive
    cron pings, stays immediate. Failures are logged and swallowed: rag.py already
    degrades to the deterministic encoder on its own, and a warm-up that could
    take the server down would be worse than a slow first query.
    """
    def _warm() -> None:
        try:
            from src.rag import _load_index, encoder_id
            _load_index()
            logger.info("Citation index warm, encoder %s.", encoder_id())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Citation index warm-up failed: %s", exc)

    threading.Thread(target=_warm, name="rag-index-warm", daemon=True).start()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _warm_citation_index_async()
    yield


app = FastAPI(
    title="AccessGate",
    description="Film accessibility conformance pre-check engine.",
    version="1.0.0",
    lifespan=_lifespan,
)

# CORS: this is an open, read-only demo API (Vercel frontend + mobile clients),
# so a single wildcard is the honest configuration — the explicit localhosts
# alongside "*" were redundant.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory report cache (keyed by report_id)
_report_cache: dict[str, dict] = {}




def _citation_provenance() -> dict:
    """
    Report which encoder is actually retrieving citations on THIS instance.

    The gated fix already states the engine behind every generated line. The
    citation layer deserves the same treatment: a judge should not have to infer
    from the text of a citation whether a Granite model produced it. `active` is
    what this process would use for a query right now; `index_built_with` is what
    the on-disk index was actually embedded with. They agree in a healthy state,
    and a mismatch is exactly the condition that triggers a rebuild.
    """
    try:
        from src.rag import _read_index_meta, encoder_id
        return {
            "active": encoder_id(),
            "index_built_with": _read_index_meta().get("encoder"),
            "note": "Best-available resolution: Granite Embedding r2 locally, watsonx-hosted Granite on this deploy, deterministic character n-gram as the last resort so citations survive with every hosted API deleted.",
        }
    except Exception as exc:  # noqa: BLE001
        # Never let a transparency field take down the transparency page.
        return {"active": None, "error": str(exc)}


def _safe_name(filename: Optional[str], default: str) -> str:
    """Basename of an uploaded filename, preventing path traversal (../, /)."""
    name = Path(filename or "").name
    return name or default


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Health check endpoint — used by CI keepalive and frontend."""
    demo_mode = os.getenv("ACCESSGATE_DEMO_MODE", "false").lower() == "true"
    return {"status": "ok", "service": "AccessGate", "demo_mode": demo_mode}


# ---------------------------------------------------------------------------
# Demo endpoint — pre-computed NOTLD report (served on Render / no Ollama)
# ---------------------------------------------------------------------------

@app.get("/demo")
def demo_report() -> JSONResponse:
    """
    Return the pre-computed Night of the Living Dead conformance report.

    This endpoint is always available — in both full local mode and on the
    Render-hosted deployment where the heavy ML inference stack is not present.
    It lets judges see the full UI (timeline, rule table, NER score, gap markers)
    without needing to upload a video file.
    """
    demo_path = Path(__file__).parent.parent / "data" / "demo" / "demo_report.json"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="Demo report not found.")
    with open(demo_path) as f:
        # The committed demo artifact predates the clause-reference field; add the
        # canonical clause URLs on the way out so /demo matches a live /check.
        return JSONResponse(content=enrich_report_dict(json.load(f)))


# ---------------------------------------------------------------------------
# Judges transparency endpoint — honesty tier breakdown
# ---------------------------------------------------------------------------

@app.get("/judges")
def judges_page() -> JSONResponse:
    """
    Transparency page for judges — honesty tier breakdown.

    Shows exactly what is: wired-live (runs locally without any hosted API),
    integration (calls a hosted API but gracefully degrades),
    accelerator (IBM Bob tooling, not runtime product code).
    """
    return JSONResponse(content={
        "claim": "conformance pre-check: automatable checks plus human-judgment flags",
        "not_a": ["conformance certifier", "accessibility auditor", "legal compliance tool"],
        "scope_boundaries": [
            {"not_checked": "Audio-description final-mix loudness",
             "why": "AccessGate scores the audio-description sidecar file for structure, timing, and gap-fit, not the delivered audio mix level. Surfaced by a real audio-description user who described AD mixed too quietly under the soundtrack in one release."},
            {"not_checked": "Semantic sufficiency of a description or caption",
             "why": "Whether a present, well-timed description actually conveys the needed meaning is a human-judgment flag, not an automated pass or fail."},
        ],
        "tiers": {
            "wired_live": [
                {"name": "23-rule evaluator engine", "evidence": "src/evaluators/, tests/test_evaluators.py"},
                {"name": "Silero VAD gap detection", "evidence": "src/gap_engine.py"},
                {"name": "NER-style caption scorer", "evidence": "src/ner_scorer.py", "note": "Never auto-fails on ASR alone (Koenecke et al. PNAS 2020)"},
                {"name": "Caption error-type classifier (recognition vs edition)", "evidence": "src/ner_scorer.py (_classify_error, phonetic heuristic)", "note": "The live NER path classifies with a phonetic heuristic (jellyfish). A trained sklearn model (macro-F1 0.94 on a synthetic weak-labeled held-out set) is a separate, documented, reproducible artifact (see data/training/model_card.md), not the runtime classifier."},
                {"name": "RAG citation engine (Granite Embedding)", "evidence": "src/rag.py", "note": "Citations are retrieved at runtime rather than mapped rule-to-string. The corpus is the six Docling-parsed standard pages (206 of 218 chunks) plus committed short-form clause text for the same six standards (12 chunks, src/rag.py _INLINE_STANDARDS), both chunked into the same index. The encoder resolves best-available: Granite Embedding r2 locally via sentence-transformers; on this hosted deploy, which omits the embedding stack (requirements-deploy.txt), watsonx-hosted Granite embeddings over REST (ibm/granite-embedding-278m-multilingual, src/watsonx_embedding.py); and a deterministic character n-gram encoder as the last resort, so citations still work with every hosted API deleted. The active encoder is recorded in standards/index/index_meta.json and the index rebuilds if it changes."},
                {"name": "SARIF 2.1.0 exporter", "evidence": "src/exporters/sarif.py"},
                {"name": "OSCAL POA&M v1.1.2 exporter", "evidence": "src/exporters/oscal.py"},
                {"name": "Editor-native exports (WebVTT AD track, findings CSV, WebVTT markers)", "evidence": "src/exporters/editor.py", "note": "A file a captioner or AD writer can open and use, not just a compliance document; the CSV is formula-injection hardened. Example artifacts: data/demo/editor_exports/"},
                {"name": "MCP server (self-referential loop)", "evidence": "src/mcp_server/server.py"},
                {"name": "Event-sourced conformance review session (reversible typed ops, server-computed inverses, deterministic replay + undo, append-only audit trail, grounded so an instruction can only target findings the engine actually produced)", "evidence": "src/review_session.py + /review/* endpoints", "note": "The deterministic natural-language compiler runs with no keys; the watsonx NL path (below) is the optional IBM-runtime upgrade"}
            ],
            "integration": [
                {"name": "Granite Vision 3.2:2b (local Ollama)", "evidence": "src/generative_fix.py", "note": "Primary AD drafter in the local, API-deletion-proof pipeline"},
                {"name": "watsonx-hosted vision (Llama 3.2 11B)", "evidence": "src/watsonx_vision.py", "note": "Drafts the gap fix live on the HOSTED demo (no Ollama on Render), via the /demo-fix endpoint; Granite Vision is the local model"},
                {"name": "Granite Guardian 3:2b (local Ollama)", "evidence": "src/generative_fix.py"},
                {"name": "Granite Guardian 3-8b (watsonx.ai)", "evidence": "src/watsonx_guardian.py", "note": "The safety gate that actually runs on this hosted deploy, where there is no Ollama. Model id ibm/granite-guardian-3-8b; surfaced live in guardian_provenance on every gated fix."},
                {"name": "Granite Embedding (watsonx.ai)", "evidence": "src/watsonx_embedding.py", "note": "Embeds the standards corpus for citation retrieval on this hosted deploy, where the local embedding stack is absent. Model id ibm/granite-embedding-278m-multilingual, called over REST so it needs no torch. Falls back to the deterministic encoder if watsonx is unreachable."},
                {"name": "Granite Speech 3.3-2b (local transformers)", "evidence": "src/granite_speech.py", "note": "High-accuracy NER reference, opt-in ACCESSGATE_GRANITE_SPEECH=1; faster-whisper is the default reference"},
                {"name": "watsonx.ai (ibm/granite-3-8b-instruct)", "evidence": "src/watsonx_showcase.py", "note": "Hosted AD-line generation, side-by-side with the local Granite path; gracefully degrades if the key is absent"},
                {"name": "watsonx NL review compiler (ibm/granite-3-8b-instruct)", "evidence": "src/watsonx_nl.py", "note": "Compiles a plain-English review instruction to a structured intent, then re-grounds it against the report's real findings through the same deterministic selector, so the model can only ever narrow to real findings; falls back to the keyword compiler with no key"}
            ],
            "accelerator": [
                {"name": "IBM Bob custom mode (accessibility-compliance-engineer)", "evidence": ".bob/custom_modes.yaml"},
                {"name": "IBM Bob DCMP/FCC/Netflix rule-authoring skill", "evidence": ".bob/skills/conformance/SKILL.md"},
                {"name": "IBM Bob /review SARIF audit", "evidence": "security/review-audit-1.sarif"},
                {"name": "IBM Bob /review OSCAL audit", "evidence": "security/review-audit-2.oscal.json"},
                {"name": "Self-referential MCP loop (Bob consumed its own tool during dev)", "evidence": ".bob/mcp.json"}
            ]
        },
        "api_deletion_test": "Remove every hosted AI API. The engine still runs. The gap detector, caption scorer, classifier, rule evaluators, RAG citations, the SARIF/OSCAL/editor exporters, and the event-sourced review session (with its deterministic NL compiler) are all self-built and API-deletion-proof.",
        "generative_provenance": "Every generated output carries its provenance: which engine drafted it, the model id where the code holds it, the call latency, and an explicit fallback flag. A canned fallback draft or a safety screen that could not run is marked fallback and can never be accepted, so a judge always sees whether an output came from a live model or a deterministic path. Surfaced on the gated fix (draft_provenance, guardian_provenance) and in the fix panel UI.",
        "citation_provenance": _citation_provenance(),
        "demo_transparency": "Nothing in the demo is synthetic: the report is the real engine's output on the real public-domain Night of the Living Dead audio and captions, and any uploaded file is analyzed and drafted live end to end. On the hosted site the /demo-fix endpoint drafts the gated AD fix live via watsonx-hosted vision. For the recorded video's fix beat, the AD draft was pre-generated for take reliability (the local 2b vision model over-describes the short window on camera); the DCMP structure validator and the Granite Guardian safety screen still ran live on it, and the same fix drafts live on the hosted site.",
        "github": "https://github.com/StephenSook/accessgate"
    })


# ---------------------------------------------------------------------------
# Full conformance check
# ---------------------------------------------------------------------------

@app.post("/check")
async def check_conformance(
    film: UploadFile = File(...),
    captions: UploadFile = File(...),
    ad: Optional[UploadFile] = File(None),
    profile: str = Form("netflix"),
) -> JSONResponse:
    """
    Upload film + captions (+ optional AD) and run the full conformance pipeline.

    Returns ConformanceReport JSON plus a report_id for caching.
    """
    from src.engine import run_engine

    # Save uploads to temp files
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        film_path = tmp_dir / _safe_name(film.filename, "film.mp4")
        cap_path = tmp_dir / _safe_name(captions.filename, "captions.srt")

        with open(film_path, "wb") as f:
            shutil.copyfileobj(film.file, f)
        with open(cap_path, "wb") as f:
            shutil.copyfileobj(captions.file, f)

        ad_path = None
        if ad and ad.filename:
            ad_path = tmp_dir / _safe_name(ad.filename, "ad.vtt")
            with open(ad_path, "wb") as f:
                shutil.copyfileobj(ad.file, f)

        report = run_engine(
            film_path=str(film_path),
            caption_path=str(cap_path),
            ad_path=str(ad_path) if ad_path else None,
            profile=profile,
        )

        report_id = str(uuid.uuid4())
        report_dict = json.loads(report.model_dump_json())
        report_dict["report_id"] = report_id
        _report_cache[report_id] = report_dict

        return JSONResponse(content=report_dict)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Caption-only check (mobile): structural rules on a caption file, no film
# ---------------------------------------------------------------------------

@app.post("/check-captions")
async def check_captions(
    captions: UploadFile = File(...),
    profile: str = Form("netflix"),
) -> JSONResponse:
    """
    Run the conformance engine on a caption file alone (no film upload).

    Without a film, VAD gap detection and ASR accuracy scoring skip gracefully;
    the structural caption rules (DCMP line/duration/reading-speed, Netflix
    length/CPS/duration, FCC placement) still run. Built for the mobile app,
    where uploading a full video is impractical.
    """
    from src.engine import run_engine

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        cap_path = tmp_dir / _safe_name(captions.filename, "captions.srt")
        with open(cap_path, "wb") as f:
            shutil.copyfileobj(captions.file, f)
        no_film = tmp_dir / "none.mp4"
        no_film.write_bytes(b"")  # absent film -> VAD + NER skip gracefully

        report = run_engine(
            film_path=str(no_film),
            caption_path=str(cap_path),
            ad_path=None,
            profile=profile,
        )
        d = json.loads(report.model_dump_json())
        d["report_id"] = str(uuid.uuid4())
        return JSONResponse(content=d)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

@app.post("/gaps")
async def get_gaps(
    film: UploadFile = File(...),
    min_duration: float = Form(2.5),
) -> JSONResponse:
    """Detect dialogue-free gaps in a film."""
    from src.gap_engine import detect_gaps

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        film_path = tmp_dir / _safe_name(film.filename, "film.mp4")
        with open(film_path, "wb") as f:
            shutil.copyfileobj(film.file, f)

        # detect_gaps returns (gaps, speech_regions) and its keyword is min_gap.
        gaps, _speech = detect_gaps(str(film_path), min_gap=min_duration)
        return JSONResponse(content=[
            {"start": g.start, "end": g.end, "duration": g.duration,
             "max_words": g.max_words(wpm=150.0)}
            for g in gaps
        ])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Cached report retrieval
# ---------------------------------------------------------------------------

@app.get("/report/{report_id}")
def get_report(report_id: str) -> JSONResponse:
    """Retrieve a previously-generated conformance report by ID."""
    if report_id not in _report_cache:
        raise HTTPException(status_code=404, detail="Report not found.")
    return JSONResponse(content=enrich_report_dict(_report_cache[report_id]))


# ---------------------------------------------------------------------------
# Generative fix
# ---------------------------------------------------------------------------

@app.post("/fix")
async def request_fix(
    film: UploadFile = File(...),
    gap_start: float = Form(...),
    gap_end: float = Form(...),
) -> JSONResponse:
    """
    Request a gated generative AD fix for a specific gap.

    Returns FixResult: draft text, DCMP validation, Guardian screen, accepted flag.
    Also includes a watsonx_showcase field with the ibm/granite-3-8b-instruct
    hosted inference result for side-by-side comparison.
    """
    from src.generative_fix import generate_fix
    from src.models import GapRegion
    from src.watsonx_showcase import generate_ad_line

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        film_path = tmp_dir / _safe_name(film.filename, "film.mp4")
        with open(film_path, "wb") as f:
            shutil.copyfileobj(film.file, f)

        gap = GapRegion(start=gap_start, end=gap_end)
        result = generate_fix(gap=gap, film_path=str(film_path))
        result_dict = json.loads(result.model_dump_json())

        # watsonx.ai Lite showcase — runs in parallel with local Granite path
        # Uses the local Granite Vision draft as the scene description input
        scene_desc = result_dict.get("draft_text", "scene in progress")
        showcase = generate_ad_line(
            gap_start=gap_start,
            gap_end=gap_end,
            scene_description=scene_desc,
        )
        result_dict["watsonx_showcase"] = showcase

        return JSONResponse(content=result_dict)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Granite report summary — plain-English executive brief via watsonx Granite
# ---------------------------------------------------------------------------

@app.get("/demo-summary")
def demo_summary() -> JSONResponse:
    """Granite-generated plain-English summary of the demo conformance report."""
    from src.report_summary import summarize_report

    demo_path = Path(__file__).parent.parent / "data" / "demo" / "demo_report.json"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="Demo report not found.")
    with open(demo_path) as f:
        report = json.load(f)
    return JSONResponse(content=summarize_report(report))


@app.post("/summary")
async def summary(report: dict = Body(...)) -> JSONResponse:
    """Granite-generated plain-English summary of a posted conformance report."""
    from src.report_summary import summarize_report
    return JSONResponse(content=summarize_report(report))


# ---------------------------------------------------------------------------
# Demo generative fix — live watsonx vision draft from committed keyframes
# ---------------------------------------------------------------------------

@app.post("/demo-fix")
async def demo_fix(gap_start: float = Form(...), gap_end: float = Form(...)) -> JSONResponse:
    """
    Run the gated generative fix for a demo gap, live, with no file upload.

    Uses the pre-committed keyframes for the demo film (data/demo/keyframes/),
    drafts the audio description on watsonx vision, validates it against the
    DCMP structure rules live, and returns the FixResult plus the draft source.
    This lets a judge trigger the fix on the hosted demo where there is no
    Ollama and no uploaded film.
    """
    from src.generative_fix import generate_demo_fix
    from src.models import GapRegion

    kf_dir = Path(__file__).parent.parent / "data" / "demo" / "keyframes"
    bucket = int(gap_start)
    keyframes = sorted(str(p) for p in kf_dir.glob(f"gap_{bucket}_*.jpg"))
    if not keyframes:
        keyframes = sorted(str(p) for p in kf_dir.glob("*.jpg"))[:2]
    if not keyframes:
        raise HTTPException(status_code=404, detail="No demo keyframes available.")

    gap = GapRegion(start=gap_start, end=gap_end)
    result, source = generate_demo_fix(gap, keyframes)
    payload = json.loads(result.model_dump_json())
    payload["draft_source"] = source
    return JSONResponse(content=payload)


# ---------------------------------------------------------------------------
# Live caption monitoring (WebSocket)
# ---------------------------------------------------------------------------

@app.websocket("/live")
async def live_monitor(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for live caption monitoring.

    Accepts: JSON frames {"chunk_path": "...", "window_secs": 10}
    Emits:   JSON metrics {"cps": float, "wpm": float, "coverage": bool,
                           "violations": [...], "timestamp": float}

    Clients stream audio chunks; the engine scores each against Netflix/DCMP
    thresholds in near-real-time (≤3s latency target).
    """
    from src.live_monitor import LiveMonitor

    await websocket.accept()
    monitor = LiveMonitor()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            chunk_path = msg.get("chunk_path", "")
            window_secs = float(msg.get("window_secs", 10.0))

            metrics = monitor.process_chunk(chunk_path, window_secs)
            await websocket.send_text(json.dumps(metrics))
    except Exception as e:
        logger.info("WebSocket closed: %s", e)


# ---------------------------------------------------------------------------
# Conformance review session (event-sourced, natural-language drivable)
# ---------------------------------------------------------------------------
from src.review_session import ReviewSession, ReviewOp, compile_nl, GroundingError
from src.models import ConformanceReport

# In-memory review sessions (keyed by session_id), like the report cache.
_review_sessions: dict[str, ReviewSession] = {}


def _load_report_for_review(report_id: str) -> ConformanceReport:
    """Resolve a report_id to a ConformanceReport (cache, or the bundled demo)."""
    if report_id in ("demo", "notld", "demo-notld-2026"):
        demo_path = Path(__file__).parent.parent / "data" / "demo" / "demo_report.json"
        if not demo_path.exists():
            raise HTTPException(status_code=404, detail="Demo report not found.")
        return ConformanceReport(**json.loads(demo_path.read_text()))
    if report_id in _report_cache:
        return ConformanceReport(**_report_cache[report_id])
    raise HTTPException(status_code=404, detail=f"report_id '{report_id}' not found")


def _session_view(s: ReviewSession) -> dict:
    st = s.state
    summary = {"open": 0, "accepted": 0, "dismissed": 0, "flagged": 0}
    for n in st.findings.values():
        summary[n.review_status] = summary.get(n.review_status, 0) + 1
    return {
        "session_id": st.session_id,
        "report_id": st.report_id,
        "version": st.version,
        "summary": summary,
        "findings": {k: n.model_dump() for k, n in st.findings.items()},
        "fixes": st.fixes,
        "audit_log": s.audit_log(),
    }


@app.post("/review/session")
def review_create(report_id: str = Body(..., embed=True)) -> JSONResponse:
    """Open an event-sourced review session over a report (or 'demo')."""
    report = _load_report_for_review(report_id)
    s = ReviewSession(report, report_id=report_id)
    _review_sessions[s.state.session_id] = s
    return JSONResponse(content=_session_view(s))


@app.post("/review/op")
def review_op(
    session_id: str = Body(...),
    kind: str = Body(...),
    target: str = Body(...),
    payload: dict = Body(default={}),
) -> JSONResponse:
    """Apply one typed, reversible op. Grounded: a bad target is rejected 422."""
    s = _review_sessions.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="review session not found")
    try:
        s.apply(ReviewOp(kind=kind, target=target, payload=payload))  # type: ignore[arg-type]
    except GroundingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return JSONResponse(content=_session_view(s))


@app.post("/review/nl")
def review_nl(
    session_id: str = Body(...),
    phrase: str = Body(...),
    apply: bool = Body(default=True),
) -> JSONResponse:
    """Compile a plain-English instruction into grounded typed ops (watsonx/Granite
    at runtime, deterministic fallback) and optionally apply them."""
    s = _review_sessions.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="review session not found")
    result = compile_nl(phrase, s)
    applied = 0
    if apply and result.intent == "mutate":
        for op in result.ops:
            try:
                s.apply(op)
                applied += 1
            except GroundingError:
                pass  # ungrounded ops are silently skipped, never applied
    view = _session_view(s)
    view["nl"] = {
        "intent": result.intent,
        "engine": result.engine,
        "reasoning": result.reasoning,
        "matched": result.matched,
        "compiled_ops": [o.model_dump(exclude={"restore_state"}) for o in result.ops],
        "query": result.query.model_dump() if result.query else None,
        "applied": applied,
    }
    return JSONResponse(content=view)


@app.post("/review/undo")
def review_undo(session_id: str = Body(..., embed=True)) -> JSONResponse:
    """Deterministically undo the last op (its server-computed inverse)."""
    s = _review_sessions.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="review session not found")
    s.undo()
    return JSONResponse(content=_session_view(s))


@app.get("/review/{session_id}")
def review_get(session_id: str) -> JSONResponse:
    """Current review state + the full append-only audit trail."""
    s = _review_sessions.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="review session not found")
    return JSONResponse(content=_session_view(s))


# ---------------------------------------------------------------------------
# Editor-native export downloads (a file a captioner/AD writer can open + use)
# ---------------------------------------------------------------------------
from fastapi.responses import PlainTextResponse
from src.exporters.editor import export_findings_csv, export_findings_markers_vtt


@app.get("/export/{report_id}/findings.csv")
def export_findings(report_id: str) -> PlainTextResponse:
    """Findings as a triage CSV (formula-injection hardened)."""
    report = _load_report_for_review(report_id)
    return PlainTextResponse(
        content=export_findings_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{report_id}_findings.csv"'},
    )


@app.get("/export/{report_id}/markers.vtt")
def export_markers(report_id: str) -> PlainTextResponse:
    """Findings as a navigable WebVTT marker track for an editor timeline."""
    report = _load_report_for_review(report_id)
    return PlainTextResponse(
        content=export_findings_markers_vtt(report),
        media_type="text/vtt",
        headers={"Content-Disposition": f'attachment; filename="{report_id}_markers.vtt"'},
    )
