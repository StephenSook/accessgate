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
from collections import OrderedDict
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

# In-memory caches, bounded.
#
# These are plain process memory with no eviction policy in the original design,
# so across an unattended judging window every uploaded report and every review
# session accumulated for the life of the instance, and a review session's op log
# only ever grows. Free-tier spin-down "solved" that by throwing everything away,
# which is the wrong cure: it means a judge's report_id stops resolving mid
# session and their export links 404. Bounded FIFO keeps recent work available
# and puts a ceiling on growth.
_CACHE_LIMIT = 50


def _remember(cache: "OrderedDict", key: str, value) -> None:
    """Insert into a bounded FIFO cache, evicting the oldest entries."""
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _CACHE_LIMIT:
        cache.popitem(last=False)


_report_cache: "OrderedDict[str, dict]" = OrderedDict()




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
        from src.rag import _read_index_meta, encoder_id, loaded_encoder
        return {
            "active": encoder_id(),
            # The vectors actually in memory. index_meta.json only records
            # whichever build ran last, and the repo ships one vector file per
            # encoder, so this is the honest answer to "what served this".
            "serving": loaded_encoder(),
            "index_built_with": _read_index_meta().get("encoder"),
            "note": "Prebuilt vectors ship for both encoders, so nothing re-embeds at request time: Granite Embedding r2 on a local install, watsonx-hosted Granite on this deploy. `serving` is the set actually in memory answering your citations; `active` is what this process would use for a query. A deterministic encoder remains the last resort so citations survive with every hosted API deleted.",
        }
    except Exception as exc:  # noqa: BLE001
        # Never let a transparency field take down the transparency page.
        return {"active": None, "error": str(exc)}


def _safe_name(filename: Optional[str], default: str) -> str:
    """Basename of an uploaded filename, preventing path traversal (../, /)."""
    name = Path(filename or "").name
    return name or default


#: Caption and audio-description sidecars the parser can actually read.
_CAPTION_SUFFIXES = {".srt", ".vtt"}
#: Upload ceilings. Without these one oversized POST fills the instance's
#: ephemeral disk and every later request fails on write for the life of the box.
_MAX_MEDIA_BYTES = 200 * 1024 * 1024
_MAX_SIDECAR_BYTES = 5 * 1024 * 1024


def _reject_oversized(upload: UploadFile, limit: int, label: str) -> None:
    size = getattr(upload, "size", None)
    if size is not None and size > limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{label} is {size / 1_048_576:.1f} MB, over the "
                f"{limit // 1_048_576} MB limit for this endpoint."
            ),
        )


def _reject_unsupported_caption(upload: UploadFile, label: str) -> None:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in _CAPTION_SUFFIXES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{label} has extension {suffix or '(none)'}, which this engine cannot parse. "
                f"Supported: {', '.join(sorted(_CAPTION_SUFFIXES))}."
            ),
        )


def _engine_http_error(exc: Exception, what: str) -> HTTPException:
    """Turn an engine or parser exception into an answer a human can act on.

    These endpoints used to run the pipeline with no `except` at all, so a
    malformed .srt, an unsupported extension, or a missing ffmpeg on the
    instance surfaced to the judge as a bare `500` with no body. The frontend
    then rendered the literal string "/check failed: 500". Anyone uploading
    their own file, which the UI explicitly invites, concluded the engine was
    broken rather than that their file was.
    """
    if isinstance(exc, HTTPException):
        return exc

    # Parser-layer failures are a bad FILE, not a broken server, so they are 422.
    # The subtitle libraries raise their own exception types rather than
    # ValueError (pysubs2.FormatAutodetectionError on an empty or unrecognisable
    # file, webvtt's MalformedFileError), so matching on the defining module
    # catches them without having to import and enumerate each one.
    origin = type(exc).__module__.split(".")[0]
    if isinstance(exc, (ValueError, IndexError, KeyError)) or origin in {"pysubs2", "webvtt"}:
        return HTTPException(
            status_code=422,
            detail=f"Could not parse {what}: {exc}",
        )
    if isinstance(exc, (FileNotFoundError, RuntimeError, OSError)):
        return HTTPException(
            status_code=503,
            detail=(
                f"Media analysis is unavailable on this instance ({exc}). "
                f"Caption-only checks still work: use /check-captions."
            ),
        )
    logger.exception("Unhandled error while processing %s", what)
    return HTTPException(status_code=500, detail=f"Unexpected error processing {what}.")


# ---------------------------------------------------------------------------
# API index
# ---------------------------------------------------------------------------

@app.get("/")
def api_index() -> JSONResponse:
    """Human-readable index of the API.

    The README lists this host as "REST API", so it is a link a judge clicks.
    FastAPI has no root route by default, so that click used to return a bare
    {"detail":"Not Found"}, which reads as a broken deployment rather than as
    an API with no landing page. Point them at the things worth opening.
    """
    return JSONResponse(content={
        "service": "AccessGate",
        "what": "Film accessibility conformance pre-check: caption and audio-description "
                "sidecars scored against 23 coded rules from FCC 47 CFR 79.1(j)(2), "
                "WCAG 2.2, the DCMP Captioning and Description Keys, and the Netflix "
                "Timed Text Style Guide.",
        "start_here": {
            "web_app": "https://accessgate-web.vercel.app",
            "transparency": "/judges",
            "demo_report": "/demo",
            "source": "https://github.com/StephenSook/accessgate",
        },
        "endpoints": {
            "GET  /health": "liveness",
            "GET  /demo": "the precomputed conformance report for the demo film",
            "GET  /demo-summary": "plain-English executive summary via watsonx Granite",
            "POST /demo-fix": "the gated generative fix on a demo gap (form: gap_start, gap_end)",
            "GET  /judges": "what is wired, what is not, and which model served what",
            "POST /check": "full check (multipart: film, captions, optional ad)",
            "POST /check-captions": "caption-only check (multipart: captions)",
            "POST /gaps": "dialogue-free gap detection (multipart: film)",
            "GET  /report/{id}": "retrieve a cached report",
            "POST /review/session|op|nl|undo": "event-sourced conformance review",
            "GET  /export/{id}/findings.csv|markers.vtt": "editor-native exports",
        },
        "docs": "https://github.com/StephenSook/accessgate#readme",
    })


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """
    Liveness, plus a straight answer about which subsystems are actually working.

    A judge arriving during the judging window should not have to run the gated
    fix and read a provenance field out of the response to find out whether the
    generative layer is live on this deployment. One GET answers it.

    This endpoint makes NO outbound calls, deliberately. It is pinged by the CI
    keepalive and again on every cold start, and on 2026-07-27 a metered call on
    a startup path drained a month of watsonx quota in under a day because the
    real multiplier is the restart rate, not the traffic rate. So `subsystems`
    reports what real traffic has already observed, and `configured` reports
    only what the process can see about itself for free. Neither costs a token.

    `configured` is not a health claim. Credentials being present says nothing
    about whether the far end answers; that is what `subsystems` is for, and an
    unexercised subsystem reports `not_observed` rather than a cheerful default.
    """
    from src.subsystem_status import snapshot

    demo_mode = os.getenv("ACCESSGATE_DEMO_MODE", "false").lower() == "true"
    return {
        "status": "ok",
        "service": "AccessGate",
        "demo_mode": demo_mode,
        "subsystems": snapshot(),
        "configured": {
            # Presence of credentials only. Says nothing about the far end.
            "watsonx_credentials": bool(
                os.getenv("WATSONX_API_KEY") and os.getenv("WATSONX_PROJECT")
            ),
        },
        "citations": _citation_provenance(),
        "note": "`subsystems` reports the last REAL call this instance made, never a probe: "
                "this endpoint spends no tokens. `not_observed` means nothing has exercised "
                "that path on this instance yet, which is the honest state after a cold start "
                "and is not a failure. Exercise the gated fix, then re-read this.",
    }


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

# The engine's build trace, transcribed from this repo's own git history so a
# judge can re-derive it rather than trust it:
#   git log --reverse --format='%ad %s' --date=format:'%H:%M'
# These eight commits are the window in which the engine core was authored
# through IBM Bob on 2026-07-13. Bob credits ran out later the same day, which
# is why commits after this window shift to deployment and refinement done with
# other tooling. Kept as data, not prose, so it stays checkable line by line.
_BOB_BUILD_TRACE = [
    {"time_et": "19:40", "commit": "539905e", "tests": None,
     "subject": "repo foundation, Bob artifacts, rule registry, README, AGENTS.md"},
    {"time_et": "19:53", "commit": "d825caf", "tests": 6,
     "subject": "data models, rule registry loader"},
    {"time_et": "19:57", "commit": "c08b279", "tests": 9,
     "subject": "caption parser (SRT+VTT)"},
    {"time_et": "19:58", "commit": "2bb704e", "tests": 22,
     "subject": "VAD gap engine + NER scorer"},
    {"time_et": "20:09", "commit": "14c1b7f", "tests": 108,
     "subject": "all 23 rule evaluators, degradation recipe verified"},
    {"time_et": "20:23", "commit": "afda272", "tests": 108,
     "subject": "trained caption error-type classifier, macro-F1 0.952"},
    {"time_et": "20:34", "commit": "69d24f9", "tests": 154,
     "subject": "RAG layer (Granite Embedding), main engine, SARIF/OSCAL exporters"},
    {"time_et": "20:40", "commit": "df1a5df", "tests": 172,
     "subject": "generative fix loop (Vision+DCMP+Guardian), MCP server, FastAPI"},
]


def _bob_usage() -> dict:
    """What IBM Bob actually did, separated from what only the config implies."""
    return {
        "role": (
            "Primary development tool, not exclusive. Bob authored the conformance "
            "engine, the test suite, and the React frontend. Deployment, the Granite "
            "Speech wiring, and later honesty and UI refinements were finished with "
            "other tooling after Bob credits ran out on 2026-07-13. The July rules "
            "require Bob as primary, not exclusive, so this is the honest and "
            "compliant claim."
        ),
        "build_trace": {
            "note": (
                "The engine core, from first model to a running FastAPI service with "
                "a generative fix loop, in eight commits over 47 minutes on "
                "2026-07-13. Test counts are carried in the commit subjects "
                "themselves, so this is re-derivable from a clone with: "
                "git log --reverse --format='%ad %s' --date=format:'%H:%M'"
            ),
            "window_et": "2026-07-13 19:40 to 20:40",
            "commits_that_day": 37,
            "commits": _BOB_BUILD_TRACE,
        },
        "artifacts_in_repo": [
            {"what": "Custom mode (accessibility-compliance-engineer)", "where": ".bob/custom_modes.yaml"},
            {"what": "Conformance rule-authoring skill", "where": ".bob/skills/conformance/SKILL.md"},
            {"what": "/review audit 1, SARIF, tool.driver.name is 'IBM Bob'", "where": "security/review-audit-1.sarif"},
            {"what": "/review audit 2, OSCAL POA&M", "where": "security/review-audit-2.oscal.json"},
            {"what": "Self-referential MCP config, three tools pre-authorised", "where": ".bob/mcp.json"},
            {"what": "Bob admin subscription screenshot", "where": "bob_sessions/bob-subscription-usage.png"},
        ],
        "session_usage": {
            "note": (
                "Read from the Bob IDE's local session store by "
                "scripts/export_bob_evidence.py and committed as "
                "bob_sessions/bob-usage-evidence.json. Tool-result messages are the "
                "load-bearing number: those are Bob reading and writing files in this "
                "repo, not conversation."
            ),
            "bob_tasks_in_workspace": 11,
            "tasks_matching_accessgate": 5,
            "messages_total": 645,
            "messages_by_role": {"assistant": 180, "tool": 441, "user": 24},
            "input_tokens": 30620038,
            "output_tokens": 186225,
            "tracked_cost_usd": 77.02,
        },
        "not_in_repo": (
            "Bob session MESSAGE BODIES, withheld on purpose. The transcripts carry "
            "the author's verbatim planning prompts, which are strategy notes rather "
            "than engineering artifacts and do not belong in a public repo, so only "
            "the aggregate above is published. An earlier version of this endpoint "
            "said no export was possible because Bob kept history server-side; that "
            "was wrong, the store is local at ~/.bob/db/bob.db and the earlier check "
            "missed it."
        ),
    }


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
                {"name": "Two-tier speech/gap detection (Silero VAD, then a pure-stdlib RMS energy detector)", "evidence": "src/gap_engine.py", "note": "Silero is attempted first. With the dependency set this repo actually ships (torchaudio >= 2.9 without torchcodec), Silero declines to load and the RMS energy detector is what produces the shipped demo's 197 speech regions and 3 dialogue-free gaps. That fallback is pure stdlib (wave, struct, math), which is why gap detection survives the API-deletion test. The switch is logged, not silent."},
                {"name": "NER-style caption scorer", "evidence": "src/ner_scorer.py", "note": "Never auto-fails on ASR alone (Koenecke et al. PNAS 2020)"},
                {"name": "Caption error-type classifier (recognition vs edition)", "evidence": "src/ner_scorer.py (_classify_error, phonetic heuristic)", "note": "The live NER path classifies with a phonetic heuristic (jellyfish). A trained sklearn model (macro-F1 0.952 on a synthetic weak-labeled held-out set) is a separate, documented, reproducible artifact (see data/training/model_card.md), not the runtime classifier."},
                {"name": "RAG citation engine", "evidence": "src/rag.py", "note": "No model is ever asked whether a citation is correct. The quoted text is retrieved from the standard's own document, so the clause a finding cites can be checked against the linked source rather than trusted. The distinction matters: asking a model to confirm its own output is not verification, and a citation assembled from model recall is not a citation. Citations are retrieved at runtime rather than mapped rule-to-string. The corpus is the six Docling-parsed standard pages (210 of 222 chunks) plus committed short-form clause text for the same six standards (12 chunks, src/rag.py _INLINE_STANDARDS). The repo ships one PREBUILT vector set per encoder, so no environment re-embeds at request time: a local install loads Granite Embedding r2 vectors, this hosted deploy loads watsonx-hosted Granite vectors (ibm/granite-embedding-278m-multilingual). See citation_provenance.serving below for the set actually answering right now. A metered encoder is never permitted to re-embed the corpus at request time; doing that on every cold start exhausted a month of token quota in a day on 2026-07-27, which is why index building is a deliberate offline step."},
                {"name": "SARIF 2.1.0 exporter", "evidence": "src/exporters/sarif.py"},
                {"name": "OSCAL POA&M v1.1.2 exporter", "evidence": "src/exporters/oscal.py"},
                {"name": "Editor-native exports (findings CSV, WebVTT markers)", "evidence": "src/exporters/editor.py", "note": "A file a captioner can open and use, not just a compliance document; the CSV is formula-injection hardened. Example artifacts: data/demo/editor_exports/. SCOPE: the same module carries export_ad_descriptions_vtt, which writes gate-passing AD drafts as a WebVTT descriptions track. It is unit-tested but NO shipped surface calls it, because accepted draft text is not retained server-side (the review session stores only accepted/rejected per gap). It is a library function, not a product output, and is not counted as wired."},
                {"name": "MCP server (self-referential loop)", "evidence": "src/mcp_server/server.py"},
                {"name": "Event-sourced conformance review session (reversible typed ops, server-computed inverses, deterministic replay + undo, append-only audit trail, grounded so an instruction can only target findings the engine actually produced)", "evidence": "src/review_session.py + /review/* endpoints", "note": "The deterministic natural-language compiler runs with no keys; the watsonx NL path (below) is the optional IBM-runtime upgrade"}
            ],
            "integration": [
                {"name": "Granite Vision 3.2:2b (local Ollama)", "evidence": "src/generative_fix.py", "note": "Primary AD drafter in the local, API-deletion-proof pipeline"},
                {"name": "watsonx-hosted vision (Llama 3.2 11B)", "evidence": "src/watsonx_vision.py", "note": "Drafts the gap fix live on the HOSTED demo (no Ollama on Render), via the /demo-fix endpoint; Granite Vision is the local model"},
                {"name": "Granite Guardian 3:2b (local Ollama)", "evidence": "src/generative_fix.py"},
                {"name": "Granite Guardian 3-8b (watsonx.ai)", "evidence": "src/watsonx_guardian.py", "note": "The safety gate that actually runs on this hosted deploy, where there is no Ollama. Model id ibm/granite-guardian-3-8b; surfaced live in guardian_provenance on every gated fix."},
                {"name": "Granite Embedding (watsonx.ai)", "evidence": "src/watsonx_embedding.py", "note": "Model id ibm/granite-embedding-278m-multilingual over REST, needing no torch. Its vectors are what this hosted deploy retrieves citations with: built offline behind ACCESSGATE_ALLOW_HOSTED_REINDEX=1 and committed, so the deploy gets Granite embeddings with zero embedding calls at request time. Per-cold-start re-embedding is blocked on purpose; it exhausted a month of quota in a day on 2026-07-27."},
                {"name": "Granite Speech 3.3-2b (local transformers)", "evidence": "src/granite_speech.py", "note": "High-accuracy NER reference, opt-in ACCESSGATE_GRANITE_SPEECH=1; faster-whisper is the default reference"},
                {"name": "watsonx.ai (ibm/granite-3-8b-instruct)", "evidence": "src/watsonx_showcase.py", "note": "Hosted AD-line generation, side-by-side with the local Granite path; gracefully degrades if the key is absent"},
                {"name": "watsonx NL review compiler (ibm/granite-3-8b-instruct)", "evidence": "src/watsonx_nl.py", "note": "Compiles a plain-English review instruction to a structured intent, then re-grounds it against the report's real findings through the same deterministic selector, so the model can only ever narrow to real findings; falls back to the keyword compiler with no key"}
            ],
            "accelerator": [
                {"name": "IBM Bob custom mode (accessibility-compliance-engineer)", "evidence": ".bob/custom_modes.yaml"},
                {"name": "IBM Bob DCMP/FCC/Netflix rule-authoring skill", "evidence": ".bob/skills/conformance/SKILL.md"},
                {"name": "IBM Bob /review SARIF audit", "evidence": "security/review-audit-1.sarif"},
                {"name": "IBM Bob /review OSCAL audit", "evidence": "security/review-audit-2.oscal.json"},
                {"name": "Self-referential MCP wiring (AccessGate's own engine registered to Bob)", "evidence": ".bob/mcp.json + src/mcp_server/server.py", "note": "All three tools (check_conformance, detect_gaps, score_captions) are pre-authorised in alwaysAllow, so the tool that built the engine can call the engine. Both the config and the server are in this repo. What is NOT here is a transcript of Bob invoking them: the message bodies are withheld on purpose (they are the author's planning prompts), and a search of the session data found every mention of those tool names to be Bob READING a spec file that documents them, never a call. Treat this as a wired capability, not a logged event."}
            ]
        },
        "bob_usage": _bob_usage(),
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
def check_conformance(
    film: UploadFile = File(...),
    captions: UploadFile = File(...),
    ad: Optional[UploadFile] = File(None),
    profile: str = Form("netflix"),
) -> JSONResponse:
    """
    Upload film + captions (+ optional AD) and run the full conformance pipeline.

    Returns ConformanceReport JSON plus a report_id for caching.

    Deliberately `def`, not `async def`. The body is entirely synchronous and
    slow: ffmpeg, VAD, whisper, and an index build behind a lock. FastAPI awaits
    an `async def` handler directly on the single event loop this instance runs,
    so declaring it async would block every other request, including the
    `/health` probe Render uses to decide whether to restart the service. As a
    plain `def` it runs in the threadpool instead.
    """
    from src.engine import run_engine

    _reject_oversized(film, _MAX_MEDIA_BYTES, "film")
    _reject_oversized(captions, _MAX_SIDECAR_BYTES, "caption file")
    _reject_unsupported_caption(captions, "caption file")
    if ad and ad.filename:
        _reject_oversized(ad, _MAX_SIDECAR_BYTES, "audio-description file")
        _reject_unsupported_caption(ad, "audio-description file")

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

        try:
            report = run_engine(
                film_path=str(film_path),
                caption_path=str(cap_path),
                ad_path=str(ad_path) if ad_path else None,
                profile=profile,
            )
        except Exception as exc:  # noqa: BLE001 - mapped to a real status below
            raise _engine_http_error(exc, f"{captions.filename or 'the caption file'}") from exc

        report_id = str(uuid.uuid4())
        report_dict = json.loads(report.model_dump_json())
        report_dict["report_id"] = report_id
        _remember(_report_cache, report_id, report_dict)

        # Same enrichment the /demo and /report paths apply. Previously the live
        # response was the only one served raw, so a judge comparing a live check
        # against the demo saw two different shapes for the same engine.
        return JSONResponse(content=enrich_report_dict(report_dict))

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Caption-only check (mobile): structural rules on a caption file, no film
# ---------------------------------------------------------------------------

@app.post("/check-captions")
def check_captions(
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

    _reject_oversized(captions, _MAX_SIDECAR_BYTES, "caption file")
    _reject_unsupported_caption(captions, "caption file")

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        cap_path = tmp_dir / _safe_name(captions.filename, "captions.srt")
        with open(cap_path, "wb") as f:
            shutil.copyfileobj(captions.file, f)
        no_film = tmp_dir / "none.mp4"
        no_film.write_bytes(b"")  # absent film -> VAD + NER skip gracefully

        try:
            report = run_engine(
                film_path=str(no_film),
                caption_path=str(cap_path),
                ad_path=None,
                profile=profile,
            )
        except Exception as exc:  # noqa: BLE001 - mapped to a real status below
            raise _engine_http_error(exc, captions.filename or "the caption file") from exc

        d = json.loads(report.model_dump_json())
        report_id = str(uuid.uuid4())
        d["report_id"] = report_id
        # Cache it like /check does. Without this the id handed to the client
        # never resolves, so /report/{id} and the CSV/VTT export links 404.
        _remember(_report_cache, report_id, d)
        return JSONResponse(content=d)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

@app.post("/gaps")
def get_gaps(
    film: UploadFile = File(...),
    min_duration: float = Form(2.5),
) -> JSONResponse:
    """Detect dialogue-free gaps in a film."""
    from src.gap_engine import detect_gaps

    _reject_oversized(film, _MAX_MEDIA_BYTES, "film")
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        film_path = tmp_dir / _safe_name(film.filename, "film.mp4")
        with open(film_path, "wb") as f:
            shutil.copyfileobj(film.file, f)

        # detect_gaps returns (gaps, speech_regions) and its keyword is min_gap.
        # This needs ffmpeg and the audio stack, neither of which is installed on
        # the hosted free tier, so an unguarded call here returned a bare 500 even
        # for a perfectly valid WAV.
        try:
            gaps, _speech = detect_gaps(str(film_path), min_gap=min_duration)
        except Exception as exc:  # noqa: BLE001 - mapped to a real status below
            raise _engine_http_error(exc, film.filename or "the media file") from exc
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
def request_fix(
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
        result = generate_fix(gap=gap, film_path=str(film_path), work_dir=tmp_dir)
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
    return JSONResponse(content=_summarize_and_record(summarize_report(report)))


@app.post("/summary")
def summary(report: dict = Body(...)) -> JSONResponse:
    """Granite-generated plain-English summary of a posted conformance report."""
    from src.report_summary import summarize_report
    return JSONResponse(content=_summarize_and_record(summarize_report(report)))


def _summarize_and_record(result: dict) -> dict:
    """
    Pass a summary result through untouched, recording what it revealed.

    The observation is taken from the result the caller is already getting, so
    this cannot disagree with what the judge sees, and it costs no extra call.
    """
    from src.subsystem_status import record

    err = result.get("error")
    # Truncation is not a subsystem failure: Granite ran and answered. It is a
    # quality caveat about the answer, so it rides in `detail` rather than
    # flipping the state to failed, which would itself be an inaccurate claim.
    detail = str(err) if err else None
    if not err and result.get("truncated"):
        detail = "output reached the token cap; trimmed to the last complete sentence"
    record(
        "report_summary",
        ok=not err and bool(result.get("summary")),
        model_id=result.get("model_id"),
        detail=detail,
    )
    return result


# ---------------------------------------------------------------------------
# Demo generative fix — live watsonx vision draft from committed keyframes
# ---------------------------------------------------------------------------

@app.post("/demo-fix")
def demo_fix(gap_start: float = Form(...), gap_end: float = Form(...)) -> JSONResponse:
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
    _record_fix_observations(result)
    return JSONResponse(content=payload)


def _record_fix_observations(result: "FixResult") -> None:
    """
    Record what the gated fix just proved about the drafter and the Guardian.

    Read straight off the Provenance the fix already returns, so /health can
    never claim something the response itself contradicts. A fallback draft is
    recorded as `failed`, because a canned string standing in for a live model
    is exactly the condition a judge is trying to detect, and calling it ok is
    the fabricated-provenance bug this batch caught in a rival's live demo.
    """
    from src.subsystem_status import record

    draft = result.draft_provenance
    if draft is not None:
        record(
            "vision_drafter",
            ok=not draft.fallback,
            model_id=draft.model_id,
            latency_ms=draft.latency_ms,
            detail=draft.label,
        )

    guard = result.guardian_provenance
    if guard is not None:
        # guardian_ran is the load-bearing flag: a screen that could not run
        # must never read as a screen that passed.
        record(
            "guardian",
            ok=bool(result.guardian_ran) and not guard.fallback,
            model_id=guard.model_id,
            latency_ms=guard.latency_ms,
            detail=guard.label if result.guardian_ran else "did not run",
        )


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
_review_sessions: "OrderedDict[str, ReviewSession]" = OrderedDict()


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
    _remember(_review_sessions, s.state.session_id, s)
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
