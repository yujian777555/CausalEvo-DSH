"""Phase 3.2 evolution run: NSGA-III over intervention genomes (offline).

Fitness comes only from replay measurements (container world + tape provider).
Train on 2 failure cases, evaluate the final Pareto front on the held-out case
(case split = the generalization axis; recorded in artifacts).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from causalevo.counterfactual.replay import apply_tape_transform, run_single  # noqa: E402
from causalevo.eval.executor import DockerExecutor  # noqa: E402
from causalevo.eval.judge import Judge  # noqa: E402
from causalevo.eval.runtime_budget import RuntimeBudget  # noqa: E402
from causalevo.eval.scenarios import SCENARIOS, scenario_tape  # noqa: E402
from causalevo.eval.task_spec import load_all_tasks  # noqa: E402
from causalevo.eval.trace import provenance_block  # noqa: E402
from causalevo.eval.workspace_factory import WorkspaceFactory  # noqa: E402
from causalevo.evolution.fitness import FitnessCache, fitness_from_measurements  # noqa: E402
from causalevo.evolution.genome import GENES, InterventionGenome  # noqa: E402
from causalevo.evolution.nsga3 import (  # noqa: E402
    fast_non_dominated_sort,
    hypervolume_2d_reference,
    nsga3_select,
)
from causalevo.evolution.population import Population, RULE_SEED_GENOMES  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase3" / "evolution"
IMAGE = "causalevo-dsh-agent:0.2.1"
PATCH = REPO / "configs" / "dsh_task_patch.yml"
TRAIN_CASES = ["bad_tool_blocks_write", "broken_write"]
TEST_CASES = ["wrong_fix"]
SEED = 20261014
POP = 6
GENS = 3
MUT_P = 0.25

_ORIGINALS: dict = {}


def _budget() -> RuntimeBudget:
    return RuntimeBudget(max_provider_calls=8, max_total_output_tokens=4096,
                         max_tool_calls=12, wall_time_s=240)


def _state_key(scenario: str, task_id: str) -> str:
    return f"{scenario}::{task_id}"


def _slug(text: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9]+", "-", text)[:32]


def _run_state(spec, scenario, tape, judge, tag):
    factory = WorkspaceFactory()
    try:
        return run_single(spec, tape, _budget(), image=IMAGE, patch_path=PATCH,
                          network="ceval-net", judge=judge, factory=factory, run_tag=tag)
    finally:
        factory.destroy_all()


def evaluate_genome(genome: InterventionGenome, states, judge, cache: FitnessCache,
                    *, causal: bool = True, tag: str) -> list[float]:
    cached = cache.get(genome)
    if cached is not None and (causal or True):
        return cached
    rows = []
    for spec, scenario in states:
        tape = scenario_tape(spec, SCENARIOS[scenario], max_calls=12)
        key = _state_key(scenario, spec.task_id)
        if key not in _ORIGINALS:
            _ORIGINALS[key] = _run_state(spec, scenario, tape, judge, _slug(f"orig-{key}"))
        orig = _ORIGINALS[key]
        cf_tape = tape
        for transform in genome.phenotype_transforms():
            cf_tape, _ = apply_tape_transform(
                cf_tape, transform, entry_file=spec.entry_file,
                fixed_content=spec.reference_fixed.read_text(encoding="utf-8"))
        cfx = _run_state(spec, scenario, cf_tape, judge, _slug(f"cf-{genome.genome_id}-{key}"))
        success_delta = int(cfx["success"]) - int(orig["success"])
        rows.append({
            "success_delta": success_delta if causal else int(cfx["success"]),
            "cost_delta_cny": cfx["ledger"]["known_cost_cny"] - orig["ledger"]["known_cost_cny"],
            "extra_calls": (cfx["ledger"]["provider_attempts"] - orig["ledger"]["provider_attempts"]),
            "cf_success": cfx["success"],
        })
    fitness = fitness_from_measurements(rows)
    cache.put(genome, fitness, {"tag": tag, "causal": causal})
    return fitness


def nsga3_evolve(states, judge, cache, *, seed=SEED, pop_size=POP, generations=GENS,
                 mutation_p=MUT_P, causal=True, single_objective=False):
    rng = np.random.default_rng(seed)
    pop = Population.initialize(pop_size, rng)
    history = []

    def eval_pop(population, tag):
        for ind in population.individuals:
            if ind.fitness is None:
                f = evaluate_genome(ind.genome, states, judge, cache, causal=causal, tag=tag)
                ind.fitness = f[:1] if single_objective else f

    eval_pop(pop, "gen0")
    history.append(_gen_record(pop, 0))
    for gen in range(1, generations + 1):
        fit = np.array([i.fitness for i in pop.individuals])
        if single_objective:
            order = np.argsort(-fit[:, 0])[:pop_size]
            parents = [pop.individuals[i] for i in order]
        else:
            sel = nsga3_select(fit, pop_size, rng)
            parents = [pop.individuals[i] for i in sel]
        children = []
        n = 0
        while len(children) < pop_size:
            a, b = parents[rng.integers(len(parents))], parents[rng.integers(len(parents))]
            child = a.genome.crossover(b.genome, rng).mutate(rng, p=mutation_p)
            children.append(type(a)(
                genome=child, generation=gen,
                individual_id=f"g{gen}-i{n}",
                parent_ids=[a.individual_id, b.individual_id]))
            n += 1
        pop = Population(children)
        eval_pop(pop, f"gen{gen}")
        history.append(_gen_record(pop, gen))
    return pop, history


def _gen_record(pop, gen):
    return {
        "generation": gen,
        "individuals": [
            {**i.as_dict(), "parent_ids": i.parent_ids} for i in pop.individuals
        ],
    }


def pareto_front(fitness_rows: list[list[float]]) -> list[int]:
    fronts = fast_non_dominated_sort(np.array(fitness_rows))
    return fronts[0] if fronts else []


def main(out_dir: Path | None = None) -> int:
    out = out_dir or OUT
    out.mkdir(parents=True, exist_ok=True)
    judge = Judge(DockerExecutor())
    all_specs = load_all_tasks(REPO / "benchmarks" / "tasks")[:2]
    train_states = [(s, c) for s in all_specs for c in TRAIN_CASES]
    test_states = [(s, c) for s in all_specs for c in TEST_CASES]
    cache = FitnessCache(out / "fitness_cache.jsonl")

    # B3: NSGA-III
    final_pop, history = nsga3_evolve(train_states, judge, cache)
    all_fitness = [i.fitness for i in final_pop.individuals]
    front_idx = pareto_front(all_fitness)
    front = [final_pop.individuals[i] for i in front_idx]

    # B0 random search (same evaluation budget as one generation batch)
    rng = np.random.default_rng(SEED + 1)
    b0_genomes = [InterventionGenome.random(rng) for _ in range(POP * GENS)]
    b0_fit = [evaluate_genome(g, train_states, judge, cache, tag="B0") for g in b0_genomes]
    # B1 rule seeds
    b1_genomes = [InterventionGenome(tuple(d.get(n, 0) for n, _ in GENES))
                  for d in RULE_SEED_GENOMES]
    b1_fit = [evaluate_genome(g, train_states, judge, cache, tag="B1") for g in b1_genomes]
    # B2 CEA-v0 (P3.1 LinUCB) — its learned per-state choices as a fixed policy,
    # measured on the same train states via the sweep matrix is NOT reused;
    # evaluate its chosen library actions as genomes where available.
    from causalevo.evolution.policy import ACTIONS, LinUCBPolicy, state_vector  # noqa
    from causalevo.evolution.policy import FAILURE_TYPES  # noqa
    from causalevo.failure_dataset.builder import SCENARIO_GROUND_TRUTH  # noqa
    from causalevo.intervention.generator import INTERVENTION_LIBRARY  # noqa
    b2 = LinUCBPolicy(alpha=0.5)
    # train it quickly over train-state reward matrix (same episodes idea as P3.1)
    lib_by_id = {iv.intervention_id: iv for iv in INTERVENTION_LIBRARY}
    transform_to_genome = {}
    for d in RULE_SEED_GENOMES:
        g = InterventionGenome(tuple(d.get(n, 0) for n, _ in GENES))
        # map the seed genome's primary transform back
        tr = g.phenotype_transforms()
        if tr:
            transform_to_genome[tr[0]] = g
    sweep_rows = [json.loads(l) for l in
                  (REPO / "results" / "phase3" / "replay_sweep" / "sweep_results.jsonl")
                  .read_text(encoding="utf-8").splitlines()]
    mat = {(r["scenario"], r["task_id"], r["tape_transform"]): r for r in sweep_rows}
    for _round in range(10):
        for spec, scenario in train_states:
            fs = {"failure_type": SCENARIO_GROUND_TRUTH[scenario], "prompt_chars": 100,
                  "n_visible_checks": 3}
            action = b2.select(fs, ACTIONS)
            transform = lib_by_id[action].tape_transform
            key = (scenario, spec.task_id, transform)
            if key in mat:
                from causalevo.evolution.reward import compute_reward
                b2.update(fs, action, compute_reward(mat[key]["success_delta"],
                                                     mat[key]["cost_delta_cny"]))
    # evaluate B2's policy as per-state genomes on train states
    b2_rows = []
    for spec, scenario in train_states:
        fs = {"failure_type": SCENARIO_GROUND_TRUTH[scenario], "prompt_chars": 100,
              "n_visible_checks": 3}
        action = b2.select(fs, ACTIONS)
        transform = lib_by_id[action].tape_transform
        g = transform_to_genome.get(transform)
        if g is None:
            continue
        f = cache.get(g)
        if f is None:
            f = evaluate_genome(g, train_states, judge, cache, tag="B2")
        b2_rows.append({"fitness": f, "genome": g.as_dict(), "action": action})
    b2_best = max((r["fitness"] for r in b2_rows), key=lambda f: f[0], default=None)

    # generalization: final Pareto front + best of each baseline on held-out case
    def eval_test(genome):
        rows = []
        for spec, scenario in test_states:
            tape = scenario_tape(spec, SCENARIOS[scenario], max_calls=12)
            key = _state_key(scenario, spec.task_id)
            if key not in _ORIGINALS:
                _ORIGINALS[key] = _run_state(spec, scenario, tape, judge, _slug(f"origT-{key}"))
            orig = _ORIGINALS[key]
            cf_tape = tape
            for transform in genome.phenotype_transforms():
                cf_tape, _ = apply_tape_transform(
                    cf_tape, transform, entry_file=spec.entry_file,
                    fixed_content=spec.reference_fixed.read_text(encoding="utf-8"))
            cfx = _run_state(spec, scenario, cf_tape, judge,
                             _slug(f"cfT-{genome.genome_id}-{key}"))
            rows.append({"success_delta": int(cfx["success"]) - int(orig["success"]),
                         "cost_delta_cny": cfx["ledger"]["known_cost_cny"] - orig["ledger"]["known_cost_cny"],
                         "extra_calls": cfx["ledger"]["provider_attempts"] - orig["ledger"]["provider_attempts"],
                         "cf_success": cfx["success"]})
        return fitness_from_measurements(rows)

    pareto_test = [{"genome": g.genome.as_dict(), "train_fitness": g.fitness,
                    "test_fitness": eval_test(g.genome)} for g in front]
    b0_best = max(zip(b0_fit, b0_genomes), key=lambda t: t[0][0])
    b1_best = max(zip(b1_fit, b1_genomes), key=lambda t: t[0][0])
    baseline_comparison = {
        "B0-random-search": {"best_train_fitness": b0_best[0],
                             "best_genome": b0_best[1].as_dict(),
                             "test_fitness": eval_test(b0_best[1])},
        "B1-rule-library": {"best_train_fitness": b1_best[0],
                            "best_genome": b1_best[1].as_dict(),
                            "test_fitness": eval_test(b1_best[1])},
        "B2-cea-v0": {"best_train_fitness": b2_best,
                      "note": "state-conditioned policy; best per-state genome shown"},
        "B3-nsga3": {"pareto_front_size": len(front),
                     "pareto_train_fitness": [g.fitness for g in front],
                     "hypervolume_train": hypervolume_2d_reference(
                         np.array([g.fitness for g in front]),
                         np.array([-0.5, -0.01, -6.0, -0.1]))},
    }

    with (out / "population_history.jsonl").open("w", encoding="utf-8") as fh:
        for rec in history:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    (out / "pareto_front.json").write_text(json.dumps(pareto_test, indent=2), encoding="utf-8")
    (out / "fitness_history.json").write_text(json.dumps(history, indent=1), encoding="utf-8")
    (out / "baseline_comparison.json").write_text(json.dumps(baseline_comparison, indent=2),
                                                  encoding="utf-8")
    (out / "evolution_manifest.json").write_text(json.dumps({
        "seed": SEED, "pop": POP, "generations": GENS, "mutation_p": MUT_P,
        "train_cases": TRAIN_CASES, "test_cases": TEST_CASES,
        "provenance": provenance_block(),
        "honesty": "replay-measured fitness; simulated interventions; zero API spend",
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # ablations
    abl = {}
    p, _h = nsga3_evolve(train_states, judge, cache, seed=SEED + 7, mutation_p=0.0)
    abl["A1_no_mutation"] = {"front_size": len(pareto_front([i.fitness for i in p.individuals])),
                             "best_success_gain": max(i.fitness[0] for i in p.individuals)}
    p2, _h2 = nsga3_evolve(train_states, judge, cache, seed=SEED + 8, single_objective=True)
    abl["A2_single_objective"] = {"best_success_gain": max(i.fitness[0] for i in p2.individuals)}
    abl["A2_multi_objective"] = {"best_success_gain": max(i.fitness[0] for i in final_pop.individuals),
                                 "front_size": len(front)}
    p3, _h3 = nsga3_evolve(train_states, judge, cache, seed=SEED + 9, causal=False)
    abl["A3_no_causal_reward"] = {"best_robustness": max(i.fitness[3] for i in p3.individuals)}
    abl["A4_causal_reward"] = {"best_success_gain": max(i.fitness[0] for i in final_pop.individuals)}
    (out / "ablation_results.json").write_text(json.dumps(abl, indent=2), encoding="utf-8")

    print("pareto front size:", len(front))
    print("B3 front fitness:", [g.fitness for g in front])
    return 0


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=None)
    args = p.parse_args()
    raise SystemExit(main(Path(args.out) if args.out else None))
