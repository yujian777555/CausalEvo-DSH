"""Online evolutionary controller (CEA-v2; CE-DSH-P4-R1.8 Task B / R1.9 Task A).

A genuine runtime L2/L3 loop: settled episode outcomes (independent judge +
accounting ledger) update context-conditioned statistics, and a bounded
evolutionary step (NSGA-III parent selection + crossover/mutation over
effective-phenotype-deduplicated candidates) changes later selections.

Frozen design: docs/PHASE4_R1_8_ONLINE_EVOLUTION_DESIGN.md. NOT L4 recursive
self-improvement: operators and the evaluator are fixed.

Fail-closed rules: manifest mismatch at load; duplicate episode_id; unknown
cost; infra outcomes produce no behavioral update and no retry.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .genome import InterventionGenome
from .nsga3 import nsga3_select

CONTROLLER_VERSION = "cea-v2-r1.8"
INFRA_KINDS = ("unknown_cost", "budget_stop", "transport", "protocol")

DEFAULT_CONFIG: dict[str, Any] = {
    "max_population": 16,
    "update_every": 4,
    "mutation_p": 0.25,
    "n_offspring": 4,
    "exploration_beta": 0.05,
    "lambda_cost": 50.0,
    "lambda_calls": 0.02,
    "seed": 20261021,
}


class OnlineEvolutionError(RuntimeError):
    pass


def effective_phenotype(genome: InterventionGenome) -> tuple[str, ...]:
    """The phenotype identity: ordered tape transforms. Reserved genes
    (reflection_step, retry_strategy) have no phenotype effect and therefore
    do not inflate diversity (disclosed, not counted)."""
    return tuple(genome.phenotype_transforms())


class _Candidate:
    __slots__ = ("genome", "parent_ids", "born_generation", "n", "successes",
                 "costs", "calls", "ctx_n", "ctx_successes")

    def __init__(self, genome: InterventionGenome, parent_ids: list[str],
                 born_generation: int) -> None:
        self.genome = genome
        self.parent_ids = list(parent_ids)
        self.born_generation = born_generation
        self.n = 0
        self.successes = 0
        self.costs = 0.0
        self.calls = 0
        self.ctx_n: dict[str, int] = {}
        self.ctx_successes: dict[str, int] = {}

    @property
    def genome_id(self) -> str:
        return self.genome.genome_id

    @property
    def phenotype(self) -> tuple[str, ...]:
        return effective_phenotype(self.genome)

    @property
    def measured(self) -> bool:
        return self.n > 0

    def fitness_vector(self) -> list[float] | None:
        if not self.measured:
            return None
        return [self.successes / self.n,
                -(self.costs / self.n),
                -(self.calls / self.n)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "genome": self.genome.as_dict(), "genome_id": self.genome_id,
            "phenotype": list(self.phenotype), "parent_ids": self.parent_ids,
            "born_generation": self.born_generation, "n": self.n,
            "successes": self.successes, "costs": self.costs,
            "calls": self.calls, "ctx_n": dict(self.ctx_n),
            "ctx_successes": dict(self.ctx_successes),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "_Candidate":
        c = cls(InterventionGenome.from_dict(d["genome"]), d["parent_ids"],
                d["born_generation"])
        c.n = d["n"]
        c.successes = d["successes"]
        c.costs = d["costs"]
        c.calls = d["calls"]
        c.ctx_n = dict(d["ctx_n"])
        c.ctx_successes = dict(d["ctx_successes"])
        return c


class OnlineEvolutionController:
    """Bounded online evolutionary controller over intervention genomes."""

    def __init__(self, *, pareto_front_path: Path, manifest_path: Path,
                 config: dict[str, Any] | None = None) -> None:
        from .adapter import canonical_sha256  # manifest-pinned load
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.rng = np.random.default_rng(self.config["seed"])
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        rel = "results/phase3/evolution/pareto_front.json"
        entry = manifest.get("artifacts", {}).get(rel)
        if entry is None:
            raise OnlineEvolutionError(f"{rel} not pinned in the manifest")
        actual = canonical_sha256(pareto_front_path)
        if actual != entry["sha256"].strip().lower():
            raise OnlineEvolutionError(
                "pareto front hash mismatch with frozen manifest; refusing to "
                "initialize the online controller from an unpinned artifact")
        front = json.loads(Path(pareto_front_path).read_text(encoding="utf-8"))
        self.population: list[_Candidate] = []
        seen_phenotypes: set[tuple[str, ...]] = set()
        for member in front:
            g = InterventionGenome.from_dict(member["genome"])
            ph = effective_phenotype(g)
            if ph in seen_phenotypes:
                continue  # dedupe by EFFECTIVE phenotype (not genome_id)
            seen_phenotypes.add(ph)
            self.population.append(_Candidate(g, parent_ids=[], born_generation=0))
        if not self.population:
            raise OnlineEvolutionError("empty deduplicated candidate set")
        self.policy_version = CONTROLLER_VERSION
        self.population_version = 0
        self.generation = 0
        self.events: list[dict[str, Any]] = []
        self._episode_seen: set[str] = set()
        self._pending_observations = 0
        self._stopped: str | None = None
        self.evolution_updates = 0

    # ---------- selection ----------
    def _score(self, c: _Candidate, failure_type: str) -> float:
        cfg = self.config
        if c.ctx_n.get(failure_type, 0) > 0:
            rate = ((c.ctx_successes.get(failure_type, 0) + 1)
                    / (c.ctx_n[failure_type] + 2))  # Laplace
        elif c.measured:
            rate = (c.successes + 1) / (c.n + 2)
        else:
            rate = 0.5  # unmeasured prior (never treated as proven optimal)
        score = rate + (cfg["exploration_beta"] if not c.measured else 0.0)
        if c.measured:
            score -= cfg["lambda_cost"] * (c.costs / c.n)
            score -= cfg["lambda_calls"] * (c.calls / c.n)
        return score

    def select(self, context: dict[str, Any], episode_id: str) -> dict[str, Any]:
        if self._stopped:
            raise OnlineEvolutionError(f"controller stopped: {self._stopped}")
        ft = str(context.get("failure_type", "unknown"))
        best = max(self.population,
                   key=lambda c: (self._score(c, ft), c.genome_id))
        reason = (f"score={self._score(best, ft):.4f} ctx={ft} "
                  f"{'unmeasured+explore' if not best.measured else 'measured'}")
        return {
            "genome": best.genome, "genome_id": best.genome_id,
            "phenotype": list(best.phenotype), "reason": reason,
            "policy_version": self.policy_version,
            "population_version": self.population_version,
            "episode_id": episode_id,
        }

    # ---------- observation ----------
    def observe(self, episode_id: str, context: dict[str, Any],
                genome_id: str, outcome: dict[str, Any]) -> dict[str, Any]:
        """Record ONE settled observation. Exactly-once; infra outcomes never
        update behavior statistics; unknown cost stops learning (fail-closed)."""
        if episode_id in self._episode_seen:
            raise OnlineEvolutionError(f"duplicate episode_id {episode_id}")
        if self._stopped:
            raise OnlineEvolutionError(f"controller stopped: {self._stopped}")
        self._episode_seen.add(episode_id)
        failure_kind = outcome.get("failure_kind", "none")
        cost = outcome.get("cost_cny")
        event = {"episode_id": episode_id, "context": dict(context),
                 "genome_id": genome_id, "failure_kind": failure_kind}
        if failure_kind in INFRA_KINDS:
            event["kind"] = "infra"
            self.events.append(event)
            return {"updated": False, "reason": f"infra {failure_kind}: no behavioral update"}
        if cost is None:
            self._stopped = f"unknown cost at episode {episode_id}"
            event["kind"] = "unknown_cost_stop"
            self.events.append(event)
            raise OnlineEvolutionError(self._stopped)
        cand = next((c for c in self.population if c.genome_id == genome_id), None)
        if cand is None:
            raise OnlineEvolutionError(f"observation for unknown genome {genome_id}")
        success = bool(outcome.get("success"))
        calls = int(outcome.get("calls", 0))
        cand.n += 1
        cand.successes += int(success)
        cand.costs += float(cost)
        cand.calls += calls
        ft = str(context.get("failure_type", "unknown"))
        cand.ctx_n[ft] = cand.ctx_n.get(ft, 0) + 1
        cand.ctx_successes[ft] = cand.ctx_successes.get(ft, 0) + int(success)
        event.update({"kind": "behavioral", "success": success,
                      "cost_cny": float(cost), "calls": calls})
        self.events.append(event)
        self._pending_observations += 1
        evolved = False
        if self._pending_observations >= self.config["update_every"]:
            self._evolve()
            self._pending_observations = 0
            evolved = True
        return {"updated": True, "evolved": evolved,
                "population_version": self.population_version}

    # ---------- evolutionary step ----------
    def _evolve(self) -> None:
        cfg = self.config
        measured = [c for c in self.population if c.measured]
        if not measured:
            return
        fit = np.array([c.fitness_vector() for c in measured])
        n_parents = min(4, len(measured))
        if len(measured) > n_parents:
            sel = nsga3_select(fit, n_parents, self.rng)
            parents = [measured[i] for i in sel]
        else:
            parents = measured
        self.generation += 1
        existing_ph = {c.phenotype for c in self.population}
        offspring: list[_Candidate] = []
        # Bounded offspring generation: once the effective-phenotype space is
        # exhausted, further parents cannot yield novel phenotypes — stop
        # instead of looping forever (R1.9 defect CEA-V2-D1: livelock).
        max_attempts = 200
        attempts = 0
        while len(offspring) < cfg["n_offspring"] and attempts < max_attempts:
            attempts += 1
            a = parents[int(self.rng.integers(len(parents)))]
            b = parents[int(self.rng.integers(len(parents)))]
            child_g = a.genome.crossover(b.genome, self.rng).mutate(
                self.rng, p=cfg["mutation_p"])
            child = _Candidate(child_g, parent_ids=[a.genome_id, b.genome_id],
                               born_generation=self.generation)
            if child.phenotype in existing_ph:
                continue  # never let duplicate phenotypes occupy the archive
            existing_ph.add(child.phenotype)
            offspring.append(child)
        self.population.extend(offspring)
        # Bound the archive. Unmeasured offspring get ONE batch of grace, not
        # permanent immunity: over-capacity archives evict by NSGA-III over
        # measured candidates and by age/fitness for the rest, so the
        # phenotype space can never deadlock the controller.
        over = len(self.population) - cfg["max_population"]
        if over > 0:
            measured_now = [c for c in self.population if c.measured]
            unmeasured = [c for c in self.population if not c.measured]
            keep_unmeasured = unmeasured[-cfg["n_offspring"]:]
            keep_n = max(1, cfg["max_population"] - len(keep_unmeasured))
            if len(measured_now) > keep_n:
                fit_now = np.array([c.fitness_vector() for c in measured_now])
                keep_idx = nsga3_select(fit_now, keep_n, self.rng)
                measured_now = [measured_now[i] for i in keep_idx]
            self.population = measured_now + keep_unmeasured
        if len(self.population) > cfg["max_population"]:
            # still over: drop by (unmeasured first, oldest generation first)
            excess = len(self.population) - cfg["max_population"]
            self.population.sort(key=lambda c: (c.measured,
                                                -c.born_generation))
            self.population = self.population[excess:]
        self.population_version += 1
        self.evolution_updates += 1
        self.events.append({"kind": "evolve", "generation": self.generation,
                            "population_version": self.population_version,
                            "offspring": [c.genome_id for c in offspring],
                            "offspring_attempts": attempts,
                            "phenotype_space_exhausted": attempts >= max_attempts,
                            "parents": [p.genome_id for p in parents]})

    # ---------- serialization / replay ----------
    def state_dict(self) -> dict[str, Any]:
        return {
            "controller_version": self.policy_version,
            "config": dict(self.config),
            "config_sha256": hashlib.sha256(
                json.dumps(self.config, sort_keys=True).encode()).hexdigest(),
            "population_version": self.population_version,
            "generation": self.generation,
            "evolution_updates": self.evolution_updates,
            "population": [c.to_dict() for c in self.population],
            "events": len(self.events),
            "stopped": self._stopped,
        }

    def history_up_to(self, episode_index: int) -> dict[str, Any]:
        """A view using ONLY the first `episode_index` behavioral/infra events
        (no future leakage). Indexes the event log, not wall time."""
        return {"events": [e for e in self.events[:episode_index]]}

    @classmethod
    def replay(cls, events_path: Path, **init_kw) -> "OnlineEvolutionController":
        """Deterministic replay: rebuild the controller from its event log."""
        ctl = cls(**init_kw)
        for line in Path(events_path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("kind") in ("behavioral", "infra", "unknown_cost_stop"):
                outcome = {"failure_kind": e["failure_kind"]}
                if e["kind"] == "behavioral":
                    outcome.update({"success": e["success"],
                                    "cost_cny": e["cost_cny"], "calls": e["calls"]})
                else:
                    outcome["cost_cny"] = e.get("cost_cny")
                ctl.observe(e["episode_id"], e["context"], e["genome_id"], outcome)
        return ctl
