"""Tests for exact task-cluster sign-flip sensitivity (P4-R1.11 Task A)."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from analyze_r19_cluster_sensitivity import (analyze, exact_signflip_p,
                                             task_mean_differences,
                                             validate_rows)

AUDIT = REPO / "results" / "phase4" / "r19-audit"


def _rows():
    return [json.loads(l) for l in (AUDIT / "auditable_tasks.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]


def test_exactly_26_clusters_both_seeds_retained():
    results = analyze(_rows())
    for comp in results.values():
        assert comp["n_clusters"] == 26
        assert comp["seeds_kept_together"] is True


def test_exact_expected_p_values():
    results = analyze(_rows())
    assert results["CEA-v2-online vs B1-random"]["exact_two_sided_p"] == 0.75
    assert results["CEA-v2-online vs B5-v1-frozen-pareto"]["exact_two_sided_p"] == 0.625
    assert results["CEA-v2-online vs B0-original"]["exact_two_sided_p"] == 0.7265625
    assert results["B5-v1-frozen-pareto vs B1-random"]["exact_two_sided_p"] == 1.0


def test_two_sided_tail_and_tie_handling():
    # all-zero differences: every assignment is as extreme as observed -> p=1
    p, _ = exact_signflip_p([0] * 26, 0)
    assert p == 1.0
    # all +2 differences: only all-plus/all-minus reach |S|=52 -> p=2/2^26
    p, _ = exact_signflip_p([2] * 26, 52)
    assert p == 2 / (2 ** 26)
    # one-sided boundary: observed_sum=0 includes all assignments
    p, _ = exact_signflip_p([1, -1], 0)
    assert p == 1.0


def test_missing_arm_rejected():
    rows = [r for r in _rows() if r["arm"] != "CEA-v2-online"]
    with pytest.raises(ValueError):
        analyze(rows)


def test_duplicate_key_rejected():
    rows = _rows()
    rows.append(rows[0])
    with pytest.raises(ValueError):
        validate_rows(rows)


def test_missing_seed_rejected():
    rows = [r for r in _rows() if r["seed"] != 20261015]
    with pytest.raises(ValueError):
        validate_rows(rows)


def test_label_is_post_hoc_not_primary():
    out = json.loads((AUDIT / "sensitivity.json").read_text(encoding="utf-8"))
    assert out["label"] == "POST_HOC_CLUSTER_AWARE_SENSITIVITY"
    assert out["not_preregistered_primary"] is True


def test_historical_estimates_preserved_exactly_after_two_regenerations():
    """R1.11-FIX1: the three historical Monte Carlo records must survive every
    regeneration, byte-identically and with exact p/stat/permutations/seed."""
    import hashlib
    import subprocess
    import sys
    script = REPO / "scripts" / "analyze_r19_cluster_sensitivity.py"
    target = AUDIT / "sensitivity.json"
    source = json.loads((AUDIT / "previous_monte_carlo_estimates.json").read_text(
        encoding="utf-8"))
    expected = source["estimates"]
    hashes = []
    for _ in range(2):
        subprocess.run([sys.executable, str(script)], check=True,
                       capture_output=True, text=True, timeout=120)
        hashes.append(hashlib.sha256(target.read_bytes()).hexdigest())
        out = json.loads(target.read_text(encoding="utf-8"))
        got = out["previous_monte_carlo_estimates"]
        assert set(got) == set(expected), "all three estimates must be retained"
        for key, rec in expected.items():
            assert got[key] == rec, f"historical record changed: {key}"
        assert out["previous_monte_carlo_provenance"]["source_commit"] == \
            "2bb9e5c3e6f9ac8c01e9f2529d4939459b055b1e"
        assert out["previous_monte_carlo_provenance"]["n_permutations"] == 20000
        assert out["previous_monte_carlo_provenance"]["seed"] == 20261026
    assert hashes[0] == hashes[1], "regeneration must be byte-identical"


def test_regeneration_is_byte_deterministic(tmp_path):
    import subprocess
    import sys
    import hashlib
    script = REPO / "scripts" / "analyze_r19_cluster_sensitivity.py"
    target = AUDIT / "sensitivity.json"
    hashes = []
    for _ in range(2):
        proc = subprocess.run([sys.executable, str(script)], check=True,
                              capture_output=True, text=True, timeout=120)
        hashes.append(hashlib.sha256(target.read_bytes()).hexdigest())
    assert hashes[0] == hashes[1], "regeneration must be byte-identical"
