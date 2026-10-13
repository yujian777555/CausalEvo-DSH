"""P1: end-to-end offline pipeline validation with fake agents.

Engineering plumbing only: a noop/break/oracle fake agent's outcomes are
pipeline evidence, never model performance claims. Fully offline, no key.
"""

import json
from dataclasses import fields
from pathlib import Path

import pytest

from causalevo.eval.executor import LocalTrustedExecutor
from causalevo.eval.judge import Judge
from causalevo.eval.pipeline import run_offline
from causalevo.eval.policy import B0
from causalevo.eval.task_spec import load_all_tasks
from causalevo.eval.trace import TaskTrace

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "benchmarks" / "tasks"
N_TASKS = 3
EXPECTED_STATES = {
    "api_response_observed", "tool_executed", "task_completed",
    "visible_tests_passed", "sealed_tests_passed", "invalid", "timeout",
    "budget_stop",
}


def _run(tmp_path_factory, mode):
    specs = load_all_tasks(TASKS_DIR)[:N_TASKS]
    assert len(specs) == N_TASKS
    executor = LocalTrustedExecutor.for_trusted_content()
    result = run_offline(
        specs, B0, Judge(executor), executor,
        tmp_path_factory.mktemp(f"pipeline-{mode}"),
        fake_mode=mode, split_seed=20261010,
        config={"benchmark": "microtasks", "fake_mode": mode},
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
    return _run(tmp_path_factory, "noop")


@pytest.fixture(scope="module")
def oracle_run(tmp_path_factory):
    return _run(tmp_path_factory, "oracle")


@pytest.fixture(scope="module")
def break_run(tmp_path_factory):
    return _run(tmp_path_factory, "break")


def test_noop_run_counts_and_artifacts(noop_run):
    summary = noop_run["summary"]
    assert summary["requested"] == N_TASKS
    assert summary["executed"] == N_TASKS
    assert summary["scored"] == N_TASKS
    assert summary["task_succeeded"] == 0  # honest: noop fixes nothing
    assert len(noop_run["trace_rows"]) == N_TASKS
    run_dir = Path(noop_run["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["policy_id"] == B0.policy_id
    assert manifest["executor_kind"] == "local-trusted"
    assert manifest["task_count"] == N_TASKS
    assert len(manifest["config_sha256"]) == 16
    assert (run_dir / "report.json").is_file()


def test_oracle_run_proves_judge_can_pass_correct_code(oracle_run):
    # Engineering validation only: the judge+pipeline CAN pass correct code.
    assert oracle_run["summary"]["task_succeeded"] == N_TASKS
    assert oracle_run["summary"]["invalid"] == 0


def test_break_run_is_marked_invalid(break_run):
    assert break_run["summary"]["invalid"] == N_TASKS
    assert break_run["summary"]["task_succeeded"] == 0


def test_traces_carry_no_policy_internals(noop_run):
    """Blinding: a trace holds only the policy_id label, never budget or
    reflection internals — every key must be a declared TaskTrace field."""
    allowed = {f.name for f in fields(TaskTrace)}
    for trace in noop_run["trace_rows"]:
        assert set(trace) <= allowed
        assert trace["policy_id"] == B0.policy_id


def test_workspace_digests_reflect_agent_edits(noop_run, oracle_run):
    for trace in noop_run["trace_rows"]:
        assert trace["workspace_digest_before"] == trace["workspace_digest_after"]
    for trace in oracle_run["trace_rows"]:
        assert trace["workspace_digest_before"] != trace["workspace_digest_after"]


def test_every_trace_has_exactly_the_eight_states(noop_run):
    for trace in noop_run["trace_rows"]:
        assert set(trace["states"]) == EXPECTED_STATES
