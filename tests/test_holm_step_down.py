"""Tests for the R1.12 Holm step-down adjustment and comparison-family
separation (P4-R1.12-REVIEW-FIX1 Task B)."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from analyze_r12_replication import holm_step_down


def test_holm_cumulative_max_nontrivial_ordering():
    # sorted p = [0.01, 0.02, 0.03], m = 3
    # rank0: 3*0.01=0.03; rank1: 2*0.02=0.04; rank2: 1*0.03=0.03 -> cumulative max 0.04
    adjusted = holm_step_down([0.03, 0.01, 0.02])
    assert adjusted == [0.03, 0.04, 0.04]
    assert all(a1 <= a2 for a1, a2 in zip(adjusted, adjusted[1:])), "monotone non-decreasing"


def test_holm_step_down_monotonic_and_clamped():
    adjusted = holm_step_down([0.5, 0.9, 0.99, 1.0])
    assert adjusted == [1.0, 1.0, 1.0, 1.0]
    assert all(0.0 <= p <= 1.0 for p in adjusted)


def test_holm_ties_and_p1_behavior():
    assert holm_step_down([0.01, 0.01, 0.5]) == [0.03, 0.03, 0.5]
    assert holm_step_down([1.0, 1.0, 1.0]) == [1.0, 1.0, 1.0]
    assert holm_step_down([]) == []


def test_primary_not_in_secondary_holm_family():
    out = json.loads((REPO / "results" / "phase4" / "live2" /
                      "phase4-r12-replication-pilot-20261027T034229Z" / "analysis.json")
                     .read_text(encoding="utf-8"))
    primary = out["primary_comparison"]
    assert primary["arm_pair"] == "CEA-v2-online vs B1-random"
    assert primary["exact_cluster_signflip_p_unadjusted"] == 1.0
    secondary = set(out["secondary_holm_family"])
    assert secondary == {"CEA-v2-online vs B5-v1-frozen-pareto",
                         "CEA-v2-online vs B0-original",
                         "B5-v1-frozen-pareto vs B1-random"}
    assert primary["arm_pair"] not in secondary
    for key in secondary:
        assert out["comparisons"][key]["holm_adj_p"] is not None
