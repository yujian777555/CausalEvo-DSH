"""Trace analyzer tests on REAL committed Phase 1 R2 traces (fixtures are
actual offline runs, not synthetic constructions)."""

import json
from pathlib import Path

import pytest

from causalevo.analysis.trace_analyzer import analyze_trace
from causalevo.analysis.baselines import attribute_b0_raw

REPO = Path(__file__).resolve().parents[1]
R2 = REPO / "results" / "phase1" / "r2-offline"


def _load(run_prefix: str) -> list[dict]:
    for run_dir in sorted(R2.iterdir()):
        if run_dir.name.startswith(run_prefix):
            return [json.loads(l) for l in
                    (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    raise FileNotFoundError(run_prefix)


def _load_scenario(scenario: str) -> list[dict]:
    for run_dir in sorted(R2.iterdir()):
        manifest = run_dir / "manifest.json"
        if manifest.is_file():
            m = json.loads(manifest.read_text(encoding="utf-8"))
            if (m.get("config") or {}).get("scenario") == scenario:
                return [json.loads(l) for l in
                        (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()
                        if l.strip()]
    raise FileNotFoundError(scenario)


def test_noop_maps_to_planning_failure():
    for trace in _load_scenario("noop"):
        rep = analyze_trace(trace)
        assert rep.failure_type == "planning_failure"
        assert any(e.kind == "no_tool_use" for e in rep.evidence)


def test_bad_tool_call_maps_to_tool_failure():
    for trace in _load_scenario("bad_tool_call"):
        rep = analyze_trace(trace)
        assert rep.failure_type == "tool_failure"
        assert rep.confidence == "high"


def test_tool_over_budget_maps_to_strategy_failure():
    for trace in _load_scenario("tool_over_budget"):
        rep = analyze_trace(trace)
        assert rep.failure_type == "strategy_failure"
        assert any(e.kind == "repeat_pattern" for e in rep.evidence)


def test_provider_error_maps_to_execution_failure():
    for trace in _load_scenario("provider_error"):
        rep = analyze_trace(trace)
        assert rep.failure_type == "execution_failure"
        assert rep.confidence == "high"


def test_wrong_fix_maps_to_knowledge_failure():
    for trace in _load_scenario("wrong_fix"):
        rep = analyze_trace(trace)
        assert rep.failure_type == "knowledge_failure"


def test_correct_fix_is_success_without_failure_type():
    for trace in _load_scenario("correct_fix"):
        rep = analyze_trace(trace)
        assert rep.outcome == "success"
        assert rep.confidence == "high"


def test_b0_baseline_abstains_on_plain_failures():
    for trace in _load_scenario("wrong_fix"):
        rep = attribute_b0_raw(trace)
        assert rep.failure_type == "unknown"
        assert rep.evidence  # abstention carries insufficiency evidence


def test_b0_baseline_maps_timeout_to_execution():
    fake = {"task_id": "t", "run_id": "r",
            "states": {"timeout": True, "budget_stop": False, "invalid": False,
                       "visible_tests_passed": False, "sealed_tests_passed": False}}
    rep = attribute_b0_raw(fake)
    assert rep.failure_type == "execution_failure"


def test_evidence_refs_point_at_trace_fields():
    for trace in _load_scenario("bad_tool_call"):
        rep = analyze_trace(trace)
        for e in rep.evidence:
            root = e.ref.split(".")[0].split("#")[0]
            assert root in trace or root in trace.get("agent", {}) or root in trace.get("judge", {}), \
                f"evidence ref {e.ref} not grounded in trace"


def test_no_cot_or_sealed_content_in_reports():
    for trace in _load_scenario("noop"):
        rep = analyze_trace(trace)
        text = json.dumps(rep.as_dict(), ensure_ascii=False)
        assert "reasoning" not in text.lower()
        assert "sealed_tests.py" not in text
