"""Diagnosis dataset builder (P2.2-S2).

Joins failure records (Phase 2.1) with trace features. Labels come ONLY from
the frozen taxonomy: scenario-injected ground truth or the frozen rule-chain
output for unlabeled engineering runs (marked label_source). Split is grouped
by task_id so no task leaks across train/val/test; seed is fixed.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .features import extract_features

SPLIT_SEED = 20261014
SPLIT_RATIOS = {"train": 0.6, "val": 0.2, "test": 0.2}


def _task_meta(tasks_dir: Path) -> dict[str, dict[str, int]]:
    meta: dict[str, dict[str, int]] = {}
    for tj in sorted(tasks_dir.glob("*/task.json")):
        m = json.loads(tj.read_text(encoding="utf-8"))
        meta[m["task_id"]] = {
            "prompt_chars": len(m["instructions"]),
            "n_visible_checks": m.get("n_visible_checks", 0),
        }
    return meta


def build_dataset(results_root: Path, tasks_dir: Path) -> list[dict[str, Any]]:
    """One row per trace with features + label (or None) + evidence."""
    from ..failure_dataset.builder import iter_traces
    from ..analysis.trace_analyzer import analyze_trace
    from ..failure_dataset.builder import SCENARIO_GROUND_TRUTH

    meta = _task_meta(tasks_dir)
    rows = []
    for trace, source_run, provider_kind, scenario in iter_traces(results_root):
        report = analyze_trace(trace)
        tm = meta.get(trace.get("task_id", ""), {"prompt_chars": 0, "n_visible_checks": 0})
        feat = extract_features(trace, task_prompt_chars=tm["prompt_chars"],
                                n_visible_checks=tm["n_visible_checks"])
        ground_truth = scenario and SCENARIO_GROUND_TRUTH.get(scenario)
        if ground_truth:
            label, label_source = ground_truth, "scenario_injected"
        elif report.outcome == "success":
            label, label_source = "success", "judge_outcome"
        elif report.failure_type != "unknown" and report.confidence in ("high", "medium"):
            label, label_source = report.failure_type, "rule_chain_silver"
        else:
            label, label_source = None, "unlabeled"
        rows.append({
            "trace_id": trace.get("trace_id"),
            "task_id": trace.get("task_id"),
            "source_run": source_run,
            "features": feat.as_dict(),
            "label": label,
            "label_source": label_source,
            "evidence": [e.as_dict() for e in report.evidence],
            "confidence": report.confidence,
        })
    return rows


def split_dataset(rows: list[dict[str, Any]], seed: int = SPLIT_SEED) -> dict[str, list[dict]]:
    """Group split by task_id: a task's traces live in exactly one split."""
    by_task: dict[str, list[dict]] = {}
    for r in rows:
        by_task.setdefault(r["task_id"], []).append(r)
    tasks = sorted(by_task)
    random.Random(seed).shuffle(tasks)
    n = len(tasks)
    n_train = int(n * SPLIT_RATIOS["train"])
    n_val = int(n * SPLIT_RATIOS["val"])
    out = {"train": [], "val": [], "test": []}
    for i, t in enumerate(tasks):
        split = "train" if i < n_train else "val" if i < n_train + n_val else "test"
        for r in by_task[t]:
            r = dict(r)
            r["split"] = split
            out[split].append(r)
    return out


def dataset_manifest(splits: dict[str, list[dict]], seed: int) -> dict[str, Any]:
    return {
        "seed": seed,
        "split_ratios": SPLIT_RATIOS,
        "grouped_by": "task_id",
        "counts": {k: len(v) for k, v in splits.items()},
        "label_sources": sorted({r["label_source"] for v in splits.values() for r in v}),
        "labeled_counts": {
            k: sum(1 for r in v if r["label"]) for k, v in splits.items()
        },
        "row_sha256": hashlib.sha256(
            json.dumps(splits, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
    }
