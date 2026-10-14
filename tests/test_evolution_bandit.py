"""LinUCB core tests (P3.1)."""

import numpy as np
import pytest

from causalevo.evolution.bandit import LinUCB


def test_init_validation():
    with pytest.raises(ValueError):
        LinUCB(2, 3, alpha=0)
    with pytest.raises(ValueError):
        LinUCB(2, 3, ridge=0)


def test_select_returns_valid_action():
    b = LinUCB(3, 5)
    x = np.zeros(5)
    assert b.select(x) in (0, 1, 2)


def test_state_dim_mismatch_raises():
    b = LinUCB(2, 3)
    with pytest.raises(ValueError):
        b.scores(np.zeros(4))


def test_update_changes_scores():
    b = LinUCB(2, 3)
    x = np.array([1.0, 0.0, 0.0])
    before = b.scores(x).copy()
    b.update(0, x, 1.0)
    after = b.scores(x)
    assert after[0] > before[0]  # rewarded action scores higher
    assert after[1] == pytest.approx(before[1])  # other action untouched


def test_determinism():
    def run():
        b = LinUCB(2, 3)
        x = np.array([0.5, 0.5, 0.0])
        b.update(1, x, 1.0)
        b.update(0, x, -0.5)
        return b.scores(x)
    assert np.allclose(run(), run())


def test_serialization_roundtrip():
    b = LinUCB(3, 4, alpha=0.7)
    x = np.array([1.0, 0.0, 1.0, 0.0])
    b.update(2, x, 1.0)
    b2 = LinUCB.from_dict(b.to_dict())
    assert np.allclose(b.scores(x), b2.scores(x))
    assert b2.alpha == 0.7


def test_negative_reward_penalizes():
    b = LinUCB(2, 2)
    x = np.array([1.0, 0.0])
    b.update(0, x, -1.0)
    b.update(1, x, 1.0)
    # with enough updates the UCB bonus shrinks relative to the mean shift
    for _ in range(5):
        b.update(0, x, -1.0)
        b.update(1, x, 1.0)
    assert b.scores(x)[1] > b.scores(x)[0]
