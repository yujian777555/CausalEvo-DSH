"""Rejection tests for the strict frozen task-set validation
(P4-R1.12-REVIEW-FIX1 Task C)."""

import json
import runpy
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import analyze_r12_replication as a12


def _row(task, seed, arm, final=True):
    return {"episode_id": f"run/{task}/{seed}/{arm}", "task_id": task, "seed": seed,
            "arm": arm, "attempt1_success": False, "final_success": final,
            "retried": True, "attempt_1_status": "none", "attempt_2_status": "none",
            "edited": True, "invalid": False, "attempt1_visible_failures": 0,
            "final_status": "none", "provider_calls": 3, "input_tokens": 100,
            "cache_read_tokens": 50, "output_tokens": 20, "cost_cny": 0.001,
            "latency_ms": 1000, "intervention_text": "t", "selected_genome_id": "g1",
            "policy_version": "cea-v2.1-r1.10", "population_version": 1,
            "selection_reason": "r", "controller_update": {"updated": True},
            "population_version_after": 1}


def _all_rows():
    tasks = sorted(p.name for p in (REPO / "benchmarks" / "tasks").iterdir()
                   if p.is_dir())
    assert len(tasks) == 26
    rows = []
    for t in tasks:
        for seed in (20261027, 20261028):
            for arm in a12.ARMS_R12:
                rows.append(_row(t, seed, arm))
    return rows


def _write(tmp_path, rows):
    d = tmp_path / "run"
    d.mkdir()
    (d / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                   encoding="utf-8")
    (d / "events.jsonl").write_text("", encoding="utf-8")
    return d


def _run(d):
    sys.argv = ["analyze_r12_replication.py", str(d)]
    try:
        runpy.run_path(str(REPO / "scripts" / "analyze_r12_replication.py"),
                       run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise


def test_committed_208_rows_passes():
    _run(REPO / "results" / "phase4" / "live2" / "phase4-r12-replication-pilot-20261027T034229Z")


def test_normal_synthetic_208_rows_passes(tmp_path):
    d = _write(tmp_path, _all_rows())
    _run(d)


def test_missing_whole_task_rejected(tmp_path):
    rows = _all_rows()
    victim = rows[0]["task_id"]
    rows = [r for r in rows if r["task_id"] != victim]
    d = _write(tmp_path, rows)
    with pytest.raises(ValueError):
        _run(d)


def test_unexpected_task_rejected(tmp_path):
    rows = _all_rows()
    rows.append(_row("micro-999-not-a-task", 20261027, "B0-original"))
    d = _write(tmp_path, rows)
    with pytest.raises(ValueError):
        _run(d)


def test_unexpected_arm_rejected(tmp_path):
    rows = _all_rows()
    rows.append(_row("micro-000-clamp_value", 20261027, "B9-not-an-arm"))
    d = _write(tmp_path, rows)
    with pytest.raises(ValueError):
        _run(d)


def test_delete_single_row_rejected(tmp_path):
    rows = _all_rows()[:-1]
    d = _write(tmp_path, rows)
    with pytest.raises(ValueError):
        _run(d)


def test_duplicate_row_rejected(tmp_path):
    rows = _all_rows()
    rows.append(rows[0])
    d = _write(tmp_path, rows)
    with pytest.raises(ValueError):
        _run(d)


def test_unexpected_seed_rejected(tmp_path):
    rows = _all_rows()
    rows[0]["seed"] = 20261014
    d = _write(tmp_path, rows)
    with pytest.raises(ValueError):
        _run(d)


def test_manifest_hash_mismatch_rejected(tmp_path):
    # a benchmarks root with different content must yield a different manifest
    # hash and be rejected (not a runpy monkeypatch, which cannot affect the
    # fresh runpy namespace).
    fake = tmp_path / "fake-tasks"
    fake.mkdir()
    (fake / "micro-000-clamp_value").mkdir()
    (fake / "micro-000-clamp_value" / "solution.py").write_text("x = 1\n",
                                                                encoding="utf-8")
    d = _write(tmp_path, _all_rows())
    with pytest.raises(ValueError):
        a12.main(benchmarks_root=fake)
