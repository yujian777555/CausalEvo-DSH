"""Diagnosis results artifact tests (P2.2): committed outputs stay consistent."""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase2" / "diagnosis"


def test_artifacts_exist():
    for name in ("dataset_manifest.json", "baseline_results.json",
                 "confusion_matrix.json", "sample_diagnosis.json",
                 "diagnosis_dataset.jsonl"):
        assert (OUT / name).is_file(), name


def test_baseline_results_structure():
    data = json.loads((OUT / "baseline_results.json").read_text(encoding="utf-8"))
    assert {"B0-rules", "B1-feature-lr", "B2-embedding-lr"} <= set(data["results"])
    for name, res in data["results"].items():
        assert res["n_eval"] > 0
        assert 0.0 <= res["accuracy"] <= 1.0
        assert res["risk_coverage"], "risk-coverage points required"
        assert res["evidence_precision"] is not None


def test_confusion_matrix_square():
    cm = json.loads((OUT / "confusion_matrix.json").read_text(encoding="utf-8"))
    for name, block in cm.items():
        n = len(block["labels"])
        assert all(len(row) == n for row in block["matrix"])


def test_dataset_manifest_seed_and_counts():
    m = json.loads((OUT / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert m["seed"] == 20261014
    assert m["grouped_by"] == "task_id"
    total = sum(m["counts"].values())
    assert total > 100


def test_sample_diagnosis_schema():
    s = json.loads((OUT / "sample_diagnosis.json").read_text(encoding="utf-8"))
    for model, rows in s.items():
        for r in rows:
            assert {"trace_id", "failure_type", "evidence", "confidence",
                    "abstained", "model"} <= set(r)


def test_artifacts_regenerate_identically(tmp_path):
    """Re-running the diagnosis pipeline into a TEMP dir reproduces metrics;
    the committed artifacts are never overwritten by tests."""
    before = json.loads((OUT / "baseline_results.json").read_text(encoding="utf-8"))
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "run_diagnosis.py"),
                           "--out", str(tmp_path)],
                          capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr[-500:]
    after = json.loads((tmp_path / "baseline_results.json").read_text(encoding="utf-8"))
    for name in before["results"]:
        assert before["results"][name]["accuracy"] == after["results"][name]["accuracy"]
