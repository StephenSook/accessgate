"""
A citation field is either true or absent. It is never invented.

WHY THIS TEST EXISTS. The sharpest defect across 149 graded rivals in this
challenge belongs to a medical anti-misinformation tool. Its citation builder
reads only one date field from the Crossref record and falls back like this:

    year: item['published-print'] ?? new Date().getFullYear()

27 of 30 real Crossref results lack `published-print`, so roughly nine in ten of
its citations are stamped with the current year. A genuine 2024 paper renders as
"Kamran (2026)". Missing authors become the literal string "Tim Peneliti"
("Research Team"); missing journals become "Jurnal Akademik". All of it sits
under a UI label reading "Validated by Crossref & PubMed", and nothing validates
anything.

The mechanism is worth naming precisely, because it is not lying, it is
CONVENIENCE. Each fallback was written to avoid rendering an empty string. The
product that results asserts facts it never had, in the one domain where a wrong
citation can hurt someone.

A second rival hardcodes a DIFFERENT project's deployment as its production API
base, so in production its own server-to-server calls leave for a domain the
authors do not own.

AccessGate does neither today. These tests are here so that stays true when
someone later reaches for a tidy default to avoid a blank field.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_REPORT = REPO_ROOT / "data" / "demo" / "demo_report.json"

#: Every host our citations are allowed to point a reader at. These are the
#: standards bodies whose text the corpus is built from. A search engine is
#: deliberately absent: "here, go look for it" is not a citation.
ALLOWED_CITATION_HOSTS = {
    "www.ecfr.gov",
    "www.w3.org",
    "dcmp.org",
    "partnerhelp.netflixstudios.com",
}

#: Strings that mean "we did not have this, so we made something up".
FABRICATION_TELLS = re.compile(
    r"google\.com/search|scholar\.google|bing\.com/search|duckduckgo\.com/\?q"
    r"|research team|unknown author|academic journal|n/?a$",
    re.I,
)


def _results() -> list[dict]:
    report = json.loads(DEMO_REPORT.read_text())
    return report.get("results", [])


def test_the_fixture_is_not_vacuous():
    """
    Guard the guard.

    Every assertion below iterates the committed demo report. If that report
    ever loses its citations, each test would pass over an empty sequence and
    protect nothing while still reporting green.
    """
    results = _results()
    assert len(results) >= 20, f"demo report has only {len(results)} results"
    cited = [r for r in results if r.get("citation")]
    assert len(cited) >= 20, f"only {len(cited)} results carry a citation"
    assert any(r.get("clause_url") for r in cited), "no clause_url anywhere"


def test_no_citation_points_at_a_search_engine():
    """
    The rival's citation link is a Google Scholar query built from the title.

    It is styled and labelled exactly like a DOI link, so a reader cannot tell
    that the product never resolved a source at all.
    """
    offenders = []
    for r in _results():
        url = r.get("clause_url")
        if url and FABRICATION_TELLS.search(url):
            offenders.append(f"{r.get('rule_id')}: {url}")
    assert offenders == [], (
        "a citation URL is a search query rather than a source:\n  "
        + "\n  ".join(offenders)
    )


def test_every_citation_url_points_at_a_standards_body():
    """A citation must resolve to the document it claims to quote."""
    from urllib.parse import urlparse

    offenders = []
    for r in _results():
        url = r.get("clause_url")
        if not url:
            continue
        host = urlparse(url).netloc
        if host not in ALLOWED_CITATION_HOSTS:
            offenders.append(f"{r.get('rule_id')}: {host}")
    assert offenders == [], (
        "citation host is not a standards body this corpus is built from: "
        f"{offenders}. If a new standard was added, add its host to "
        "ALLOWED_CITATION_HOSTS deliberately rather than widening the check."
    )


def test_no_citation_field_carries_a_fabricated_placeholder():
    """
    Missing authors becoming "Research Team" is the same defect as a missing
    date becoming this year. Both replace an absence with an assertion.
    """
    offenders = []
    for r in _results():
        for field in ("citation", "clause_id", "clause_url"):
            value = r.get(field)
            if isinstance(value, str) and FABRICATION_TELLS.search(value):
                offenders.append(f"{r.get('rule_id')}.{field}: {value[:60]}")
    assert offenders == [], "placeholder text in a citation field: " + str(offenders)


def test_absent_measurements_are_null_rather_than_defaulted():
    """
    The rule that most directly prevents the rival's defect.

    A rule with nothing to measure must report None, not 0, not "", not a
    neutral-looking constant. A zero renders as a measurement; a null renders as
    an absence, and only one of those is true.
    """
    offenders = []
    for r in _results():
        # A measurement is only meaningful alongside the limit it was compared
        # against. Having one without the other means a number was invented to
        # fill a column.
        measured, limit = r.get("measured"), r.get("limit")
        if measured is not None and limit is None:
            offenders.append(f"{r.get('rule_id')}: measured={measured} with no limit")
        if r.get("delta_pct") is not None and measured is None:
            offenders.append(
                f"{r.get('rule_id')}: delta_pct without a measurement to derive it from"
            )
    assert offenders == [], "\n  ".join(offenders)


def test_the_production_api_base_names_no_foreign_domain():
    """
    A rival hardcodes a DIFFERENT project's vercel.app deployment as its
    production API base, so unset config sends its production traffic to a host
    its authors do not own.

    Ours resolves from VITE_API_URL and falls back to a same-origin relative
    path. This pins that: no absolute URL may be the default.
    """
    client = (REPO_ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    match = re.search(r"const BASE\s*=\s*([^\n]+)", client)
    assert match, "could not find the BASE constant; update this test"
    expression = match.group(1)

    urls = re.findall(r"https?://[^\s'\"`]+", expression)
    assert urls == [], (
        f"the production API base defaults to an absolute URL: {urls}. "
        "It must fall back to a relative path so a missing VITE_API_URL cannot "
        "silently send traffic to someone else's host."
    )
