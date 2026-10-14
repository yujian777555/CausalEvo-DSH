"""Phase 1.5 experiment-protocol freeze tests (fully offline, zero API spend).

These tests pin the immutable parts of the Phase 1 protocol so that ANY later
edit — config tweak, schema drift, registry change — fails loudly instead of
silently mutating the experiment definition:

1. configs/phase1_b0.yaml + configs/phase1_b1.yaml sha256-pinned (constants
   computed 2026-10-13 from the frozen files); the two configs may differ
   ONLY in policy id and behavior knobs; budget/execution/tasks stay equal.
2. Policy parity freeze: B0/B1 share the identical budget envelope and both
   keep persistent_updates False (deliberate duplicate of the R1 guard).
3. Trace/manifest/summary schema freeze: an offline noop pipeline run must
   emit exactly the 8 outcome states, provider_kind "none", model_invoked
   False, the exact 10-key manifest, and the exact 10-key summary.
4. Registry freeze: benchmarks/registry.json microtasks split_seed 20261010
   and counts 26/13/7/6 (total/train/dev/sealed_test).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from causalevo.eval.executor import LocalTrustedExecutor
from causalevo.eval.judge import Judge
from causalevo.eval.metrics import summarize_traces
from causalevo.eval.pipeline import run_offline
from causalevo.eval.policy import B0, B1, check_budget_parity
from causalevo.eval.task_spec import load_all_tasks

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_B0 = REPO_ROOT / "configs" / "phase1_b0.yaml"
CONFIG_B1 = REPO_ROOT / "configs" / "phase1_b1.yaml"
REGISTRY_PATH = REPO_ROOT / "benchmarks" / "registry.json"
TASKS_DIR = REPO_ROOT / "benchmarks" / "tasks"

# Pinned 2026-10-13 (Phase 1.5 freeze): sha256 of the raw file bytes.
# Any later edit to either file — including comments/whitespace — must fail.
PHASE1_B0_SHA256 = "98536728d527fa3ee79f1f8b939acce0cf9d4167447d8e8c690a6f6014490985"
PHASE1_B1_SHA256 = "fba4ce5ad097d2472ff8aa291393bb5a5c714f3b1b5b2fe0f14e2e5ea4083235"

EXPECTED_STATES = {
    "api_response_observed", "tool_executed", "task_completed",
    "visible_tests_passed", "sealed_tests_passed", "invalid", "timeout",
    "budget_stop",
}
EXPECTED_MANIFEST_KEYS = {
    "run_id", "policy_id", "created_utc", "split_seed", "task_count",
    "executor_kind", "config", "config_sha256", "notes", "provenance",
}
EXPECTED_SUMMARY_KEYS = {
    "requested", "executed", "scored", "visible_tests_passed",
    "sealed_tests_passed", "task_succeeded", "invalid", "timeouts",
    "success_rate_over_executed", "note",
}
FREEZE_SPLIT_SEED = 20261010
FREEZE_SPLIT_QUOTA = {"train": 13, "dev": 7, "sealed_test": 6}
FREEZE_TASK_COUNT = 26
N_TASKS = 2


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def frozen_noop_run(tmp_path_factory):
    """One offline noop run over 2 tasks, shared by the schema-freeze tests."""
    specs = load_all_tasks(TASKS_DIR)[:N_TASKS]
    assert len(specs) == N_TASKS
    executor = LocalTrustedExecutor.for_trusted_content()
    result = run_offline(
        specs, B0, Judge(executor), executor,
        tmp_path_factory.mktemp("protocol-freeze"),
        fake_mode="noop", split_seed=FREEZE_SPLIT_SEED,
        config={"benchmark": "microtasks", "freeze": "phase1.5"},
    )
    run_dir = Path(result["run_dir"])
    result["trace_rows"] = [
        json.loads(line)
        for line in (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result["manifest"] = json.loads(
        (run_dir / "manifest.json").read_text(encoding="utf-8"))
    return result


def test_phase1_b0_yaml_sha256_pinned():
    assert _sha256(CONFIG_B0) == PHASE1_B0_SHA256


def test_phase1_b1_yaml_sha256_pinned():
    assert _sha256(CONFIG_B1) == PHASE1_B1_SHA256


def test_phase1_configs_differ_only_in_policy_and_behavior():
    cfg0 = yaml.safe_load(CONFIG_B0.read_text(encoding="utf-8"))
    cfg1 = yaml.safe_load(CONFIG_B1.read_text(encoding="utf-8"))
    assert set(cfg0) == set(cfg1)
    # Fair-comparison envelope: budget, execution, and task selection identical.
    assert cfg0["budget"] == cfg1["budget"]
    assert cfg0["execution"] == cfg1["execution"]
    assert cfg0["tasks"] == cfg1["tasks"]
    # The two baselines differ in policy identity and behavior knobs only.
    assert cfg0["policy"] == B0.policy_id
    assert cfg1["policy"] == B1.policy_id
    behavior0, behavior1 = cfg0["behavior"], cfg1["behavior"]
    assert set(behavior0) == set(behavior1)
    changed = {k for k in behavior0 if behavior0[k] != behavior1[k]}
    assert changed <= {"allow_reflection", "max_attempts_per_task"}
    assert changed, "B0/B1 must remain two distinct decision policies"
    assert behavior0["persistent_updates"] is False
    assert behavior1["persistent_updates"] is False


def test_policy_budget_parity_freeze():
    check_budget_parity(B0, B1)  # identical envelopes: must not raise
    assert B0.budget == B1.budget


def test_policy_persistent_updates_disabled_freeze():
    assert B0.persistent_updates is False
    assert B1.persistent_updates is False


def test_trace_states_schema_freeze(frozen_noop_run):
    rows = frozen_noop_run["trace_rows"]
    assert len(rows) == N_TASKS
    for trace in rows:
        assert set(trace["states"]) == EXPECTED_STATES


def test_trace_provider_honesty_freeze(frozen_noop_run):
    """Offline fake-agent runs never invoke a model or observe an API response."""
    for trace in frozen_noop_run["trace_rows"]:
        assert trace["provider_kind"] == "none"
        assert trace["model_invoked"] is False
        assert trace["states"]["api_response_observed"] is False


def test_manifest_schema_freeze(frozen_noop_run):
    manifest = frozen_noop_run["manifest"]
    assert set(manifest) == EXPECTED_MANIFEST_KEYS
    assert manifest["policy_id"] == B0.policy_id
    assert manifest["split_seed"] == FREEZE_SPLIT_SEED
    assert manifest["task_count"] == N_TASKS
    assert manifest["executor_kind"] == "local-trusted"
    assert len(manifest["config_sha256"]) == 16


def test_registry_freeze():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    micro = registry["microtasks"]
    assert micro["split_seed"] == FREEZE_SPLIT_SEED
    assert micro["count"] == FREEZE_TASK_COUNT
    assert micro["split_quota"] == FREEZE_SPLIT_QUOTA
    for split, quota in FREEZE_SPLIT_QUOTA.items():
        assert len(micro["splits"][split]) == quota
    assert len(micro["tasks"]) == FREEZE_TASK_COUNT


def test_summary_metrics_schema_freeze(frozen_noop_run):
    assert set(frozen_noop_run["summary"]) == EXPECTED_SUMMARY_KEYS
    # The aggregator itself is pinned to the same schema on raw trace dicts.
    assert set(summarize_traces(frozen_noop_run["trace_rows"])) == EXPECTED_SUMMARY_KEYS


def test_microtasks_relabeled_engineering_regression():
    """P1.6: the 26 microtasks are engineering regression, never paper eval."""
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    micro = registry["microtasks"]
    assert micro["role"] == "engineering_regression"
    assert micro["paper_eval_eligible"] is False


def test_holdout_manifest_hashes_only():
    path = REPO_ROOT / "benchmarks" / "holdout_manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    assert m["kind"] == "private-holdout"
    text = path.read_text(encoding="utf-8")
    assert "def " not in text, "holdout manifest must not contain task code"
    assert m["count"] == 3
