"""Genome tests (P3.2-S1/S5)."""

import numpy as np
import pytest

from causalevo.evolution.genome import GENES, InterventionGenome


def test_genome_roundtrip():
    g = InterventionGenome(tuple(1 for _ in GENES))
    assert InterventionGenome.from_json(g.to_json()) == g


def test_genome_range_validation():
    with pytest.raises(ValueError):
        InterventionGenome(tuple(0 for _ in GENES)[:-1])  # wrong length
    with pytest.raises(ValueError):
        InterventionGenome(tuple(9 for _ in GENES))  # out of range
    with pytest.raises(ValueError):
        InterventionGenome(tuple(-1 for _ in GENES))


def test_genome_id_stable():
    g = InterventionGenome(tuple(int(i % 2) for i in range(len(GENES))))
    assert g.genome_id == InterventionGenome(g.genes).genome_id


def test_mutation_never_out_of_range():
    rng = np.random.default_rng(0)
    g = InterventionGenome(tuple(1 for _ in GENES))
    for _ in range(50):
        g.mutate(rng, p=0.9)  # must not raise


def test_mutation_zero_prob_is_identity():
    rng = np.random.default_rng(0)
    g = InterventionGenome(tuple(1 for _ in GENES))
    assert g.mutate(rng, p=0.0) == g


def test_mutation_deterministic_with_seed():
    g = InterventionGenome(tuple(0 for _ in GENES))
    a = g.mutate(np.random.default_rng(7), p=0.5)
    b = g.mutate(np.random.default_rng(7), p=0.5)
    assert a == b


def test_crossover_child_genes_from_parents():
    rng = np.random.default_rng(3)
    a = InterventionGenome(tuple(0 for _ in GENES))
    b = InterventionGenome(tuple(min(1, hi) for _n, hi in GENES))
    child = a.crossover(b, rng)
    for c, (x, y) in zip(child.genes, zip(a.genes, b.genes)):
        assert c in (x, y)


def test_distance_self_zero_and_symmetric():
    a = InterventionGenome(tuple(0 for _ in GENES))
    b = InterventionGenome(tuple(min(1, hi) for _n, hi in GENES))
    assert a.distance(a) == 0.0
    assert a.distance(b) == b.distance(a) > 0


def test_phenotype_identity_for_zero_genome():
    g = InterventionGenome(tuple(0 for _ in GENES))
    assert g.phenotype_transforms() == ["identity"]


def test_phenotype_composition_order():
    base = {n: 0 for n, _h in GENES}
    g = InterventionGenome.from_dict({**base, "tool_validation": 1, "verification_level": 1})
    tr = g.phenotype_transforms()
    assert tr.index("replace_unknown_tool_with_read") < tr.index("append_readback_and_fix")
