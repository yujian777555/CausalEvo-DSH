"""Non-vacuous Holm mapping regression tests (P4-R1.12-REVIEW-FIX4 Task B).

Deterministic fixture with three DISTINCT raw p-values whose lexical key order
differs from raw-p order. Verifies the helper maps adjusted values back to the
correct keys, enforces cumulative maximum/monotonicity/ties/[0,1], and that
the analyzer applies Holm only to the three secondary comparisons while the
primary stays unadjusted.
"""

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
    primary = "CEA-v2-online vs B1-random"
    raw_p_by_key = {
        primary: 0.001,
        "CEA-v2-online vs B5-v1-frozen-pareto": 0.20,
        "CEA-v2-online vs B0-original": 0.01,
        "B5-v1-frozen-pareto vs B1-random": 0.04,
    }

    adjusted = a12.apply_secondary_holm(primary, raw_p_by_key)

    assert set(adjusted) == set(raw_p_by_key)
    assert adjusted[primary] is None
    expected_secondary = {
        "CEA-v2-online vs B5-v1-frozen-pareto": 0.20,
        "CEA-v2-online vs B0-original": 0.03,
        "B5-v1-frozen-pareto vs B1-random": 0.08,
    }
    for key, expected in expected_secondary.items():
        assert adjusted[key] == pytest.approx(expected)

    changed_primary_raw = {**raw_p_by_key, primary: 0.9}
    adjusted_with_changed_primary = a12.apply_secondary_holm(primary, changed_primary_raw)
    for key in expected_secondary:
        assert adjusted_with_changed_primary[key] == adjusted[key]


def test_apply_secondary_holm_requires_primary_raw_p():
    with pytest.raises(ValueError, match="missing primary comparison"):
        a12.apply_secondary_holm("primary", {"secondary": 0.01})


def test_old_lexical_assignment_would_be_wrong():
    # Guard against the OLD bug: assigning adjusted values by lexicographic
    # comparison-name order instead of by raw-p order would attach the WRONG
    # adjusted value to a key when p-values differ.
    fixture = {"comparison_z": 0.01, "comparison_a": 0.20, "comparison_m": 0.04}
    raw_p_keys = sorted(fixture, key=fixture.get)
    lexical_keys = sorted(fixture)
    assert raw_p_keys == ["comparison_z", "comparison_m", "comparison_a"]
    assert lexical_keys == ["comparison_a", "comparison_m", "comparison_z"]
    assert raw_p_keys != lexical_keys

    # The sorted adjusted values are [0.03, 0.08, 0.20]. Assigning them to
    # lexical keys rather than raw-p-sorted keys misassigns two values.
    lexical_misassigned = dict(zip(lexical_keys, [0.03, 0.08, 0.20]))
    adjusted = a12.holm_adjusted_by_key(fixture)
    assert any(lexical_misassigned[key] != adjusted[key] for key in fixture)
    assert lexical_misassigned["comparison_a"] != adjusted["comparison_a"]
    assert adjusted["comparison_z"] == pytest.approx(0.03)
    assert adjusted["comparison_m"] == pytest.approx(0.08)
    assert adjusted["comparison_a"] == pytest.approx(0.20)
