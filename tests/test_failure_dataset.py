"""Failure dataset builder + evaluation metrics tests (P2.1-S3/S5)."""

import json
from pathlib import Path

from causalevo.analysis.evaluate import evaluate
from causalevo.failure_dataset.builder import build_records, iter_traces, stats

REPO = Path(__file__).resolve().parents[1]


def test_iter_traces_finds_committed_runs():
    traces = list(iter_traces(REPO / "results" / "phase1"))
    assert len(traces) > 100  # 52 R1 + 52 R2 noop + scenario runs
    assert all(isinstance(t[0], dict) for t in traces)


def test_records_cover_every_trace_no_fabrication():
    traces = list(iter_traces(REPO / "results" / "phase1"))
    records = build_records(REPO / "results" / "phase1")
    assert len(records) == len(traces)
    trace_ids = {t[0]["trace_id"] for t in traces}
    assert {r["trace_id"] for r in records} == trace_ids


def test_records_schema_fields():
    records = build_records(REPO / "results" / "phase1")
    required = {"trace_id", "task_id", "failure_category", "evidence", "confidence",
                "repair_hint", "source_run", "provider_kind", "ground_truth", "outcome"}
    for r in records:
        assert required <= set(r)


def test_ground_truth_labels_align_with_scenarios():
    records = build_records(REPO / "results" / "phase1")
    labeled = [r for r in records if r["ground_truth"]]
    assert labeled, "expected labeled scenario records"
    assert all(r["failure_category"] == r["ground_truth"] for r in labeled)


def test_stats_counts_sum_to_total():
    records = build_records(REPO / "results" / "phase1")
    s = stats(records)
    assert sum(s["by_category"].values()) == s["total_records"] == len(records)
    assert sum(s["by_confidence"].values()) == len(records)


def test_evaluate_metrics_math():
    records = [
        {"failure_category": "tool_failure", "ground_truth": "tool_failure", "evidence": [{}]},
        {"failure_category": "tool_failure", "ground_truth": "tool_failure", "evidence": [{}]},
        {"failure_category": "unknown", "ground_truth": "execution_failure", "evidence": [{}]},
        {"failure_category": "planning_failure", "ground_truth": "planning_failure", "evidence": []},
    ]
    ev = evaluate(records)
    assert abs(ev["accuracy_labeled"] - 0.75) < 1e-9
    assert ev["unknown_rate"] == 0.25
    assert ev["abstention_rate"] == 0.25
    assert ev["macro_f1_labeled"] is not None
    # evidence coverage over non-unknown: 2 of 3 have evidence
    assert abs(ev["evidence_coverage_non_unknown"] - 2 / 3) < 1e-9


def test_evaluate_empty_and_unlabeled():
    assert evaluate([])["n_records"] == 0
    ev = evaluate([{"failure_category": "unknown", "evidence": [{}]}])
    assert ev["accuracy_labeled"] is None
    assert ev["unknown_rate"] == 1.0


def test_no_sensitive_content_in_records():
    records = build_records(REPO / "results" / "phase1")
    blob = json.dumps(records, ensure_ascii=False)
    assert "sk-" not in blob
    assert "solution_fixed" not in blob
    assert "sealed_tests.py" not in blob


def test_dataset_artifacts_exist_and_match():
    out = REPO / "results" / "phase2" / "failure_analysis"
    records_path = out / "failure_records.jsonl"
    if not records_path.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(REPO / "scripts" / "build_failure_dataset.py")],
                       check=True, cwd=REPO)
    records = [json.loads(l) for l in records_path.read_text(encoding="utf-8").splitlines()]
    rebuilt = build_records(REPO / "results" / "phase1")
    assert len(records) == len(rebuilt)
    stats_file = json.loads((out / "failure_stats.json").read_text(encoding="utf-8"))
    assert stats_file["stats"]["total_records"] == len(records)
    assert (out / "manifest.json").exists()
    assert (out / "sample_reports.json").exists()
