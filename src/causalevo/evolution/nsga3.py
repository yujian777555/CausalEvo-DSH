"""NSGA-III core (P3.2-S4) — pure numpy, no external optimization library.

Implements: fast non-dominated sort, Das–Dennis reference directions,
ideal/extreme-point normalization (ASF), perpendicular-distance association,
and niche-preserving selection. Deterministic given inputs + seed.
"""

from __future__ import annotations

import itertools

import numpy as np


def dominates(a: np.ndarray, b: np.ndarray) -> bool:
    """Maximization: a dominates b iff a >= b everywhere and > somewhere."""
    return bool(np.all(a >= b) and np.any(a > b))


def fast_non_dominated_sort(fitness: np.ndarray) -> list[list[int]]:
    n = len(fitness)
    S = [[] for _ in range(n)]
    dom_count = np.zeros(n, dtype=int)
    fronts: list[list[int]] = [[]]
    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if dominates(fitness[p], fitness[q]):
                S[p].append(q)
            elif dominates(fitness[q], fitness[p]):
                dom_count[p] += 1
        if dom_count[p] == 0:
            fronts[0].append(p)
    i = 0
    while fronts[i]:
        nxt: list[int] = []
        for p in fronts[i]:
            for q in S[p]:
                dom_count[q] -= 1
                if dom_count[q] == 0:
                    nxt.append(q)
        i += 1
        if nxt:
            fronts.append(nxt)
        else:
            break
    return [f for f in fronts if f]


def das_dennis_reference_directions(n_obj: int, divisions: int) -> np.ndarray:
    """Uniformly spaced reference directions on the unit simplex."""
    def gen(m, p, left, cur, out):
        if m == 1:
            out.append(cur + [left / p])
            return
        for i in range(left + 1):
            gen(m - 1, p, left - i, cur + [i / p], out)
    out: list[list[float]] = []
    gen(n_obj, divisions, divisions, [], out)
    return np.array(out, dtype=float)


def normalize(fitness: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Translate so the per-axis ideal is 0, then scale by the intercepts of
    the hyperplane through the per-axis extreme points (NSGA-III style).
    Degenerate planes fall back to per-axis span scaling."""
    ideal = fitness.max(axis=0)
    span = np.maximum(ideal - fitness.min(axis=0), 1e-12)
    extremes = [int(np.argmax(fitness[:, j])) for j in range(fitness.shape[1])]
    plane = fitness[extremes]
    eps = 1e-12
    try:
        intercepts = np.abs(np.linalg.solve(plane - ideal, np.ones(fitness.shape[1])))
    except np.linalg.LinAlgError:
        intercepts = span
    intercepts = np.where(np.isfinite(intercepts) & (intercepts > eps), intercepts, span)
    intercepts = np.where(intercepts > eps, intercepts, span)
    return (fitness - ideal) / intercepts, ideal, intercepts


def associate(z_norm: np.ndarray, ref_dirs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Associate each point to the nearest reference direction (perpendicular
    distance). Returns (ref_index, distance)."""
    ref_norm = np.linalg.norm(ref_dirs, axis=1, keepdims=True)
    ref_norm = np.where(ref_norm == 0, 1e-12, ref_norm)
    unit = ref_dirs / ref_norm
    proj = (z_norm @ unit.T)  # n x r
    dists = np.sqrt(np.maximum(
        (z_norm ** 2).sum(axis=1, keepdims=True) - proj ** 2, 0.0))
    return dists.argmin(axis=1), dists.min(axis=1)


def niching(front: list[int], n_select: int, ref_idx: np.ndarray,
            rng: np.random.Generator) -> list[int]:
    """Niche-count based selection from the last (partially admitted) front."""
    selected: list[int] = []
    niche_counts: dict[int, int] = {}
    remaining = list(front)
    while len(selected) < n_select and remaining:
        # rarest niche among remaining
        counts = [(niche_counts.get(ref_idx[i], 0), i) for i in remaining]
        min_count = min(c for c, _ in counts)
        candidates = [i for c, i in counts if c == min_count]
        pick = candidates[int(rng.integers(len(candidates)))]
        selected.append(pick)
        remaining.remove(pick)
        niche_counts[ref_idx[pick]] = niche_counts.get(ref_idx[pick], 0) + 1
    return selected


def nsga3_select(fitness: np.ndarray, n_select: int,
                 rng: np.random.Generator, divisions: int = 1) -> list[int]:
    """Full NSGA-III environmental selection. Returns selected indices."""
    fronts = fast_non_dominated_sort(fitness)
    selected: list[int] = []
    for front in fronts:
        if len(selected) + len(front) <= n_select:
            selected.extend(front)
        else:
            ref_dirs = das_dennis_reference_directions(fitness.shape[1], divisions)
            z_norm, _ideal, _i = normalize(fitness)
            ref_idx, _dist = associate(z_norm, ref_dirs)
            need = n_select - len(selected)
            # account niches already covered by selected points
            pre_counts: dict[int, int] = {}
            for i in selected:
                pre_counts[ref_idx[i]] = pre_counts.get(ref_idx[i], 0) + 1
            chosen = niching_with_counts(front, need, ref_idx, pre_counts, rng)
            selected.extend(chosen)
            break
    return selected


def niching_with_counts(front, need, ref_idx, pre_counts, rng):
    selected: list[int] = []
    counts = dict(pre_counts)
    remaining = list(front)
    while len(selected) < need and remaining:
        cands = [(counts.get(ref_idx[i], 0), i) for i in remaining]
        min_c = min(c for c, _ in cands)
        pool = [i for c, i in cands if c == min_c]
        pick = pool[int(rng.integers(len(pool)))]
        selected.append(pick)
        remaining.remove(pick)
        counts[ref_idx[pick]] = counts.get(ref_idx[pick], 0) + 1
    return selected


def hypervolume_2d_reference(points: np.ndarray, reference: np.ndarray) -> float:
    """Exact hypervolume (maximization) above `reference`, via recursive
    dimension sweep. Correct for any dimensionality; fine for our small
    fronts. Points below the reference on any axis are excluded."""
    pts = np.asarray(points, dtype=float)
    ref = np.asarray(reference, dtype=float)
    if len(pts) == 0:
        return 0.0
    pts = pts[np.all(pts >= ref, axis=1)]
    if len(pts) == 0:
        return 0.0
    return float(_hv(pts - ref))


def _hv(pts: np.ndarray) -> float:
    """Hypervolume of pts (all >= 0, maximization) above the origin."""
    if len(pts) == 0:
        return 0.0
    if pts.shape[1] == 1:
        return float(pts[:, 0].max())
    order = np.argsort(pts[:, -1])  # ascending along last objective
    pts = pts[order]
    hv = 0.0
    prev = 0.0
    for i in range(len(pts)):
        width = pts[i, -1] - prev
        if width > 0:
            # slab [prev, pts[i, -1]] is covered by points pts[i:]
            hv += width * _hv(pts[i:, :-1])
        prev = pts[i, -1]
    return hv
