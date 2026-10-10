"""Baseline policy definitions: budget parity gate, behavior flags, YAML configs."""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from causalevo.eval.policy import B0, B1, Budget, Policy, check_budget_parity, get_policy

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_B0 = REPO_ROOT / "configs" / "phase1_b0.yaml"
CONFIG_B1 = REPO_ROOT / "configs" / "phase1_b1.yaml"


def test_budget_parity_passes_for_baselines():
    check_budget_parity(B0, B1)  # identical envelopes: must not raise


def test_tampered_budget_raises():
    tampered = replace(B1, budget=Budget(max_provider_calls=99))
    with pytest.raises(ValueError):
        check_budget_parity(B0, tampered)


def test_baselines_never_persist_updates():
    assert B0.persistent_updates is False
    assert B1.persistent_updates is False


def test_attempt_and_reflection_flags():
    assert B0.max_attempts_per_task == 1
    assert B1.max_attempts_per_task == 2
    assert B0.allow_reflection is False
    assert B1.allow_reflection is True


def test_budgets_identical_field_by_field():
    assert B0.budget == B1.budget
    for budget in (B0.budget, B1.budget):
        assert budget.max_provider_calls == 2
        assert budget.max_total_output_tokens == 2048
        assert budget.max_tool_calls == 20
        assert budget.wall_time_s == 300


@pytest.mark.parametrize(
    "config_path,policy",
    [(CONFIG_B0, B0), (CONFIG_B1, B1)],
)
def test_yaml_configs_match_policy_objects(config_path, policy):
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert cfg["policy"] == policy.policy_id
    assert cfg["budget"] == {
        "max_provider_calls": policy.budget.max_provider_calls,
        "max_total_output_tokens": policy.budget.max_total_output_tokens,
        "max_tool_calls": policy.budget.max_tool_calls,
        "wall_time_s": policy.budget.wall_time_s,
    }
    assert cfg["behavior"]["allow_reflection"] is policy.allow_reflection
    assert cfg["behavior"]["max_attempts_per_task"] == policy.max_attempts_per_task
    assert cfg["behavior"]["persistent_updates"] is False
    assert cfg["execution"]["mode"] == "offline"


def test_get_policy_roundtrip_and_unknown_id():
    for policy in (B0, B1):
        assert get_policy(policy.policy_id) is policy
    with pytest.raises(KeyError):
        get_policy("B9-does-not-exist")
