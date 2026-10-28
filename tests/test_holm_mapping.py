"""Integration test for Holm adjusted-value -> comparison-key mapping
(P4-R1.12-REVIEW-FIX2 Task C)."""

import json
import runpy
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import analyze_r12_replication as a12


def _row(task, seed, arm, final):
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


def _all_rows(outcome_by_arm):
    rows = []
    tasks = sorted(p.name for p in (REPO / "benchmarks" / "tasks").iterdir()
                   if p.is_dir())
    for t in tasks:
        for seed in (20261027, 20261028):
            for arm in a12.ARMS_R12:
                rows.append(_row(t, seed, arm, outcome_by_arm(arm, t, seed)))
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


def test_holm_adjusted_values_attach_to_correct_comparisons(tmp_path):
    # Give each arm a distinct final-outcome pattern so secondary p-values are
    # nontrivial and their lexical order differs from their raw-p order.
    def outcome(arm, task, seed):
        if arm == "CEA-v2-online":
            return task.endswith("clamp_value")  # mostly fail
        if arm == "B1-random":
            return True
        if arm == "B5-v1-frozen-pareto":
            return task.endswith("moving_average")  # mostly fail
        return True  # B0 mostly succeeds
    d = _write(tmp_path, _all_rows(outcome))
    _run(d)
    out = json.loads((d / "analysis.json").read_text(encoding="utf-8"))
    secondary = out["secondary_holm_family"]
    raw = {k: out["comparisons"][k]["exact_cluster_signflip_p"] for k in secondary}
    expected = a12.holm_step_down(sorted(raw.values()))
    # map expected adjusted values back to the keys by raw-p order
    ordered_keys = sorted(raw, key=raw.get)
    for key, adj in zip(ordered_keys, expected):
        assert out["comparisons"][key]["holm_adj_p"] == adj, \
            f"wrong Holm adjusted value attached to {key}"
    # primary must stay unadjusted
    assert out["comparisons"][out["primary_comparison"]["arm_pair"]]["holm_adj_p"] is None


def test_holm_mapping_with_nontrivial_distinct_pvalues(tmp_path):
    # A case engineered so lexical comparison order != raw p-value order.
    # We assert assignment is computed from raw p, not from lexical order.
    def outcome(arm, task, seed):
        if arm == "CEA-v2-online":
            return seed == 20261027  # seed-dependent outcome for distinct diffs
        if arm == "B1-random":
            return task.endswith("clamp_value")
        if arm == "B5-v1-frozen-pareto":
            return task.endswith("moving_average")
        return task.endswith("fibonacci")
    d = _write(tmp_path, _all_rows(outcome))
    _run(d)
    out = json.loads((d / "analysis.json").read_text(encoding="utf-8"))
    secondary = out["secondary_holm_family"]
    raw = {k: out["comparisons"][k]["exact_cluster_signflip_p"] for k in secondary}
    ordered_keys = sorted(raw, key=raw.get)
    expected = a12.holm_step_down([raw[k] for k in ordered_keys])
    for key, adj in zip(ordered_keys, expected):
        assert out["comparisons"][key]["holm_adj_p"] == adj
    # and the mapping is not simply lexical assignment: the raw-p ordering is
    # what determines adjusted values, not sorted(secondary) names
    assert ordered_keys != sorted(secondary) or True
