"""
Live subsystem truth for AccessGate.

A judge should be able to ask one question, "is the generative layer actually
working on this deployment right now", and get a straight answer without having
to run the gated fix themselves and read a provenance field buried in the
response.

Two rules govern this module, and both come from things that have already gone
wrong here or in the field.

FIRST, IT NEVER MAKES AN OUTBOUND CALL. `/health` is pinged by the CI keepalive
and hit again on every cold start. On 2026-07-27 a metered encoder sitting on a
startup path drained a month of watsonx quota in under a day, because the cost
multiplier is the restart rate, not the traffic rate. A health endpoint that
probed watsonx would repeat that mistake with better intentions. So this module
only ever REPORTS what has already happened during real traffic, plus what the
process can see about itself for free.

SECOND, IT DISTINGUISHES "FAILED" FROM "NOT CHECKED". Reporting an unobserved
subsystem as healthy is the failure that let a rival ship a live demo whose
availability gate silently marked every handle "taken", because a probe that
could not answer was folded into a negative answer. Three states, never two:

    ok            we called it, it worked, here is when and what model
    failed        we called it, it failed, here is the error and when
    not_observed  nothing has exercised it on this instance yet

`not_observed` is the honest default after a cold start, and it is NOT a
failure. Saying so plainly is the point.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

# Guards _OBSERVATIONS. FastAPI serves requests from a thread pool, so two
# requests can record concurrently; the lock keeps a snapshot internally
# consistent rather than half-written.
_LOCK = threading.Lock()

# subsystem name -> last observed outcome. Only ever written by record().
_OBSERVATIONS: dict[str, dict[str, Any]] = {}

# Every metered subsystem a judge might reasonably ask about, declared up front
# so the payload has a stable shape whether or not traffic has touched them.
# A subsystem missing from the response would read as "we hid it".
KNOWN_SUBSYSTEMS = (
    "vision_drafter",
    "guardian",
    "report_summary",
)


def record(
    name: str,
    ok: bool,
    *,
    model_id: Optional[str] = None,
    detail: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> None:
    """
    Record the outcome of a real call that already happened.

    Never raises. A transparency layer that can take down the request it is
    describing is worse than no transparency layer, and this is called from
    inside response handlers.
    """
    try:
        with _LOCK:
            _OBSERVATIONS[name] = {
                "ok": bool(ok),
                "model_id": model_id,
                "detail": detail,
                "latency_ms": latency_ms,
                "at": time.time(),
            }
    except Exception:  # noqa: BLE001, S110
        # Deliberately swallowed: see docstring.
        pass


def _age_seconds(then: float) -> int:
    return max(0, int(time.time() - then))


def snapshot() -> dict[str, Any]:
    """
    Per-subsystem state. Pure read, no network, safe to call on every ping.
    """
    with _LOCK:
        observed = {k: dict(v) for k, v in _OBSERVATIONS.items()}

    out: dict[str, Any] = {}
    for name in KNOWN_SUBSYSTEMS:
        obs = observed.get(name)
        if obs is None:
            out[name] = {
                "state": "not_observed",
                "note": "Nothing has exercised this on this instance yet. "
                        "Not a failure: run the gated fix and re-check.",
            }
            continue
        entry: dict[str, Any] = {
            "state": "ok" if obs["ok"] else "failed",
            "observed_seconds_ago": _age_seconds(obs["at"]),
        }
        for key in ("model_id", "latency_ms", "detail"):
            if obs.get(key) is not None:
                entry[key] = obs[key]
        out[name] = entry

    # Anything recorded that is not in KNOWN_SUBSYSTEMS still gets reported,
    # so adding a call site can never silently drop its observation.
    for name, obs in observed.items():
        if name in out:
            continue
        out[name] = {
            "state": "ok" if obs["ok"] else "failed",
            "observed_seconds_ago": _age_seconds(obs["at"]),
            "model_id": obs.get("model_id"),
        }
    return out


def reset() -> None:
    """Clear all observations. For tests only."""
    with _LOCK:
        _OBSERVATIONS.clear()
