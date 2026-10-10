"""Run-level metrics aggregation. Counts are honest: requested vs executed vs
scored vs succeeded are distinct numbers; a fake/noop agent that fixes nothing
yields 0 successes, and that is the correct report."""

from __future__ import annotations

from typing import Any


def summarize_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    requested = len(traces)
    executed = sum(1 for t in traces if t["states"].get("task_completed"))
    scored = sum(1 for t in traces if not t["states"].get("budget_stop"))
    visible_passed = sum(1 for t in traces if t["states"].get("visible_tests_passed"))
    sealed_passed = sum(1 for t in traces if t["states"].get("sealed_tests_passed"))
    succeeded = sum(
        1 for t in traces
        if t["states"].get("visible_tests_passed") and t["states"].get("sealed_tests_passed")
    )
    invalid = sum(1 for t in traces if t["states"].get("invalid"))
    timeouts = sum(1 for t in traces if t["states"].get("timeout"))
    return {
        "requested": requested,
        "executed": executed,
        "scored": scored,
        "visible_tests_passed": visible_passed,
        "sealed_tests_passed": sealed_passed,
        "task_succeeded": succeeded,
        "invalid": invalid,
        "timeouts": timeouts,
        "success_rate_over_executed": (succeeded / executed) if executed else None,
        "note": "offline pipeline validation; fake-policy outcomes are NOT model performance",
    }
