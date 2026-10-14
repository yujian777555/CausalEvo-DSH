"""Population with lineage (P3.2-S2)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .genome import GENES, InterventionGenome

# Rule interventions from Phase 2.3 as seed genomes (hand-set genes matching
# their transforms; identity genome = all zeros is the no-op).
RULE_SEED_GENOMES: list[dict[str, int]] = [
    {"tool_validation": 1},                                  # lib:tool_failure
    {"read_before_write": 1},                                # lib:planning_failure
    {"verification_level": 1},                               # lib:verification_failure
    {"stagnation_break": 1},                                 # lib:strategy_failure
    {"verification_level": 1, "read_before_write": 1},       # knowledge-ish combo
    {},                                                      # identity / no-op
]


def _from_partial(d: dict[str, int]) -> InterventionGenome:
    return InterventionGenome(tuple(int(d.get(name, 0)) for name, _ in GENES))


@dataclass(slots=True)
class Individual:
    genome: InterventionGenome
    generation: int
    individual_id: str
    parent_ids: list[str]
    fitness: list[float] | None = None  # objective vector (maximized orientation)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["genome"] = self.genome.as_dict()
        d["genome_id"] = self.genome.genome_id
        return d


class Population:
    def __init__(self, individuals: list[Individual]) -> None:
        ids = [i.individual_id for i in individuals]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate individual_id")
        self.individuals = individuals

    @classmethod
    def initialize(cls, size: int, rng: np.random.Generator,
                   generation: int = 0) -> "Population":
        """Seed from the rule genomes, fill the rest with random combinations."""
        individuals = []
        n = 0
        for d in RULE_SEED_GENOMES:
            if n >= size:
                break
            individuals.append(Individual(_from_partial(d), generation, f"g{generation}-i{n}", []))
            n += 1
        seen = {i.genome.genes for i in individuals}
        while n < size:
            g = InterventionGenome.random(rng)
            if g.genes in seen:
                continue
            seen.add(g.genes)
            individuals.append(Individual(g, generation, f"g{generation}-i{n}", []))
            n += 1
        return cls(individuals)

    def __len__(self) -> int:
        return len(self.individuals)
