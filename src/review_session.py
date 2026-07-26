"""
Event-sourced conformance review session for AccessGate.

A conformance report is read-only. A *review* of it is a process: a QC lead
accepts some findings, dismisses others with a reason, flags borderline ones for
a human, and accepts or rejects the gated AD fixes. AccessGate models that review
as an append-only log of reversible, typed operations against the report's
findings, the same shape IMAGINE uses for its scene graph, applied to compliance:

  - every operation is TYPED and validated (a contract, not free text);
  - every operation is GROUNDED (it can only target a finding that actually
    exists in the report, so a natural-language instruction can never act on a
    hallucinated rule id or timecode);
  - every operation carries a server-computed INVERSE, so undo is deterministic;
  - the whole session REPLAYS deterministically from its log, giving a free,
    tamper-evident audit trail of who decided what and why.

Natural language compiles INTO these typed ops (compile_nl): "dismiss every
reading-speed flag after two minutes as acceptable for this title" becomes a set
of validated dismiss ops. The compile uses watsonx / Granite at runtime when a
key is present, and a deterministic keyword parser otherwise, so it runs with no
cloud credentials. Either way the compiled ops are validated and grounded before
they touch the session.

This module is additive: it consumes a ConformanceReport and never modifies the
engine, evaluators, or exporters.
"""
from __future__ import annotations

import re
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.models import ConformanceReport, RuleResult

FindingStatus = Literal["open", "accepted", "dismissed", "flagged"]
OpKind = Literal[
    "accept_finding", "dismiss_finding", "flag_finding", "annotate_finding",
    "reset_finding", "accept_fix", "reject_fix", "restore",
]


# --------------------------------------------------------------------------- #
# Addressable findings
# --------------------------------------------------------------------------- #
def finding_key(index: int) -> str:
    """Stable, addressable id for a finding: its position in report.results."""
    return f"f{index}"


class FindingNode(BaseModel):
    """A single addressable finding node + its mutable review state."""
    key: str
    rule_id: str
    status_source: str          # engine verdict: fail / flag
    level: str                  # error / warning / note
    timecode: Optional[float] = None
    message: str = ""
    review_status: FindingStatus = "open"
    note: Optional[str] = None
    reason: Optional[str] = None


class ReviewOp(BaseModel):
    """One typed, reversible operation in the review log."""
    op_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    seq: int = 0
    kind: OpKind
    target: str                             # finding key, or gap key for fixes
    payload: dict = Field(default_factory=dict)
    actor: str = "reviewer"
    source: Literal["api", "nl", "cli", "undo"] = "api"
    reversible: bool = True
    inverse_of: Optional[str] = None        # set when this op IS an inverse
    # snapshot of the target's prior state, so the inverse restores it exactly
    restore_state: Optional[dict] = None


class ReviewQuery(BaseModel):
    """A read-only filter compiled from natural language (no mutation)."""
    family: Optional[str] = None            # DCMP / FCC / WCAG / NFLX
    level: Optional[str] = None             # error / warning / note
    status: Optional[FindingStatus] = None
    after: Optional[float] = None           # timecode >= after (seconds)
    before: Optional[float] = None          # timecode <= before (seconds)


class ReviewSessionState(BaseModel):
    session_id: str
    report_id: Optional[str] = None
    version: int = 0
    findings: dict[str, FindingNode]
    fixes: dict[str, str] = Field(default_factory=dict)   # gap key -> accepted/rejected
    log: list[ReviewOp] = Field(default_factory=list)


class GroundingError(ValueError):
    """Raised when an op targets a finding/fix that is not in the report."""


# --------------------------------------------------------------------------- #
# Session engine
# --------------------------------------------------------------------------- #
_MUTATION_STATUS = {
    "accept_finding": "accepted",
    "dismiss_finding": "dismissed",
    "flag_finding": "flagged",
    "reset_finding": "open",
}


class ReviewSession:
    """An event-sourced review of one ConformanceReport."""

    def __init__(self, report: ConformanceReport, report_id: Optional[str] = None,
                 session_id: Optional[str] = None):
        findings: dict[str, FindingNode] = {}
        for i, r in enumerate(report.results):
            if r.status not in ("fail", "flag"):
                continue  # only reviewable findings (skip pass/skip)
            key = finding_key(i)
            findings[key] = FindingNode(
                key=key, rule_id=r.rule_id, status_source=r.status,
                level=r.sarif_level, timecode=r.timecode, message=r.message,
                review_status="flagged" if r.status == "flag" else "open",
            )
        self.state = ReviewSessionState(
            session_id=session_id or uuid.uuid4().hex,
            report_id=report_id, findings=findings,
        )
        # valid gap keys for fix ops: g<start rounded to 0.1s> for each report gap
        self._gap_keys = {self.gap_key(g.start) for g in report.gaps}

    @staticmethod
    def gap_key(start: float) -> str:
        return f"g{start:.1f}"

    # -- core apply / inverse / undo / replay ------------------------------- #
    def apply(self, op: ReviewOp) -> ReviewOp:
        """Validate + ground + apply one op, recording its inverse. Append-only."""
        op.seq = self.state.version + 1

        if op.kind == "restore":
            self._apply_restore(op)
        elif op.kind in _MUTATION_STATUS:
            node = self._require_finding(op.target)
            op.restore_state = {"kind": "finding", **node.model_dump()}
            node.review_status = _MUTATION_STATUS[op.kind]  # type: ignore[assignment]
            if op.kind == "dismiss_finding":
                node.reason = op.payload.get("reason")
            if op.kind == "reset_finding":
                node.reason = None
                node.note = None
        elif op.kind == "annotate_finding":
            node = self._require_finding(op.target)
            op.restore_state = {"kind": "finding", **node.model_dump()}
            node.note = op.payload.get("note")
        elif op.kind in ("accept_fix", "reject_fix"):
            self._require_fix(op.target)
            op.restore_state = {"kind": "fix", "target": op.target,
                                "prev": self.state.fixes.get(op.target)}
            self.state.fixes[op.target] = (
                "accepted" if op.kind == "accept_fix" else "rejected")
        else:  # pragma: no cover - guarded by the Literal type
            raise ValueError(f"unknown op kind: {op.kind}")

        self.state.version = op.seq
        self.state.log.append(op)
        return op

    def _apply_restore(self, op: ReviewOp) -> None:
        snap = op.restore_state or {}
        if snap.get("kind") == "finding":
            data = {k: v for k, v in snap.items() if k != "kind"}
            self.state.findings[data["key"]] = FindingNode(**data)
        elif snap.get("kind") == "fix":
            prev = snap.get("prev")
            if prev is None:
                self.state.fixes.pop(snap["target"], None)
            else:
                self.state.fixes[snap["target"]] = prev

    def undo(self) -> Optional[ReviewOp]:
        """Deterministically undo the last non-undo op by applying its inverse.

        The undo is itself appended to the log (append-only, fully auditable):
        the audit trail shows the action AND its reversal.
        """
        for op in reversed(self.state.log):
            if op.source == "undo" or op.kind == "restore":
                continue
            if op.restore_state is None:
                continue
            inverse = ReviewOp(kind="restore", target=op.target, source="undo",
                               inverse_of=op.op_id, restore_state=op.restore_state)
            return self.apply(inverse)
        return None

    @classmethod
    def replay(cls, report: ConformanceReport, log: list[ReviewOp],
               report_id: Optional[str] = None) -> "ReviewSession":
        """Rebuild a session deterministically from a report + an op log."""
        session = cls(report, report_id=report_id)
        session.state.log = []
        session.state.version = 0
        for logged in log:
            fresh = logged.model_copy(deep=True)
            fresh.seq = 0
            session.apply(fresh)
        return session

    def audit_log(self) -> list[dict]:
        """Human-readable audit trail (order preserved, inverses marked)."""
        trail = []
        for op in self.state.log:
            trail.append({
                "seq": op.seq, "kind": op.kind, "target": op.target,
                "source": op.source, "actor": op.actor,
                "payload": op.payload,
                "undo_of": op.inverse_of,
            })
        return trail

    # -- grounding helpers -------------------------------------------------- #
    def _require_finding(self, key: str) -> FindingNode:
        node = self.state.findings.get(key)
        if node is None:
            raise GroundingError(
                f"finding '{key}' is not in this report; refusing to act on a "
                f"target the engine never produced")
        return node

    def _require_fix(self, gap_key: str) -> None:
        if gap_key not in self._gap_keys:
            raise GroundingError(
                f"gap '{gap_key}' is not a real dialogue-free window in this "
                f"report; refusing an ungrounded fix decision")

    # -- queries ------------------------------------------------------------ #
    def query(self, q: ReviewQuery) -> list[FindingNode]:
        out = []
        for node in self.state.findings.values():
            if q.family and _family_of(node.rule_id) != q.family:
                continue
            if q.level and node.level != q.level:
                continue
            if q.status and node.review_status != q.status:
                continue
            if q.after is not None and (node.timecode is None or node.timecode < q.after):
                continue
            if q.before is not None and (node.timecode is None or node.timecode > q.before):
                continue
            out.append(node)
        return out


# --------------------------------------------------------------------------- #
# Rule-family helpers
# --------------------------------------------------------------------------- #
def _family_of(rule_id: str) -> str:
    prefix = rule_id.split("-")[0].upper()
    return {"DCMP": "DCMP", "FCC": "FCC", "WCAG": "WCAG", "NFLX": "NFLX"}.get(
        prefix, prefix)


_FAMILY_WORDS = {
    "dcmp": "DCMP", "fcc": "FCC", "wcag": "WCAG", "netflix": "NFLX", "nflx": "NFLX",
}
_TOPIC_RULE_HINTS = {
    "reading-speed": ("CPS", "CAP-03"), "reading speed": ("CPS", "CAP-03"),
    "over-long": ("LEN", "CAP-01"), "too long": ("LEN", "CAP-01"),
    "line length": ("LEN", "CAP-01"),
    "duration": ("DUR", "CAP-04"), "too short": ("DUR", "CAP-04"),
    "audio description": ("DESC",), "description": ("DESC",),
}


# --------------------------------------------------------------------------- #
# Natural-language -> typed ops (grounded, validated)
# --------------------------------------------------------------------------- #
class NLResult(BaseModel):
    """What compile_nl returns: an intent, the compiled ops, and a query."""
    intent: Literal["mutate", "query", "unknown"]
    engine: str                              # "watsonx" | "deterministic"
    ops: list[ReviewOp] = Field(default_factory=list)
    query: Optional[ReviewQuery] = None
    matched: list[str] = Field(default_factory=list)   # finding keys the NL selected
    reasoning: str = ""


_ACTION_WORDS = {
    "dismiss": "dismiss_finding", "accept": "accept_finding",
    "flag": "flag_finding", "reset": "reset_finding", "reopen": "reset_finding",
}


def _parse_time(phrase: str) -> tuple[Optional[float], Optional[float]]:
    """Extract 'after M:SS' / 'before M:SS' / 'after N minutes/seconds'."""
    after = before = None

    def to_secs(m: re.Match) -> float:
        if m.group("mmss"):
            mm, ss = m.group("mmss").split(":")
            return int(mm) * 60 + float(ss)
        val = float(m.group("num"))
        unit = (m.group("unit") or "").lower()
        return val * 60 if unit.startswith("min") else val

    pat = r"(?P<mmss>\d{1,2}:\d{2})|(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>minutes?|min|seconds?|sec|s)?"
    for kw, setter in (("after", "after"), ("before", "before"), ("past", "after")):
        m = re.search(rf"{kw}\s+({pat})", phrase)
        if m:
            secs = to_secs(m)
            if setter == "after":
                after = secs
            else:
                before = secs
    return after, before


def compile_nl_deterministic(phrase: str, session: ReviewSession) -> NLResult:
    """Keyword compiler used when no watsonx key is present (and in tests)."""
    p = phrase.lower().strip()

    # selector: family + topic-hint + level + time window
    family = next((v for w, v in _FAMILY_WORDS.items() if w in p), None)
    level = next((lv for lv in ("error", "warning", "note") if lv in p), None)
    after, before = _parse_time(p)
    rule_hints: tuple[str, ...] = ()
    for topic, hints in _TOPIC_RULE_HINTS.items():
        if topic in p:
            rule_hints = hints
            break

    def selects(node: FindingNode) -> bool:
        if family and _family_of(node.rule_id) != family:
            return False
        if level and node.level != level:
            return False
        if rule_hints and not any(h in node.rule_id.upper() for h in rule_hints):
            return False
        if after is not None and (node.timecode is None or node.timecode < after):
            return False
        if before is not None and (node.timecode is None or node.timecode > before):
            return False
        return True

    matched = [k for k, n in session.state.findings.items() if selects(n)]

    action = next((a for w, a in _ACTION_WORDS.items() if w in p), None)
    if action:
        reason = None
        rm = re.search(r"(?:as|because|reason:?)\s+(.+)$", phrase, re.IGNORECASE)
        if rm:
            reason = rm.group(1).strip().rstrip(".")
        ops = [
            ReviewOp(kind=action, target=k, source="nl",  # type: ignore[arg-type]
                     payload={"reason": reason} if reason and action == "dismiss_finding" else {})
            for k in matched
        ]
        return NLResult(
            intent="mutate", engine="deterministic", ops=ops, matched=matched,
            reasoning=(f"{action} {len(matched)} finding(s)"
                       + (f" [family={family}]" if family else "")
                       + (f" [~{'/'.join(rule_hints)}]" if rule_hints else "")
                       + (f" [after {after}s]" if after is not None else "")
                       + (f" [before {before}s]" if before is not None else "")))

    if any(w in p for w in ("show", "list", "which", "find", "how many", "what")):
        q = ReviewQuery(family=family, level=level, after=after, before=before)
        return NLResult(intent="query", engine="deterministic", query=q,
                        matched=matched, reasoning=f"query -> {len(matched)} match(es)")

    return NLResult(intent="unknown", engine="deterministic",
                    reasoning="no action or query verb recognized")


def compile_nl(phrase: str, session: ReviewSession) -> NLResult:
    """Compile NL to grounded typed ops. watsonx/Granite if available, else keywords.

    The watsonx path (IBM AI at runtime) proposes {action, selector} JSON; we
    ALWAYS re-ground and re-validate it against the deterministic selector so the
    model can never dismiss a finding the engine did not produce. On any failure
    we fall back to the deterministic compiler.
    """
    try:
        from src.watsonx_nl import compile_intent_watsonx  # optional, key-gated
        intent = compile_intent_watsonx(phrase)            # {action, family, level, topic, after, before}
        if intent:
            # Re-run the deterministic selector using the model's structured
            # intent as hints -> grounding + validation is identical, so the
            # model can only ever narrow to REAL findings.
            hint_phrase = _intent_to_phrase(intent)
            res = compile_nl_deterministic(hint_phrase, session)
            res.engine = "watsonx"
            res.reasoning = "watsonx-compiled intent, re-grounded: " + res.reasoning
            return res
    except Exception:
        pass
    return compile_nl_deterministic(phrase, session)


def _intent_to_phrase(intent: dict) -> str:
    """Turn a watsonx structured intent back into a phrase the grounded
    deterministic selector consumes (keeps ONE grounding path)."""
    parts = [str(intent.get("action", ""))]
    for k in ("family", "level", "topic"):
        if intent.get(k):
            parts.append(str(intent[k]))
    if intent.get("after") is not None:
        parts.append(f"after {intent['after']}")
    if intent.get("before") is not None:
        parts.append(f"before {intent['before']}")
    if intent.get("reason"):
        parts.append(f"as {intent['reason']}")
    return " ".join(parts)
