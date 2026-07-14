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
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AccessGate",
    description="Film accessibility conformance pre-check engine.",
    version="1.0.0",
)

# CORS: allow the Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory report cache (keyed by report_id)
_report_cache: dict[str, dict] = {}


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
    import json as _json
    with open(demo_path) as f:
        return JSONResponse(content=_json.load(f))


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
        "tiers": {
            "wired_live": [
                {"name": "23-rule evaluator engine", "evidence": "src/evaluators/", "test_count": 172},
                {"name": "Silero VAD gap detection", "evidence": "src/gap_engine.py"},
                {"name": "NER-style caption scorer", "evidence": "src/ner_scorer.py", "note": "Never auto-fails on ASR alone — Koenecke et al. PNAS 2020"},
                {"name": "Caption error-type classifier", "evidence": "data/training/classifier.pkl", "f1": 0.952},
                {"name": "RAG citation engine (Granite Embedding r2)", "evidence": "src/rag.py"},
                {"name": "SARIF 2.1.0 exporter", "evidence": "src/exporters/sarif.py"},
                {"name": "OSCAL POA&M v1.1.2 exporter", "evidence": "src/exporters/oscal.py"},
                {"name": "MCP server (self-referential loop)", "evidence": "src/mcp_server/server.py"}
            ],
            "integration": [
                {"name": "Granite Vision 3.2:2b (local Ollama)", "evidence": "src/generative_fix.py", "note": "Local, not hosted — requires Ollama"},
                {"name": "Granite Guardian 3:2b (local Ollama)", "evidence": "src/generative_fix.py"},
                {"name": "Granite Speech 3.3-2b (local transformers)", "evidence": "src/granite_speech.py", "note": "High-accuracy NER reference, opt-in ACCESSGATE_GRANITE_SPEECH=1; faster-whisper is the default reference"},
                {"name": "watsonx.ai (ibm/granite-3-8b-instruct)", "evidence": "src/watsonx_showcase.py", "note": "Hosted AD-line generation, side-by-side with the local Granite path; gracefully degrades if the key is absent"}
            ],
            "accelerator": [
                {"name": "IBM Bob custom mode (accessibility-compliance-engineer)", "evidence": ".bob/custom_modes.yaml"},
                {"name": "IBM Bob DCMP/FCC/Netflix rule-authoring skill", "evidence": ".bob/skills/conformance/SKILL.md"},
                {"name": "IBM Bob /review SARIF audit", "evidence": "security/review-audit-1.sarif"},
                {"name": "IBM Bob /review OSCAL audit", "evidence": "security/review-audit-2.oscal.json"},
                {"name": "Self-referential MCP loop (Bob consumed its own tool during dev)", "evidence": ".bob/mcp.json"}
            ]
        },
        "api_deletion_test": "Remove every hosted AI API. The engine still runs. The gap detector, caption scorer, classifier, rule evaluators, RAG citations, and SARIF/OSCAL exporters are all self-built and API-deletion-proof.",
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
        film_path = tmp_dir / film.filename
        cap_path = tmp_dir / captions.filename

        with open(film_path, "wb") as f:
            shutil.copyfileobj(film.file, f)
        with open(cap_path, "wb") as f:
            shutil.copyfileobj(captions.file, f)

        ad_path = None
        if ad and ad.filename:
            ad_path = tmp_dir / ad.filename
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
        film_path = tmp_dir / film.filename
        with open(film_path, "wb") as f:
            shutil.copyfileobj(film.file, f)

        gaps = detect_gaps(str(film_path), min_gap_duration=min_duration)
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
    return JSONResponse(content=_report_cache[report_id])


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
        film_path = tmp_dir / film.filename
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
