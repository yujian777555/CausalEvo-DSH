"""Phase 4 tests: analysis math, schema, gates, no-leakage (offline; the live
pilot artifacts are read-only fixtures)."""

import json
from pathlib import Path

import numpy as np
import pytest


# --- import the analysis module from scripts/ ---
import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import analyze_phase4 as analyze  # noqa: E402

RUN = REPO / "results" / "phase4" / "live" / "phase4-live-20261014T110259Z"
DRY = REPO / "results" / "phase4" / "scratch"


def _rows():
    return analyze.load_rows(RUN)


def test_rows_schema_complete():
    for r in _rows():
        assert {"task_id", "arm", "seed", "attempt1_success", "retried",
                "final_success", "invalid", "timeout", "failure_kind",
                "intervention", "provider_calls", "tool_calls", "input_tokens",
                "cache_read_tokens", "output_tokens", "cost_cny", "latency_ms",
                "run_id"} <= set(r)


def test_row_count_312():
    assert len(_rows()) == 312


def test_all_arms_present():
    assert {r["arm"] for r in _rows()} == {
        "B0-original", "B1-random", "B2-rule", "B3-reflexion",
        "B4-cea-v0", "B5-cea-v1"}


def test_b0_never_retries():
    for r in _rows():
        if r["arm"] == "B0-original":
            assert r["retried"] is False
            assert r["intervention"] is None


def test_retry_only_on_failure():
    for r in _rows():
        if r["attempt1_success"]:
            assert r["retried"] is False


def test_pass_rate_bounds():
    for arm, rate in analyze.analyze(RUN)["pass_rate"].items():
        assert 0.0 <= rate <= 1.0


def test_mcnemar_exact_known_answer():
    rows = _rows()
    res = analyze.mcnemar_exact(rows, "B5-cea-v1", "B0-original")
    assert res["n_discordant"] == 10
    assert res["p_value"] == pytest.approx(0.34375)


def test_bootstrap_deterministic():
    rows = _rows()
    a = analyze.bootstrap_diff_ci(rows, "B5-cea-v1", "B0-original")
    b = analyze.bootstrap_diff_ci(rows, "B5-cea-v1", "B0-original")
    assert a["ci95"] == b["ci95"]


def test_cost_totals_match_manifest():
    manifest = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))
    cost = analyze.cost_analysis(_rows())
    assert cost["total_cost_cny"] == pytest.approx(manifest["spent_cny"], abs=1e-6)


def test_cost_within_budget_cap():
    manifest = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["spent_cny"] <= manifest["budget_cap_cny"]


def test_no_api_key_in_artifacts():
    blob = RUN / "auditable_tasks.jsonl"
    text = blob.read_text(encoding="utf-8")
    assert "sk-" not in text


def test_protocol_frozen_fields():
    p = json.loads((RUN / "protocol.json").read_text(encoding="utf-8"))
    assert p["frozen_before_live"] is True
    assert p["seeds"] == [20261014, 20261015]


def test_recovery_rate_denominator():
    rows = _rows()
    rr = analyze.recovery_rate(rows, "B5-cea-v1")
    failed_retried = [r for r in rows if r["arm"] == "B5-cea-v1"
                      and not r["attempt1_success"] and r["retried"]]
    assert rr == pytest.approx(
        sum(r["final_success"] for r in failed_retried) / len(failed_retried))


def test_analysis_outputs_written():
    for name in ("baseline_results.json", "statistical_tests.json", "cost_analysis.json"):
        assert (RUN / name).is_file()


def test_dry_run_artifacts_exist():
    runs = sorted(DRY.glob("phase4-dry-*"))
    assert runs
    rows = [json.loads(l) for l in (runs[-1] / "tasks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 24
    for r in rows:
        if r["arm"] == "B0-original":
            assert r["final_success"] is False  # dry tape: B0 never recovers
