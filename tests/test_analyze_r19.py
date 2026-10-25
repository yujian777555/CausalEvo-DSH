"""Tests for scripts/analyze_r19_pilot.py statistics (offline, no docker)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze_r19_pilot import (cluster_bootstrap_ci, mcnemar_exact,  # noqa: E402
                               paired_diff, summarize)


def _row(task, seed, arm, a1, final, retried=True, cost=0.002):
    return {"task_id": task, "seed": seed, "arm": arm,
            "attempt1_success": a1, "final_success": final, "retried": retried,
            "provider_calls": 2, "input_tokens": 100, "cache_read_tokens": 10,
            "output_tokens": 50, "cost_cny": cost, "latency_ms": 1000,
            "controller_update": {"updated": True} if arm == "CEA-v2-online" else None,
            "selected_genome_id": "g1" if arm == "CEA-v2-online" else None,
            "population_version": 1 if arm == "CEA-v2-online" else None,
            "population_version_after": 1 if arm == "CEA-v2-online" else None}


def test_mcnemar_exact_values():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 0) < 0.07  # 5 discordant pairs, one-sided tail 1/32
    assert mcnemar_exact(10, 0) < 0.003


def test_paired_diff_and_recovery_denominator():
    rows = [
        _row("t1", 1, "B1-random", False, False),
        _row("t1", 1, "CEA-v2-online", False, True),
        _row("t2", 1, "B1-random", False, False),
        _row("t2", 1, "CEA-v2-online", False, False),
    ]
    pairs = paired_diff(rows, "CEA-v2-online", "B1-random")
    assert len(pairs) == 2
    dp = sum(1 for _, a, b in pairs if a == 1 and b == 0)
    dn = sum(1 for _, a, b in pairs if a == 0 and b == 1)
    assert (dp, dn) == (1, 0)
    s = summarize(rows)
    rec = s["per_arm"]["CEA-v2-online"]
    assert rec["recovery_denominator"] == 2
    assert rec["recovery_rate"] == 0.5
    assert s["update_analysis"]["observed_rows"] == 2
    assert s["update_analysis"]["distinct_selected_genomes"] == 1


def test_cluster_bootstrap_deterministic_and_bounded():
    rows = []
    for i in range(10):
        rows.append(_row(f"t{i}", 1, "CEA-v2-online", False, True))
        rows.append(_row(f"t{i}", 1, "B1-random", False, False))
    pairs = paired_diff(rows, "CEA-v2-online", "B1-random")
    d1 = cluster_bootstrap_ci(pairs, n_boot=200)
    d2 = cluster_bootstrap_ci(pairs, n_boot=200)
    assert d1 == d2, "fixed seed -> deterministic CI"
    diff, lo, hi = d1
    assert diff == 1.0 and lo > 0.9 and hi <= 1.0
    s = summarize(rows)
    comp = s["comparisons"]["CEA-v2-online vs B1-random"]
    assert comp["evidence_of_benefit"] is True, "all-discordant positive must count as benefit"


def test_no_benefit_when_random_better():
    rows = []
    for i in range(10):
        rows.append(_row(f"t{i}", 1, "CEA-v2-online", False, False))
        rows.append(_row(f"t{i}", 1, "B1-random", False, True))
    s = summarize(rows)
    comp = s["comparisons"]["CEA-v2-online vs B1-random"]
    assert comp["paired_diff"] == -1.0
    assert comp["evidence_of_benefit"] is False
