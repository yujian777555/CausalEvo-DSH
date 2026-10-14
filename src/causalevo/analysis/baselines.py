"""Attribution baselines (P2.1-S4).

B0 "raw trace": outcome-only classifier — no evidence analysis; abstains
(unknown) on anything not decidable from the outcome alone. It exists so the
rule-based B1 (and later CausalEvo) has a floor to beat.

B1 "rule-based": the trace_analyzer rule chain.

Neither is a model; neither claims accuracy beyond its construction.
"""

from __future__ import annotations

from typing import Any

from .schema import Confidence, EvidenceItem, FailureCategory, FailureReport
from .trace_analyzer import analyze_trace


def attribute_b0_raw(trace: dict[str, Any]) -> FailureReport:
    """Outcome-only: timeout/budget map to execution; everything else unknown."""
    states = trace.get("states", {})
    outcome = (
        "success" if (states.get("visible_tests_passed") and states.get("sealed_tests_passed"))
        else "timeout" if states.get("timeout")
        else "budget_stop" if states.get("budget_stop")
        else "invalid" if states.get("invalid")
        else "failed"
    )
    task_id = trace.get("task_id", "?")
    run_id = trace.get("run_id", "?")
    if outcome == "success":
        return FailureReport(task_id, run_id, "success", FailureCategory.UNKNOWN.value,
                             [], Confidence.HIGH.value,
                             "outcome-only baseline", "none")
    if outcome in ("timeout", "budget_stop"):
        ev = [EvidenceItem("state", f"states.{outcome}", "true")]
        return FailureReport(task_id, run_id, outcome, FailureCategory.EXECUTION.value,
                             ev, Confidence.LOW.value,
                             "outcome-only baseline; no mechanism analysis",
                             "环境/预算排查")
    ev = [EvidenceItem("state", "states", "non-success without decisive outcome signal")]
    return FailureReport(task_id, run_id, outcome, FailureCategory.UNKNOWN.value,
                         ev, Confidence.LOW.value,
                         "outcome-only baseline abstains by design", "保持 unknown")


def attribute_b1_rules(trace: dict[str, Any]) -> FailureReport:
    return analyze_trace(trace)
