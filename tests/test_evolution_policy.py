"""Policy tests (P3.1-S3): state layout, random/rule/LinUCB policies."""

import numpy as np
import pytest

from causalevo.evolution.policy import (
    ACTIONS,
    FAILURE_TYPES,
    LinUCBPolicy,
    RandomPolicy,
    RulePolicy,
    state_vector,
)


def test_state_vector_length_base():
    v = state_vector({"failure_type": "tool_failure", "prompt_chars": 400, "n_visible_checks": 5})
    assert len(v) == len(FAILURE_TYPES) + 2


def test_state_vector_one_hot():
    v = state_vector({"failure_type": "strategy_failure"})
    assert v[FAILURE_TYPES.index("strategy_failure")] == 1.0
    assert sum(v[:len(FAILURE_TYPES)]) == 1.0


def test_state_vector_unknown_failure_falls_to_unknown_slot():
    v = state_vector({"failure_type": "not-a-thing"})
    assert sum(v[:len(FAILURE_TYPES)]) == 0.0


def test_state_vector_normalization_caps():
    v = state_vector({"failure_type": "unknown", "prompt_chars": 99999, "n_visible_checks": 99})
    assert v[len(FAILURE_TYPES)] == 1.0
    assert v[len(FAILURE_TYPES) + 1] == 1.0


def test_state_vector_history_block():
    v = state_vector({"failure_type": "unknown"}, history_rates=[0.1] * len(ACTIONS))
    assert len(v) == len(FAILURE_TYPES) + 2 + len(ACTIONS)


def test_random_policy_deterministic_with_seed():
    a = RandomPolicy(42)
    b = RandomPolicy(42)
    s = {"failure_type": "tool_failure"}
    assert [a.select(s, ACTIONS) for _ in range(5)] == [b.select(s, ACTIONS) for _ in range(5)]


def test_rule_policy_maps_taxonomy():
    p = RulePolicy()
    assert p.select({"failure_type": "tool_failure"}, ACTIONS) == "lib:tool_failure"
    assert p.select({"failure_type": "planning_failure"}, ACTIONS) == "lib:planning_failure"


def test_rule_policy_fallback_on_subset():
    p = RulePolicy()
    out = p.select({"failure_type": "tool_failure"}, ["lib:unknown"])
    assert out == "lib:unknown"


def test_linucb_policy_select_and_update():
    p = LinUCBPolicy(alpha=0.5)
    s = {"failure_type": "tool_failure"}
    a1 = p.select(s, ACTIONS)
    p.update(s, a1, 1.0)
    assert p.updates == 1
    assert p.select(s, ACTIONS) in ACTIONS


def test_linucb_policy_hash_changes_after_update():
    p = LinUCBPolicy()
    s = {"failure_type": "unknown"}
    h0 = p.state_hash()
    p.update(s, ACTIONS[0], 1.0)
    assert p.state_hash() != h0


def test_linucb_policy_serialization_roundtrip():
    p = LinUCBPolicy(alpha=0.9, use_history=True)
    s = {"failure_type": "tool_failure"}
    p.update(s, ACTIONS[1], 0.5, history_rates=[0.0] * len(ACTIONS))
    p2 = LinUCBPolicy.from_dict(p.to_dict())
    assert p2.bandit.alpha == 0.9 and p2.use_history
    s2 = {"failure_type": "tool_failure"}
    assert p.select(s2, ACTIONS, [0.0] * len(ACTIONS)) == \
        p2.select(s2, ACTIONS, [0.0] * len(ACTIONS))


def test_linucb_learns_better_action():
    p = LinUCBPolicy(alpha=0.3)
    s = {"failure_type": "knowledge_failure"}
    good = ACTIONS.index("lib:knowledge_failure")
    for _ in range(10):
        p.update(s, ACTIONS[good], 1.0)
        p.update(s, ACTIONS[0], -0.5)
    assert p.select(s, ACTIONS) == "lib:knowledge_failure"
