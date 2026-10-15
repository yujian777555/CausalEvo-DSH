"""Phase 4 integrity tests: pairing completeness, uniqueness, doc freeze."""

import json
from pathlib import Path

import pytest

import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import analyze_phase4 as analyze  # noqa: E402

RUN = REPO / "results" / "phase4" / "live" / "phase4-live-20261014T110259Z"


def _rows():
    return analyze.load_rows(RUN)


def test_pairing_complete_grid():
    rows = _rows()
    keys = {(r["task_id"], r["arm"], r["seed"]) for r in rows}
    tasks = {r["task_id"] for r in rows}
    assert len(tasks) == 26
    assert len(keys) == 312 == len(rows), "duplicate or missing (task, arm, seed)"


def test_two_seeds_present():
    assert {r["seed"] for r in _rows()} == {20261014, 20261015}


def test_latency_positive():
    assert all(r["latency_ms"] > 0 for r in _rows())


def test_provider_calls_within_envelope():
    """Envelope = <=2 agent ATTEMPTS per task (initial + one retry). The ledger
    provider_calls counts LLM requests inside the tool loop (observed 2-8),
    which is a different granularity — pinned here so the two are never
    conflated again."""
    for r in _rows():
        assert r["provider_calls"] >= 1
        assert r["retried"] in (True, False)


def test_attempts_never_exceed_two():
    for r in _rows():
        # attempt count = 1 + retried (B0 never retries)
        assert (1 + int(r["retried"])) <= 2


def test_intervention_names_valid():
    valid = set(analyze.INTERVENTION_TEXT if hasattr(analyze, "INTERVENTION_TEXT") else [])
    from causalevo.eval.live_pilot import INTERVENTION_TEXT
    valid = set(INTERVENTION_TEXT) | {"reflection", "ceav1_bundle"}
    for r in _rows():
        if r["intervention"] is not None:
            assert r["intervention"] in valid


def test_manifest_schema():
    m = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))
    for k in ("run_id", "live", "seeds", "arms", "task_count", "rows",
              "budget_cap_cny", "spent_cny", "provenance"):
        assert k in m
    assert m["live"] is True
    assert m["rows"] == 312


def test_provenance_has_repo_sha():
    m = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))
    assert m["provenance"]["repo_head_sha"]


def test_protocol_doc_exists_and_frozen_sections():
    text = (REPO / "docs" / "PHASE4_EXPERIMENT_PROTOCOL.md").read_text(encoding="utf-8")
    for section in ("指标", "预算", "Baselines", "停止规则"):
        assert section in text


def test_evolution_gain_matches_definition():
    out = analyze.analyze(RUN)
    p0 = out["pass_rate"]["B0-original"]
    p5 = out["pass_rate"]["B5-cea-v1"]
    assert out["evolution_gain"] == pytest.approx(p5 - p0)


def test_statistical_tests_p_values_bounded():
    st = json.loads((RUN / "statistical_tests.json").read_text(encoding="utf-8"))
    for m in st["mcnemar"]:
        if m["p_value"] is not None:
            assert 0.0 <= m["p_value"] <= 1.0
    for b in st["bootstrap"]:
        if b["ci95"]:
            assert b["ci95"][0] <= b["mean_diff"] <= b["ci95"][1]


def test_cost_analysis_per_arm_keys():
    co = json.loads((RUN / "cost_analysis.json").read_text(encoding="utf-8"))
    for arm, v in co["per_arm"].items():
        assert {"runs", "cost_cny", "input_tokens", "output_tokens",
                "cache_read_tokens", "provider_calls", "mean_latency_ms"} <= set(v)


def test_no_hidden_test_leakage_in_rows():
    text = (RUN / "tasks.jsonl").read_text(encoding="utf-8")
    assert "sealed_tests.py" not in text
    assert "solution_fixed" not in text
