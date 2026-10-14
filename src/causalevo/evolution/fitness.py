"""Multi-objective fitness from counterfactual replay (P3.2-S3).

Objectives (maximization orientation: we negate the minimize-axes):
  O1 success_gain  = mean success_delta over failure states      (maximize)
  O2 neg_cost      = -mean cost_delta_cny (synthetic metering)   (minimize cost)
  O3 neg_steps     = -mean extra provider+tool calls             (minimize steps)
  O4 robustness    = mean cf_success over all states             (maximize)

Fitness NEVER comes from a model prediction: only from replay measurements
(the sweep matrix / fresh container runs). A result cache keyed by genome id
keeps evaluation deterministic and cheap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .genome import InterventionGenome

N_OBJECTIVES = 4
OBJECTIVE_NAMES = ("success_gain", "neg_cost", "neg_steps", "robustness")


def fitness_from_measurements(per_state: list[dict[str, Any]]) -> list[float]:
    """per_state: rows with success_delta, cost_delta_cny, extra_calls, cf_success."""
    if not per_state:
        raise ValueError("no measurements")
    n = len(per_state)
    success_gain = sum(r["success_delta"] for r in per_state) / n
    neg_cost = -sum(r["cost_delta_cny"] for r in per_state) / n
    neg_steps = -sum(r["extra_calls"] for r in per_state) / n
    robustness = sum(1.0 if r["cf_success"] else 0.0 for r in per_state) / n
    return [success_gain, neg_cost, neg_steps, robustness]


class FitnessCache:
    """Deterministic genome->fitness cache (JSONL, append-only)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._map: dict[str, list[float]] = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._map[row["genome_id"]] = row["fitness"]

    def get(self, genome: InterventionGenome) -> list[float] | None:
        return self._map.get(genome.genome_id)

    def put(self, genome: InterventionGenome, fitness: list[float],
            detail: dict[str, Any] | None = None) -> None:
        if genome.genome_id in self._map:
            return
        self._map[genome.genome_id] = fitness
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"genome_id": genome.genome_id, "fitness": fitness,
                                 "genome": genome.as_dict(), "detail": detail or {}},
                                ensure_ascii=False, sort_keys=True) + "\n")
