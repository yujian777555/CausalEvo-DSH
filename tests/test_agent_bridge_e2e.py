"""Offline end-to-end agent-bridge tests (R2): the real containerized DSH
runtime drives each task over the protocol-level fake provider, then the
independent Docker judge grades the workspace.

Engineering plumbing evidence only: scripted fake-provider outcomes are NOT
model performance. Requires docker plus the local agent/judge images; skips
cleanly otherwise. No external network: the fake provider binds 127.0.0.1 and
the container reaches it via host.docker.internal. The provider_timeout
scenario is covered by the budget tests, not here (it needs a short wall_time).
"""

import json
import subprocess
from dataclasses import fields, replace
from pathlib import Path

import pytest

from causalevo.eval.agent_pipeline import run_agent_tasks
from causalevo.eval.executor import DockerExecutor, docker_available
from causalevo.eval.scenarios import SCENARIOS
from causalevo.eval.judge import Judge
from causalevo.eval.policy import B0
from causalevo.eval.runtime_budget import RuntimeBudget
from causalevo.eval.task_spec import load_all_tasks
from causalevo.eval.trace import TaskTrace

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "benchmarks" / "tasks"
PATCH_PATH = REPO_ROOT / "configs" / "dsh_task_patch.yml"
AGENT_IMAGE = "causalevo-dsh-agent:0.2.0"
JUDGE_IMAGE = "python:3.11-slim"
N_TASKS = 2


def _image_present(image: str) -> bool:
    try:
        proc = subprocess.run(["docker", "image", "inspect", image],
                              capture_output=True, timeout=15)
        return proc.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (docker_available() and _image_present(AGENT_IMAGE) and _image_present(JUDGE_IMAGE)),
    reason="docker or local agent/judge images unavailable",
)


def _run_scenario(tmp_path_factory, scenario: str, **budget_overrides):
    specs = load_all_tasks(TASKS_DIR)[:N_TASKS]
    assert len(specs) == N_TASKS
    budget = replace(B0.budget, **budget_overrides)

    def budget_factory() -> RuntimeBudget:
        return RuntimeBudget(
            max_provider_calls=budget.max_provider_calls,
            max_total_output_tokens=budget.max_total_output_tokens,
            max_tool_calls=budget.max_tool_calls,
            wall_time_s=budget.wall_time_s,
        )

    judge_executor = DockerExecutor()
    result = run_agent_tasks(
        specs, B0, Judge(judge_executor), judge_executor,
        tmp_path_factory.mktemp(f"agent-{scenario}"),
        scenario_factory=SCENARIOS[scenario],
        budget_factory=budget_factory,
        image=AGENT_IMAGE,
        patch_path=PATCH_PATH,
        provider_kind="fake",
        split_seed=20261010,
        config={"scenario": scenario, "policy": B0.policy_id, "tasks": len(specs)},
    )
    run_dir = Path(result["run_dir"])
    result["trace_rows"] = [
        json.loads(line)
        for line in (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return result


@pytest.fixture(scope="module")
def noop_run(tmp_path_factory):
    return _run_scenario(tmp_path_factory, "noop")


@pytest.fixture(scope="module")
def correct_fix_run(tmp_path_factory):
    return _run_scenario(tmp_path_factory, "correct_fix")


@pytest.fixture(scope="module")
def wrong_fix_run(tmp_path_factory):
    return _run_scenario(tmp_path_factory, "wrong_fix")


@pytest.fixture(scope="module")
def bad_tool_run(tmp_path_factory):
    return _run_scenario(tmp_path_factory, "bad_tool_call")


@pytest.fixture(scope="module")
def tool_budget_run(tmp_path_factory):
    return _run_scenario(tmp_path_factory, "tool_over_budget", max_tool_calls=2)


@pytest.fixture(scope="module")
def provider_error_run(tmp_path_factory):
    return _run_scenario(tmp_path_factory, "provider_error")


def test_noop_run_invokes_the_loop_but_fixes_nothing(noop_run):
    summary = noop_run["summary"]
    assert summary["requested"] == N_TASKS
    assert summary["executed"] == N_TASKS
    assert summary["task_succeeded"] == 0  # honest: noop fixes nothing
    for trace in noop_run["trace_rows"]:
        assert trace["states"]["tool_executed"] is False
        assert trace["provider_kind"] == "fake"
        assert trace["model_invoked"] is True


def test_correct_fix_passes_visible_and_sealed(correct_fix_run):
    summary = correct_fix_run["summary"]
    assert summary["task_succeeded"] == N_TASKS
    for trace in correct_fix_run["trace_rows"]:
        assert trace["states"]["visible_tests_passed"] is True
        assert trace["states"]["sealed_tests_passed"] is True
        assert trace["states"]["invalid"] is False
        ledger = trace["agent"]["ledger"]
        assert ledger["provider_attempts"] >= 2  # read -> write -> final text
        assert ledger["known_input_tokens"] > 0
        assert ledger["output_tokens"] > 0


def test_wrong_fix_fails_tests_without_being_invalid(wrong_fix_run):
    # The wrong fix is valid python with wrong logic: test failures, not invalid.
    summary = wrong_fix_run["summary"]
    assert summary["task_succeeded"] == 0
    assert summary["invalid"] == 0
    assert summary["visible_tests_passed"] == 0
    assert summary["sealed_tests_passed"] == 0


def test_bad_tool_call_is_surfaced_and_the_run_completes(bad_tool_run):
    summary = bad_tool_run["summary"]
    assert summary["executed"] == N_TASKS  # unknown tool -> tool error, loop goes on
    assert summary["task_succeeded"] == 0
    for results in bad_tool_run["tool_results_by_task"]:
        assert any("unknown tool" in result for result in results)


def test_tool_over_budget_stops_mid_run(tool_budget_run):
    summary = tool_budget_run["summary"]
    assert summary["scored"] == 0
    assert summary["task_succeeded"] == 0
    for trace in tool_budget_run["trace_rows"]:
        assert trace["states"]["budget_stop"] is True
        assert trace["agent"]["failure_kind"] == "budget_stop"
        assert "tool_calls" in trace["agent"]["budget_stop_reason"]


def test_provider_error_never_counts_as_success(provider_error_run):
    # A scripted HTTP 500 is retried inside the runtime (6 attempts, no usage
    # frames) and ends the turn with finish_reason "error". R2 doctrine: those
    # requests were sent but cannot be metered -> unknown spend, fail-closed:
    # failure_kind "unknown_cost" and the pipeline stops launching new tasks.
    summary = provider_error_run["summary"]
    assert summary["task_succeeded"] == 0
    assert summary["invalid"] == 0  # infra failure is not a task-format failure
    trace_rows = provider_error_run["trace_rows"]
    assert len(trace_rows) == 1, "unknown_cost must stop the run (fail-closed)"
    trace = trace_rows[0]
    assert trace["agent"]["finish_reason"] == "error"
    assert trace["agent"]["failure_kind"] == "unknown_cost"
    assert trace["agent"]["ledger"]["unknown_spend_attempts"] > 0
    assert trace["states"]["task_completed"] is False
    assert trace["states"]["budget_stop"] is True


def test_manifest_and_traces_carry_full_provenance(correct_fix_run):
    run_dir = Path(correct_fix_run["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provenance"]["repo_head_sha"]
    assert len(manifest["config_sha256"]) == 16
    assert manifest["task_count"] == N_TASKS
    assert (run_dir / "report.json").is_file()
    trace_fields = {f.name for f in fields(TaskTrace)}
    for trace in correct_fix_run["trace_rows"]:
        assert set(trace) == trace_fields
        assert isinstance(trace["agent"]["ledger"], dict)
        assert trace["agent"]["ledger"]["provider_attempts"] >= 1
        assert trace["agent"]["events_slim"]


def test_workspace_digests_reflect_agent_edits(noop_run, correct_fix_run):
    for trace in noop_run["trace_rows"]:
        assert trace["workspace_digest_before"] == trace["workspace_digest_after"]
    for trace in correct_fix_run["trace_rows"]:
        assert trace["workspace_digest_before"] != trace["workspace_digest_after"]
