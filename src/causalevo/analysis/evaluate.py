"""Attribution evaluation (P2.1-S5): frozen metrics computed offline.

Metrics (docs/PHASE2_FAILURE_EVAL.md):
- classification: accuracy / macro F1 on the LABELED subset only
- evidence coverage: attributed (non-unknown) reports carrying >=1 evidence item
- evidence correctness: evidence refs must point at real trace fields (validated)
- reliability: unknown rate, abstention rate

Unknown is allowed by design; a confident wrong answer scores worse than an
honest abstention in review, not in these numbers — the numbers stay neutral
and the trade-off is reported, not hidden.
"""

from __future__ import annotations

from typing import Any

from .schema import FailureCategory

_CATEGORIES = [c.value for c in FailureCategory]


def evaluate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """records: builder rows with failure_category + optional ground_truth."""
    labeled = [r for r in records if r.get("ground_truth")]
    unknown = sum(1 for r in records if r["failure_category"] == "unknown")
    abstain = unknown  # abstention == emitting unknown in this taxonomy
    non_unknown = [r for r in records if r["failure_category"] != "unknown"]
    with_evidence = sum(1 for r in non_unknown if r.get("evidence"))

    accuracy = None
    macro_f1 = None
    per_class: dict[str, Any] = {}
    if labeled:
        correct = sum(1 for r in labeled if r["failure_category"] == r["ground_truth"])
        accuracy = correct / len(labeled)
        f1s = []
        for cat in _CATEGORIES:
            tp = sum(1 for r in labeled
                     if r["failure_category"] == cat and r["ground_truth"] == cat)
            fp = sum(1 for r in labeled
                     if r["failure_category"] == cat and r["ground_truth"] != cat)
            fn = sum(1 for r in labeled
                     if r["failure_category"] != cat and r["ground_truth"] == cat)
            if tp == fp == fn == 0:
                continue
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            f1s.append(f1)
            per_class[cat] = {"precision": precision, "recall": recall, "f1": f1,
                              "support": tp + fn}
        macro_f1 = sum(f1s) / len(f1s) if f1s else None

    n = len(records)
    return {
        "n_records": n,
        "n_labeled": len(labeled),
        "accuracy_labeled": accuracy,
        "macro_f1_labeled": macro_f1,
        "per_class": per_class,
        "evidence_coverage_non_unknown": (with_evidence / len(non_unknown)) if non_unknown else None,
        "unknown_rate": (unknown / n) if n else None,
        "abstention_rate": (abstain / n) if n else None,
    }
