"""Evolution artifacts + offline loop tests (P3.2)."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from causalevo.evolution.genome import GENES, InterventionGenome
from causalevo.evolution.nsga3 import fast_non_dominated_sort
from causalevo.evolution.population import Population

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase3" / "evolution"


def test_artifacts_exist():
    for name in ("population_history.jsonl", "pareto_front.json",
                 "fitness_history.json", "baseline_comparison.json",
                 "ablation_results.json", "evolution_manifest.json",
                 "fitness_cache.jsonl"):
        assert (OUT / name).is_file(), name


def test_population_history_schema():
    rows = [json.loads(l) for l in
            (OUT / "population_history.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) >= 2  # gen0 + at least gen1
    for gen in rows:
        assert "generation" in gen and "individuals" in gen
        for ind in gen["individuals"]:
            assert {"individual_id", "parent_ids", "fitness", "genome", "genome_id"} <= set(ind)
            assert ind["fitness"] is None or len(ind["fitness"]) == 4


def test_lineage_gen1_children_have_parents():
    rows = [json.loads(l) for l in
            (OUT / "population_history.jsonl").read_text(encoding="utf-8").splitlines()]
    gen1 = next(r for r in rows if r["generation"] == 1)
    for ind in gen1["individuals"]:
        assert len(ind["parent_ids"]) == 2


def test_pareto_front_members_nondominated():
    front = json.loads((OUT / "pareto_front.json").read_text(encoding="utf-8"))
    assert front
    fit = np.array([f["train_fitness"] for f in front])
    fronts = fast_non_dominated_sort(fit)
    assert set(fronts[0]) == set(range(len(fit))), "front contains dominated members"


def test_baseline_comparison_arms():
    comp = json.loads((OUT / "baseline_comparison.json").read_text(encoding="utf-8"))
    assert {"B0-random-search", "B1-rule-library", "B2-cea-v0", "B3-nsga3"} <= set(comp)
    assert comp["B3-nsga3"]["pareto_front_size"] >= 1
    assert comp["B3-nsga3"]["hypervolume_train"] >= 0


def test_ablation_arms():
    abl = json.loads((OUT / "ablation_results.json").read_text(encoding="utf-8"))
    assert {"A1_no_mutation", "A2_single_objective", "A2_multi_objective",
            "A3_no_causal_reward", "A4_causal_reward"} <= set(abl)


def test_fitness_cache_consistent_with_history():
    cache_rows = [json.loads(l) for l in
                  (OUT / "fitness_cache.jsonl").read_text(encoding="utf-8").splitlines()]
    hist = [json.loads(l) for l in
            (OUT / "population_history.jsonl").read_text(encoding="utf-8").splitlines()]
    cached = {r["genome_id"]: r["fitness"] for r in cache_rows}
    for gen in hist:
        for ind in gen["individuals"]:
            if ind["genome_id"] in cached:
                assert cached[ind["genome_id"]] == ind["fitness"]


def test_mini_evolution_loop_progresses_without_docker():
    """Synthetic-fitness smoke of the NSGA loop (no containers): selection +
    variation must not crash and must keep population size."""
    from causalevo.evolution.nsga3 import nsga3_select
    rng = np.random.default_rng(0)
    pop = Population.initialize(6, rng)
    for gen in range(3):
        for ind in pop.individuals:
            # synthetic fitness: prefer more 1-genes, deterministic
            ind.fitness = [float(sum(ind.genome.genes)), 0.0, -float(gen), 0.5]
        fit = np.array([i.fitness for i in pop.individuals])
        sel = nsga3_select(fit, len(pop), rng)
        parents = [pop.individuals[i] for i in sel]
        children = []
        for n in range(len(pop)):
            a, b = parents[rng.integers(len(parents))], parents[rng.integers(len(parents))]
            children.append(type(pop.individuals[0])(
                genome=a.genome.crossover(b.genome, rng).mutate(rng, p=0.2),
                generation=gen + 1, individual_id=f"g{gen+1}-i{n}",
                parent_ids=[a.individual_id, b.individual_id]))
        pop = Population(children)
    assert len(pop) == 6


def test_evolution_rerun_deterministic(tmp_path):
    """Same seed + warm fitness cache -> same final Pareto front (train fitness).
    The cache copy makes this a determinism check of the selection logic
    without re-running containers."""
    import shutil
    shutil.copyfile(OUT / "fitness_cache.jsonl", tmp_path / "fitness_cache.jsonl")
    before = json.loads((OUT / "baseline_comparison.json").read_text(encoding="utf-8"))
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "run_evolution.py"),
                           "--out", str(tmp_path)],
                          capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr[-400:]
    after = json.loads((tmp_path / "baseline_comparison.json").read_text(encoding="utf-8"))
    assert before["B3-nsga3"]["pareto_train_fitness"] == after["B3-nsga3"]["pareto_train_fitness"]


def test_manifest_records_split_and_seed():
    m = json.loads((OUT / "evolution_manifest.json").read_text(encoding="utf-8"))
    assert m["seed"] == 20261014
    assert m["train_cases"] != m["test_cases"]
    assert set(m["test_cases"]) & set(m["train_cases"]) == set()


def test_pareto_front_has_test_fitness():
    front = json.loads((OUT / "pareto_front.json").read_text(encoding="utf-8"))
    for member in front:
        assert member["test_fitness"] is not None
        assert len(member["test_fitness"]) == 4


def test_fitness_objective_orientation():
    """neg_cost <= 0 and neg_steps <= 0 for every evaluated genome."""
    rows = [json.loads(l) for l in
            (OUT / "fitness_cache.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows
    for r in rows:
        assert r["fitness"][1] <= 0
        assert r["fitness"][2] <= 0


def test_genome_covers_all_transform_names():
    """Every gene's transform maps to a real tape transform accepted by replay."""
    from causalevo.counterfactual.replay import apply_tape_transform
    names = [n for n, _hi in GENES]
    for name, hi in GENES:
        g = InterventionGenome.from_dict({n: (hi if n == name else 0) for n in names})
        for transform in g.phenotype_transforms():
            apply_tape_transform({"0": [["text", "x"]]}, transform,
                                 entry_file="s.py", fixed_content="f")  # must not raise

