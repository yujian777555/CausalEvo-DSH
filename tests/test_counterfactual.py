"""Counterfactual replay tests (P2.3-S3/S4): structure + one real docker pair."""

import json
import subprocess
from pathlib import Path

import pytest

from causalevo.counterfactual.replay import CounterfactualResult, replay_pair
from causalevo.eval.executor import docker_available
from causalevo.eval.judge import Judge
from causalevo.eval.executor import DockerExecutor
from causalevo.eval.runtime_budget import RuntimeBudget
from causalevo.eval.scenarios import SCENARIOS, scenario_tape
from causalevo.eval.task_spec import load_task
from causalevo.intervention.generator import NO_INTERVENTION

REPO = Path(__file__).resolve().parents[1]
IMAGE = "causalevo-dsh-agent:0.2.0"


def _image_present(image: str) -> bool:
    try:
        return subprocess.run(["docker", "image", "inspect", image],
                              capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


DOCKER_OK = docker_available() and _image_present(IMAGE) and _image_present("python:3.11-slim")
docker_required = pytest.mark.skipif(not DOCKER_OK, reason="docker/images unavailable")


def _budget():
    return RuntimeBudget(max_provider_calls=8, max_total_output_tokens=4096,
                         max_tool_calls=12, wall_time_s=240)


def test_counterfactual_result_serializes():
    r = CounterfactualResult(
        case_id="c", task_id="t", scenario="s", baseline="B0",
        intervention={}, original_outcome="none", counterfactual_outcome="none",
        original_success=False, counterfactual_success=False, changed_steps=[],
        success_delta=0, cost_delta_cny=0.0, original_ledger={}, counterfactual_ledger={},
        confidence="low",
    )
    d = json.loads(r.to_jsonl())
    assert d["success_delta"] == 0


@docker_required
def test_identity_replay_never_changes_outcome():
    spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")
    tape = scenario_tape(spec, SCENARIOS["wrong_fix"], max_calls=12)
    judge = Judge(DockerExecutor())
    res = replay_pair(spec, tape, NO_INTERVENTION, scenario="wrong_fix",
                      baseline="B0", image=IMAGE, patch_path=REPO / "configs" / "dsh_task_patch.yml",
                      network="ceval-net", budget=_budget(), judge=judge,
                      case_id="test-identity")
    assert res.success_delta == 0
    assert res.original_success == res.counterfactual_success
    assert res.changed_steps == []


@docker_required
def test_tool_case_intervention_unblocks_write():
    """case_tool: bad tool blocks the mandatory read; intervention fixes it."""
    spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")
    tape = scenario_tape(spec, SCENARIOS["bad_tool_blocks_write"], max_calls=12)
    from causalevo.intervention.generator import generate_intervention
    from causalevo.diagnosis.models import DiagnosisResult
    iv = generate_intervention(DiagnosisResult(
        trace_id="t", failure_type="tool_failure", evidence=[], confidence=0.9,
        abstained=False, model="test"))
    judge = Judge(DockerExecutor())
    res = replay_pair(spec, tape, iv, scenario="bad_tool_blocks_write",
                      baseline="B2-rule", image=IMAGE,
                      patch_path=REPO / "configs" / "dsh_task_patch.yml",
                      network="ceval-net", budget=_budget(), judge=judge,
                      case_id="test-tool-case")
    assert res.original_success is False
    assert res.counterfactual_success is True
    assert res.success_delta == 1
    assert res.changed_steps
    # same provider-call count under identical synthetic per-call usage ->
    # zero cost delta is the CORRECT accounting; extra-step cases differ
    assert res.original_ledger["provider_attempts"] == res.counterfactual_ledger["provider_attempts"]
    assert res.cost_delta_cny == 0.0


def test_artifacts_exist_and_are_consistent():
    out = REPO / "results" / "phase2" / "intervention"
    for name in ("intervention_manifest.json", "counterfactual_results.jsonl",
                 "baseline_comparison.json", "sample_cases.json"):
        assert (out / name).is_file(), name
    rows = [json.loads(l) for l in
            (out / "counterfactual_results.jsonl").read_text(encoding="utf-8").splitlines()]
    comp = json.loads((out / "baseline_comparison.json").read_text(encoding="utf-8"))
    assert sum(a["cases"] for a in comp["per_arm"].values()) == len(rows)
    for r in rows:
        assert {"case_id", "original_outcome", "counterfactual_outcome", "changed_steps",
                "success_delta", "cost_delta_cny"} <= set(r)


def test_b0_identity_arm_always_zero_delta():
    out = REPO / "results" / "phase2" / "intervention"
    rows = [json.loads(l) for l in
            (out / "counterfactual_results.jsonl").read_text(encoding="utf-8").splitlines()]
    for r in rows:
        if r["baseline"] == "B0-no-intervention":
            assert r["success_delta"] == 0
            assert r["changed_steps"] == []


def test_control_case_no_improvement():
    """case_ineffective: mismatched intervention must not improve (S3 case 3)."""
    out = REPO / "results" / "phase2" / "intervention"
    rows = [json.loads(l) for l in
            (out / "counterfactual_results.jsonl").read_text(encoding="utf-8").splitlines()]
    control = [r for r in rows if r["case_id"].startswith("case_ineffective")]
    assert control
    for r in control:
        assert r["success_delta"] == 0, f"control case improved under {r['baseline']}"


def test_every_case_records_diagnosis_intervention_before_after():
    out = REPO / "results" / "phase2" / "intervention"
    rows = [json.loads(l) for l in
            (out / "counterfactual_results.jsonl").read_text(encoding="utf-8").splitlines()]
    for r in rows:
        assert r["scenario"]  # failure source
        assert r["intervention"]["intervention_id"]
        assert r["original_outcome"] and r["counterfactual_outcome"]
