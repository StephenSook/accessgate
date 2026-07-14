"""
AccessGate main engine.

CLI: python -m src.engine <film_path> <caption_path> [ad_path]
         [--profile netflix|dcmp|fcc]
         [--output-dir ./outputs]
         [--rebuild-index]

Runs all 23 rule evaluators, populates citations from the RAG layer,
and writes JSON + SARIF + OSCAL outputs.

API-deletion test: with all hosted AI APIs removed, this still produces
a complete conformance report (VAD uses Silero + CPU; citations use the
local numpy cosine index; classifier uses saved sklearn weights).
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from pathlib import Path

from src.models import ConformanceReport, NERScoreResult, RuleResult
from src.registry import get_rule, all_rules
from src.caption_parser import parse_captions
from src.gap_engine import detect_gaps, detect_speech_regions
from src.ner_scorer import score_captions
from src.rag import retrieve_citation, build_index
from src.evaluators.fcc import (
    eval_fcc_acc_01, eval_fcc_syn_01, eval_fcc_cmp_01, eval_fcc_plc_01,
)
from src.evaluators.wcag import (
    eval_wcag_122_01, eval_wcag_125_01, eval_wcag_125_02,
)
from src.evaluators.dcmp_caption import (
    eval_dcmp_cap_01, eval_dcmp_cap_02, eval_dcmp_cap_03,
    eval_dcmp_cap_04, eval_dcmp_cap_05, eval_dcmp_cap_06,
)
from src.evaluators.dcmp_desc import (
    eval_dcmp_desc_01, eval_dcmp_desc_02, eval_dcmp_desc_03,
    eval_dcmp_desc_04, eval_dcmp_desc_05, eval_dcmp_desc_06, eval_dcmp_desc_07,
)
from src.evaluators.netflix import (
    eval_nflx_cps_01, eval_nflx_len_01, eval_nflx_dur_01,
)
from src.exporters.sarif import export_sarif
from src.exporters.oscal import export_oscal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def run_engine(
    film_path: str,
    caption_path: str,
    ad_path: str | None = None,
    profile: str = "netflix",
    rebuild_index: bool = False,
) -> ConformanceReport:
    """
    Full conformance pre-check pipeline.

    Steps:
    1. Parse captions (and AD if provided)
    2. Run VAD gap/speech detection on the film
    3. Score captions with NER scorer (if reference available)
    4. Run all 23 evaluators
    5. Populate RAG citations for every result
    6. Return ConformanceReport
    """
    # ---- Step 0: ensure RAG index is ready ----
    if rebuild_index:
        build_index(force=True)
    else:
        build_index(force=False)  # no-op if already built

    # ---- Step 1: parse captions ----
    logger.info("Parsing captions: %s", caption_path)
    cues = parse_captions(Path(caption_path))
    logger.info("Parsed %d caption cues.", len(cues))

    ad_cues = None
    if ad_path:
        logger.info("Parsing audio description: %s", ad_path)
        ad_cues = parse_captions(Path(ad_path))
        logger.info("Parsed %d AD cues.", len(ad_cues))

    # ---- Step 2: VAD gap / speech detection ----
    # detect_gaps returns (gaps, speech_regions); it extracts audio once and
    # computes both, so we unpack it rather than calling detect_speech_regions
    # separately on the raw film.
    logger.info("Running VAD on: %s", film_path)
    try:
        gaps, speech_regions = detect_gaps(film_path)
        logger.info(
            "VAD: %d speech regions, %d dialogue-free gaps.",
            len(speech_regions), len(gaps),
        )
    except Exception as e:
        logger.warning("VAD failed (%s) — structural checks only.", e)
        speech_regions = []
        gaps = []

    # ---- Step 3: NER caption scoring ----
    ner_result: NERScoreResult | None = None
    try:
        # Uses faster-whisper to generate reference transcript
        ner_result = score_captions(cues, film_path)
        logger.info(
            "NER score: %.3f (band %.3f–%.3f)",
            ner_result.ner_score, ner_result.band_low, ner_result.band_high,
        )
    except Exception as e:
        logger.warning("NER scoring failed (%s) — accuracy check will be skipped.", e)

    # ---- Step 4: Run all 23 evaluators ----
    all_results: list[RuleResult] = []
    total_dur = max((c.end for c in cues), default=0.0)

    # FCC
    all_results.append(eval_fcc_acc_01(ner_result))
    all_results.extend(eval_fcc_syn_01(cues, speech_regions))
    all_results.append(eval_fcc_cmp_01(cues, speech_regions, total_dur))
    all_results.extend(eval_fcc_plc_01(cues))

    # WCAG
    all_results.append(eval_wcag_122_01(cues))
    all_results.append(eval_wcag_125_01(ad_cues))
    all_results.append(eval_wcag_125_02(ad_cues))

    # DCMP Caption
    all_results.extend(eval_dcmp_cap_01(cues))
    all_results.extend(eval_dcmp_cap_02(cues))
    all_results.extend(eval_dcmp_cap_03(cues, profile="adult"))
    all_results.extend(eval_dcmp_cap_04(cues))
    all_results.extend(eval_dcmp_cap_05(cues))
    all_results.extend(eval_dcmp_cap_06(cues))

    # DCMP Description (only if AD is provided)
    if ad_cues:
        all_results.extend(eval_dcmp_desc_01(ad_cues))
        all_results.extend(eval_dcmp_desc_02(ad_cues))
        all_results.extend(eval_dcmp_desc_03(ad_cues))
        all_results.extend(eval_dcmp_desc_04(ad_cues, gaps))
        all_results.extend(eval_dcmp_desc_05(ad_cues, speech_regions))
        all_results.extend(eval_dcmp_desc_06(ad_cues))
        all_results.extend(eval_dcmp_desc_07(ad_cues))
    else:
        # Skip AD rules — no AD file provided
        for rule in all_rules():
            if rule.id.startswith("DCMP-DESC"):
                all_results.append(RuleResult(
                    rule_id=rule.id,
                    status="skip",
                    message="No audio description file provided.",
                    citation=rule.source,
                    sarif_level=rule.sarif_level,
                ))

    # Netflix
    all_results.extend(eval_nflx_cps_01(cues, profile="adult"))
    all_results.extend(eval_nflx_len_01(cues))
    all_results.extend(eval_nflx_dur_01(cues))

    # ---- Step 5: populate RAG citations ----
    logger.info("Retrieving citations from RAG index...")
    for result in all_results:
        # Retrieve the verbatim passage from the standard for every result. The
        # evaluator-supplied citation is a registry placeholder; the RAG layer
        # grounds it in the actual source text.
        query = f"{result.rule_id} {result.message[:80]}"
        retrieved = retrieve_citation(result.rule_id, query)
        if retrieved:
            result.citation = retrieved

    # ---- Step 6: assemble report ----
    report = ConformanceReport(
        film_path=film_path,
        caption_path=caption_path,
        ad_path=ad_path,
        profile=profile,
        results=all_results,
        ner=ner_result,
        gaps=gaps,
        speech_regions=speech_regions,
    )

    logger.info(
        "Report: %d errors, %d warnings, %d flags.",
        report.error_count, report.warning_count, report.flag_count,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AccessGate: film accessibility conformance pre-check engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  python -m src.engine data/demo/notld_segment.mp4 \\\n"
            "    data/demo/notld_broken.srt data/demo/notld_broken_ad.vtt\n"
        ),
    )
    parser.add_argument("film", help="Path to the film/video file.")
    parser.add_argument("captions", help="Path to the caption file (.srt or .vtt).")
    parser.add_argument("ad", nargs="?", default=None,
                        help="Path to the audio description file (.vtt), optional.")
    parser.add_argument("--profile", default="netflix",
                        choices=["netflix", "dcmp", "fcc"],
                        help="Conformance profile (default: netflix).")
    parser.add_argument("--output-dir", default="outputs",
                        help="Directory for JSON, SARIF, and OSCAL outputs.")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="Force rebuild of the RAG index.")

    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run engine
    report = run_engine(
        film_path=args.film,
        caption_path=args.captions,
        ad_path=args.ad,
        profile=args.profile,
        rebuild_index=args.rebuild_index,
    )

    # Write outputs
    stem = Path(args.film).stem
    json_path = output_dir / f"{stem}_report.json"
    sarif_path = output_dir / f"{stem}_report.sarif"
    oscal_path = output_dir / f"{stem}_report.oscal.json"

    json_path.write_text(report.model_dump_json(indent=2))
    export_sarif(report, sarif_path)
    export_oscal(report, oscal_path)

    logger.info("Outputs written:")
    logger.info("  JSON:  %s", json_path)
    logger.info("  SARIF: %s", sarif_path)
    logger.info("  OSCAL: %s", oscal_path)

    # Summary
    fail_count = sum(1 for r in report.results if r.status == "fail")
    flag_count = sum(1 for r in report.results if r.status == "flag")
    print(f"\n=== AccessGate Report ===")
    print(f"Profile: {report.profile}")
    print(f"Caption cues: {len(report.speech_regions)} speech regions, {len(report.gaps)} gaps")
    if report.ner:
        print(f"NER score: {report.ner.ner_score:.1%} (band {report.ner.band_low:.1%}-{report.ner.band_high:.1%})")
    print(f"Results: {fail_count} fail, {flag_count} flag")
    print(f"Outputs: {output_dir}/")

    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
