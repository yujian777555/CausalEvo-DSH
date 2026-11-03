"""Non-vacuous Holm mapping regression tests (P4-R1.12-REVIEW-FIX3 Task B).

Deterministic fixture with three DISTINCT raw p-values whose lexical key order
differs from raw-p order. Verifies the helper maps adjusted values back to the
correct keys, enforces cumulative maximum/monotonicity/ties/[0,1], and that
the analyzer applies Holm only to the three secondary comparisons while the
primary stays unadjusted.
"""

import json
import runpy
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import analyze_r12_replication as a12


def test_helper_maps_distinct_pvalues_to_correct_keys():
    fixture = {"comparison_z": 0.01, "comparison_a": 0.20, "comparison_m": 0.04}
    assert len(set(fixture.values())) == 3, "raw p-values must be distinct"
    raw_sorted_keys = sorted(fixture, key=fixture.get)
    assert raw_sorted_keys == ["comparison_z", "comparison_m", "comparison_a"]
    assert raw_sorted_keys != sorted(fixture), \
        "raw-p ordering must differ from lexical key ordering"
    adjusted = a12.holm_adjusted_by_key(fixture)
    # rank0: 3*0.01=0.03; rank1: 2*0.04=0.08; rank2: 1*0.20=0.20
    assert adjusted["comparison_z"] == pytest.approx(0.03)
    assert adjusted["comparison_m"] == pytest.approx(0.08)
    assert adjusted["comparison_a"] == pytest.approx(0.20)
    # adjusted values are monotonically non-decreasing over raw-p order
    seq = [adjusted[k] for k in raw_sorted_keys]
    assert all(x <= y for x, y in zip(seq, seq[1:])), "cumulative maximum monotonicity"
    assert all(0.0 <= v <= 1.0 for v in adjusted.values())


def test_helper_ties_and_cumulative_maximum():
    fixture = {"k1": 0.01, "k2": 0.01, "k3": 0.5}
    adjusted = a12.holm_adjusted_by_key(fixture)
    assert adjusted["k1"] == pytest.approx(0.03)
    assert adjusted["k2"] == pytest.approx(0.03)
    assert adjusted["k3"] == pytest.approx(0.5)
    assert a12.holm_adjusted_by_key({"a": 1.0, "b": 1.0}) == {"a": 1.0, "b": 1.0}
    assert a12.holm_adjusted_by_key({}) == {}


def test_analyzer_applies_holm_only_to_secondary_and_primary_unadjusted():
    out = json.loads((REPO / "results" / "phase4" / "live2" /
                      "phase4-r12-replication-pilot-20261027T034229Z" / "analysis.json")
                     .read_text(encoding="utf-8"))
    secondary = set(out["secondary_holm_family"])
    assert secondary == {"CEA-v2-online vs B5-v1-frozen-pareto",
                         "CEA-v2-online vs B0-original",
                         "B5-v1-frozen-pareto vs B1-random"}
    primary = out["primary_comparison"]["arm_pair"]
    assert primary not in secondary
    assert out["comparisons"][primary]["holm_adj_p"] is None
    for key in secondary:
        assert out["comparisons"][key]["holm_adj_p"] is not None


def test_old_lexical_assignment_would_be_wrong():
    # Guard against the OLD bug: assigning adjusted values by lexicographic
    # comparison-name order instead of by raw-p order would attach the WRONG
    # adjusted value to a key when p-values differ.
    fixture = {"comparison_z": 0.20, "comparison_a": 0.01, "comparison_m": 0.04}
    adjusted = a12.holm_adjusted_by_key(fixture)
    # if someone assigned by lexical order, comparison_a would get 0.20, not 0.03
    assert adjusted["comparison_a"] != 0.20, \
        "lexical-order misassignment would put the largest adjusted value on comparison_a"
    assert adjusted["comparison_z"] == 0.20, "the largest adjusted value belongs to comparison_z"
