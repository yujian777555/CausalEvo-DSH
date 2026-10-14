"""Population + fitness tests (P3.2-S2/S3)."""

import numpy as np
import pytest

from causalevo.evolution.fitness import (
    FitnessCache,
    fitness_from_measurements,
)
from causalevo.evolution.genome import GENES, InterventionGenome
from causalevo.evolution.population import RULE_SEED_GENOMES, Population


def test_population_initialize_size_and_ids():
    pop = Population.initialize(8, np.random.default_rng(0))
    assert len(pop) == 8
    assert len({i.individual_id for i in pop.individuals}) == 8


def test_population_seeded_with_rule_genomes():
    pop = Population.initialize(8, np.random.default_rng(0))
    genomes = [i.genome.genes for i in pop.individuals]
    assert InterventionGenome(tuple(0 for _ in GENES)).genes in genomes  # identity seed


def test_population_rejects_duplicate_ids():
    from causalevo.evolution.population import Individual
    g = InterventionGenome(tuple(0 for _ in GENES))
    with pytest.raises(ValueError):
        Population([Individual(g, 0, "x", []), Individual(g, 0, "x", [])])


def test_population_reproducible_with_seed():
    a = Population.initialize(8, np.random.default_rng(11))
    b = Population.initialize(8, np.random.default_rng(11))
    assert [i.genome.genes for i in a.individuals] == [i.genome.genes for i in b.individuals]


def test_fitness_from_measurements():
    rows = [
        {"success_delta": 1, "cost_delta_cny": 0.001, "extra_calls": 2, "cf_success": True},
        {"success_delta": 0, "cost_delta_cny": 0.0, "extra_calls": 0, "cf_success": False},
    ]
    f = fitness_from_measurements(rows)
    assert f[0] == pytest.approx(0.5)     # success gain
    assert f[1] == pytest.approx(-0.0005)  # neg cost
    assert f[2] == pytest.approx(-1.0)     # neg steps
    assert f[3] == pytest.approx(0.5)      # robustness


def test_fitness_empty_rejected():
    with pytest.raises(ValueError):
        fitness_from_measurements([])


def test_fitness_cache_roundtrip(tmp_path):
    cache = FitnessCache(tmp_path / "cache.jsonl")
    g = InterventionGenome(tuple(0 for _ in GENES))
    cache.put(g, [0.1, -0.2, -3.0, 0.4])
    cache2 = FitnessCache(tmp_path / "cache.jsonl")
    assert cache2.get(g) == [0.1, -0.2, -3.0, 0.4]


def test_fitness_cache_no_double_write(tmp_path):
    path = tmp_path / "cache.jsonl"
    cache = FitnessCache(path)
    g = InterventionGenome(tuple(0 for _ in GENES))
    cache.put(g, [0.1, 0, 0, 0])
    cache.put(g, [9.9, 9, 9, 9])
    assert len(path.read_text().splitlines()) == 1
