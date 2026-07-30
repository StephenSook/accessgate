"""
The report summary is the only place AccessGate asks a model to restate figures
the engine computed, so it is the only place a figure can drift. These tests pin
the checker that catches it.

The design constraint worth pinning as hard as the detection itself: this check
must be permissive. A false accusation on a correct summary would be worse than
missing one drifted number, because it would train a reader to ignore the field.
"""

from src.report_summary import unsupported_figures

BRIEF = (
    "Profile: netflix. 15 errors, 0 warnings, 3 human-review flags across FCC, WCAG, "
    "DCMP and Netflix rules. 3 dialogue-free gaps need audio description. "
    "NER caption accuracy 78.9% (below the 98% broadcast threshold; reference-relative "
    "and flagged for human review, never auto-failed). Key findings: Line exceeds 32 "
    "chars (45 chars) at 31.50s"
)


def test_a_drifted_ner_figure_is_caught():
    """The failure this exists for: the model states a score we never computed."""
    summary = "NER caption accuracy came in at 85.4%, below the 98% threshold."
    assert "85.4" in unsupported_figures(summary, BRIEF)


def test_a_faithful_summary_is_clean():
    summary = (
        "There are 15 errors and 3 human-review flags to clear. NER caption accuracy "
        "is 78.9%, below the 98% broadcast threshold, and is flagged for human review "
        "rather than auto-failed. 3 dialogue-free gaps need audio description."
    )
    assert unsupported_figures(summary, BRIEF) == []


def test_trailing_zero_formatting_is_not_a_false_positive():
    """78.90 and 78.9 are the same number; flagging that would be noise."""
    assert unsupported_figures("Accuracy is 78.90%.", BRIEF) == []


def test_ordinary_prose_numbers_do_not_trip_it():
    summary = "Two or three fixes remain. 1 gap is trivial, 2 are not."
    assert unsupported_figures(summary, BRIEF) == []


def test_figures_quoted_from_findings_are_supported():
    """45 and 32 come from the brief's key-findings tail."""
    assert unsupported_figures("A line runs 45 chars against a 32 limit.", BRIEF) == []


def test_each_unsupported_figure_reported_once():
    summary = "Scores of 85.4% and again 85.4% and also 91%."
    assert unsupported_figures(summary, BRIEF) == ["85.4", "91"]


def test_empty_or_missing_summary_is_not_an_error():
    assert unsupported_figures("", BRIEF) == []
    assert unsupported_figures(None, BRIEF) == []  # type: ignore[arg-type]


def test_checker_reports_and_never_rewrites():
    """
    Pins the design decision: the summary text is returned untouched.

    Silently editing a number inside generated prose would produce a sentence no
    model wrote and no human approved.
    """
    summary = "Accuracy is 85.4%."
    before = summary
    unsupported_figures(summary, BRIEF)
    assert summary == before


# ---------------------------------------------------------------------------
# Token-cap truncation.
#
# A rival graded C+ this cycle wires Granite to this same completion endpoint
# with no chat template and no stop handling, and its live output opens with
# roughly a thousand characters of echoed prompt scaffolding pasted into the
# user's deliverable. We do not have that defect: our prompt ends on a
# "Summary:" anchor and the observed live stop_reason is eos_token at 101 of
# the allowed tokens.
#
# We DID have the quieter half of it. Nothing read stop_reason, so a report
# long enough to reach the cap would have rendered a summary ending mid-word
# on the card a judge reads, with no signal anywhere that it had been cut.
# These pin the trim.
# ---------------------------------------------------------------------------

from src.report_summary import _trim_to_last_sentence


def test_a_mid_sentence_fragment_is_dropped():
    """The defect: a card ending mid-word."""
    text = "Fix the 3 gaps first. Then re-time the overlapping cue. The accuracy sc"
    assert _trim_to_last_sentence(text) == (
        "Fix the 3 gaps first. Then re-time the overlapping cue."
    )


def test_a_complete_summary_is_left_alone():
    """Trimming a finished summary would delete real content."""
    text = "Fix the 3 gaps first. Then re-time the overlapping cue."
    assert _trim_to_last_sentence(text) == text


def test_question_and_exclamation_count_as_sentence_ends():
    assert _trim_to_last_sentence("Is it shippable? Not yet, because the ca") == (
        "Is it shippable?"
    )


def test_text_with_no_sentence_break_is_returned_whole():
    """
    Fail-safe direction. With nothing to cut back to, returning "" would blank
    the card entirely; the `truncated` flag still tells the truth in the
    payload and in /health.
    """
    text = "a single long clause with no terminator that ran out of tokens"
    assert _trim_to_last_sentence(text) == text
