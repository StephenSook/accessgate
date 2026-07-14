"""
Parse the accessibility standards into standards/parsed/*.md with Docling.

The RAG layer (src/rag.py) picks up any markdown in standards/parsed/ and
embeds it alongside the authoritative inline corpus, so citations come from the
full source text. This wires Docling as the corpus parser (previously the
directory was empty and the claim was aspirational).

Run: python scripts/parse_standards.py
"""
from __future__ import annotations

from pathlib import Path

from docling.document_converter import DocumentConverter

OUT = Path(__file__).resolve().parent.parent / "standards" / "parsed"

# Focused standard pages (not full specs) so the corpus stays relevant.
SOURCES = {
    "wcag_122_captions": "https://www.w3.org/WAI/WCAG22/Understanding/captions-prerecorded.html",
    "wcag_125_audio_description": "https://www.w3.org/WAI/WCAG22/Understanding/audio-description-prerecorded.html",
    "fcc_79_1_caption_quality": "https://www.ecfr.gov/current/title-47/chapter-I/subchapter-B/part-79/section-79.1",
    "dcmp_captioning_key": "https://dcmp.org/learn/captioningkey",
    "dcmp_description_key": "https://dcmp.org/learn/descriptionkey",
    "netflix_ttsg_english": "https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-Timed-Text-Style-Guide",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()
    for name, url in SOURCES.items():
        try:
            md = converter.convert(url).document.export_to_markdown()
            # Trim very long specs so the corpus stays focused.
            (OUT / f"{name}.md").write_text(md[:24000], encoding="utf-8")
            print(f"OK   {name}: {min(len(md), 24000)} chars")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {name}: {e}")


if __name__ == "__main__":
    main()
