"""Offline tests for the R1.12 replication analysis script (no docker)."""

import json
import runpy
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import analyze_r12_replication as a12


def _row(task, seed, arm, final, a1=False, cost=0.001, updated=False, genome="g1"):
    return {"episode_id": f"run/{task}/{seed}/{arm}", "task_id": task, "seed": seed,
            "arm": arm, "attempt1_success": a1, "final_success": final,
            "retried": not a1, "attempt_1_status": "none", "attempt_2_status": "none",
            "edited": True, "invalid": False, "attempt1_visible_failures": 0,
            "final_status": "none", "provider_calls": 3, "input_tokens": 100,
            "cache_read_tokens": 50, "output_tokens": 20, "cost_cny": cost,
            "latency_ms": 1000, "intervention_text": "t", "selected_genome_id": genome,
            "policy_version": "cea-v2.1-r1.10", "population_version": 1,
            "selection_reason": "r", "controller_update": {"updated": updated} if updated else None,
            "population_version_after": 1}


def _write_run(tmp_path, rows, events):
    d = tmp_path / "run"
    d.mkdir()
    (d / "tasks.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (d / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return d


def _run(d):
    sys.argv = ["analyze_r12_replication.py", str(d)]
    try:
        runpy.run_path(str(REPO / "scripts" / "analyze_r12_replication.py"),
                       run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise
    return json.loads((d / "analysis.json").read_text(encoding="utf-8"))


def test_analysis_structure_and_counters(tmp_path):
    rows = []
    for t in ["t1", "t2"]:
        for seed in (20261027, 20261028):
            for arm in a12.ARMS_R12:
                rows.append(_row(t, seed, arm, final=(arm != "CEA-v2-online")))
    d = _write_run(tmp_path, rows, [
        {"kind": "evolve", "nsga3_parent_selection_calls": 1,
         "nsga3_survivor_selection_calls": 0}])
    out = _run(d)
    assert out["rows_total"] == 16
    assert out["coverage"]["seeds"] == [20261027, 20261028]
    assert out["algorithm_fidelity"]["nsga3_parent_selection_calls"] == 1
    assert out["algorithm_fidelity"]["nsga3_survivor_selection_calls"] == 0
    assert out["algorithm_fidelity"]["evolve_events"] == 1
    for comp in out["comparisons"].values():
        assert "exact_cluster_signflip_p" in comp
        assert "cluster_bootstrap_ci95" in comp
        assert "holm_adj_p" in comp


def test_duplicate_key_rejected(tmp_path):
    rows = [_row("t1", 20261027, "B0-original", True)]
    rows.append(rows[0])
    d = _write_run(tmp_path, rows, [])
    with pytest.raises(ValueError):
        _run(d)


def test_missing_seed_rejected(tmp_path):
    rows = [_row("t1", 20261027, "B0-original", True)]
    d = _write_run(tmp_path, rows, [])
    with pytest.raises(ValueError):
        _run(d)
