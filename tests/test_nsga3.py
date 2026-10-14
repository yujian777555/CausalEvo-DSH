"""NSGA-III core tests (P3.2-S4)."""

import numpy as np
import pytest

from causalevo.evolution.nsga3 import (
    associate,
    das_dennis_reference_directions,
    dominates,
    fast_non_dominated_sort,
    hypervolume_2d_reference,
    normalize,
    nsga3_select,
)


def test_dominates():
    assert dominates(np.array([1, 1]), np.array([0, 1]))
    assert not dominates(np.array([1, 0]), np.array([0, 1]))
    assert not dominates(np.array([1, 1]), np.array([1, 1]))


def test_sort_simple():
    F = np.array([[2.0, 0.0], [0.0, 2.0], [1.0, 1.0], [-1.0, -1.0]])
    fronts = fast_non_dominated_sort(F)
    assert set(fronts[0]) == {0, 1, 2}
    assert fronts[1] == [3]


def test_sort_all_equal_single_front():
    F = np.ones((4, 3))
    fronts = fast_non_dominated_sort(F)
    assert len(fronts) == 1 and len(fronts[0]) == 4


def test_reference_directions_simplex():
    refs = das_dennis_reference_directions(3, 1)
    assert refs.shape == (3, 3)
    assert np.allclose(refs.sum(axis=1), 1.0)
    refs2 = das_dennis_reference_directions(4, 2)
    assert np.allclose(refs2.sum(axis=1), 1.0)


def test_normalize_scales_to_ideal():
    F = np.array([[1.0, 2.0], [0.0, 0.0], [0.5, 1.0]])
    z, ideal, intercepts = normalize(F)
    assert np.allclose(ideal, [1.0, 2.0])
    assert z.shape == F.shape
    assert np.all(z <= 1e-9)  # ideal is the max; translated values <= 0


def test_associate_nearest_direction():
    refs = das_dennis_reference_directions(2, 1)
    pts = np.array([[0.9, 0.1], [0.2, 0.8]])
    idx, dist = associate(pts, refs)
    # each point must associate with the reference direction nearest its axis
    assert refs[idx[0]][0] > refs[idx[0]][1]
    assert refs[idx[1]][1] > refs[idx[1]][0]
    assert dist[0] < 0.2


def test_nsga3_select_count_and_membership():
    rng = np.random.default_rng(0)
    F = rng.random((20, 4))
    sel = nsga3_select(F, 10, rng)
    assert len(sel) == 10
    assert len(set(sel)) == 10


def test_nsga3_deterministic_with_seed():
    F = np.random.default_rng(1).random((15, 4))
    a = nsga3_select(F, 8, np.random.default_rng(5))
    b = nsga3_select(F, 8, np.random.default_rng(5))
    assert a == b


def test_hypervolume_known_values():
    assert hypervolume_2d_reference(np.array([[1.0, 0.5], [0.5, 1.0]]),
                                    np.array([0.0, 0.0])) == pytest.approx(0.75)
    assert hypervolume_2d_reference(np.array([[2.0, 3.0]]),
                                    np.array([0.0, 0.0])) == pytest.approx(6.0)
    assert hypervolume_2d_reference(np.array([[1.0, 1.0]]),
                                    np.array([2.0, 2.0])) == 0.0


def test_hypervolume_empty():
    assert hypervolume_2d_reference(np.zeros((0, 4)), np.zeros(4)) == 0.0
