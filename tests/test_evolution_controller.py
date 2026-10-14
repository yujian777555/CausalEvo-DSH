"""Controller + temporal discipline tests (P3.1-S2/S4)."""

import pytest

from causalevo.evolution.controller import CausalEvolutionController
from causalevo.evolution.memory import Episode, EpisodeMemory
from causalevo.evolution.policy import ACTIONS, LinUCBPolicy, RandomPolicy
from causalevo.evolution.reward import compute_reward

STATE = {"failure_type": "tool_failure", "prompt_chars": 100, "n_visible_checks": 3}


def test_controller_select_shape():
    c = CausalEvolutionController(LinUCBPolicy())
    out = c.select_intervention(STATE, ACTIONS)
    assert set(out) == {"selected_action", "confidence", "policy_version"}
    assert out["selected_action"] in ACTIONS
    assert out["confidence"] in ("low", "medium", "high")


def test_policy_version_changes_with_updates():
    c = CausalEvolutionController(LinUCBPolicy())
    v0 = c.select_intervention(STATE, ACTIONS)["policy_version"]
    c.record_and_update(0, STATE, ACTIONS, ACTIONS[0], 1.0)
    v1 = c.select_intervention(STATE, ACTIONS)["policy_version"]
    assert v0 != v1


def test_memory_rejects_out_of_order():
    m = EpisodeMemory()
    m.append(Episode(1, {}, [], "a", 0.0))
    with pytest.raises(ValueError):
        m.append(Episode(1, {}, [], "a", 0.0))


def test_history_up_to_excludes_future():
    m = EpisodeMemory()
    for i in range(5):
        m.append(Episode(i, {}, [], "a", float(i)))
    assert len(m.history_up_to(3)) == 3
    assert all(e.episode_id < 3 for e in m.history_up_to(3))


def test_update_uses_only_past_history():
    """record_and_update at t must not see episodes >= t (incl. itself)."""
    c = CausalEvolutionController(LinUCBPolicy(use_history=True))
    for i in range(4):
        c.record_and_update(i, STATE, ACTIONS, ACTIONS[i % 3], 1.0)
    rates = c._rates_before(4)
    assert len(rates) == len(ACTIONS)
    # rates reflect only the 4 recorded episodes
    used = [i % 3 for i in range(4)]
    for idx, rate in enumerate(rates):
        expect = sum(1 for u in used if u == idx)
        assert rate == pytest.approx(expect / max(1, sum(1 for u in used if u == idx)) or 0.0)


def test_reward_math():
    assert compute_reward(1, 0.0) == 1.0
    assert compute_reward(1, 0.001) == 1.0 - 100.0 * 0.001
    assert compute_reward(0, 0.0) == 0.0
    # negative cost deltas (cheaper) never add reward
    assert compute_reward(0, -0.5) == 0.0


def test_random_policy_select_in_candidates():
    c = CausalEvolutionController(RandomPolicy(7))
    out = c.select_intervention(STATE, ["lib:unknown"])
    assert out["selected_action"] == "lib:unknown"
    assert out["confidence"] == "low"


def test_no_future_leakage_in_history_rates():
    """Appending later episodes must not change _rates_before(t)."""
    c = CausalEvolutionController(LinUCBPolicy(use_history=True))
    for i in range(3):
        c.record_and_update(i, STATE, ACTIONS, ACTIONS[i], float(i) - 1.0)
    before = c._rates_before(2)
    # later episodes arrive AFTER t; they must not retroactively change it
    for i in range(3, 8):
        c.record_and_update(i, STATE, ACTIONS, ACTIONS[i % len(ACTIONS)], 5.0)
    assert c._rates_before(2) == before


def test_replay_identical_history_gives_identical_policy():
    def build():
        c = CausalEvolutionController(LinUCBPolicy(alpha=0.5))
        for i in range(6):
            s = {"failure_type": FAILURE_TYPES_FOR[i % 3]}
            sel = c.select_intervention(s, ACTIONS)
            c.record_and_update(i, s, ACTIONS, sel["selected_action"], float(i % 2))
        return c.policy.state_hash()
    assert build() == build()


FAILURE_TYPES_FOR = ["tool_failure", "planning_failure", "unknown"]
