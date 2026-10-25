"""Analysis for the R1.9 four-arm pilot (frozen protocol in
docs/PHASE4_R1_9_EXPERIMENT_PROTOCOL.md).

Primary endpoint: final_success on every (task, seed, arm) row.
Primary comparison: CEA-v2-online vs B1-random (paired McNemar exact +
task-cluster bootstrap 95% CI). Secondary comparisons Holm-corrected.
Secondary descriptive: attempt-1 success, conditional recovery (explicit
denominator), cost/calls/latency, online update counts, phenotype diversity.
Never merges the historical 312 rows. Exploratory label when discordant
pairs are few.
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ARMS = ["B0-original", "B1-random", "B5-v1-frozen-pareto", "CEA-v2-online"]
PRIMARY_A = "CEA-v2-online"
PRIMARY_B = "B1-random"


def mcnemar_exact(disc_pos: int, disc_neg: int) -> float:
    """Two-sided exact binomial p for discordant pairs."""
    n = disc_pos + disc_neg
    if n == 0:
        return 1.0
    k = min(disc_pos, disc_neg)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def paired_diff(rows, arm_a, arm_b):
    """Paired final_success difference over shared (task_id, seed) rows."""
    by_key = defaultdict(dict)
    for r in rows:
        by_key[(r["task_id"], r["seed"])][r["arm"]] = r
    pairs = []
    for key, arms in by_key.items():
        if arm_a in arms and arm_b in arms:
            pairs.append((key, int(bool(arms[arm_a]["final_success"])),
                          int(bool(arms[arm_b]["final_success"]))))
    return pairs


def cluster_bootstrap_ci(pairs, n_boot=10000, seed=20261024):
    """Task-level cluster bootstrap for the paired success-rate difference."""
    if not pairs:
        return (None, None, None)
    by_task = defaultdict(list)
    for key, a, b in pairs:
        by_task[key[0]].append(a - b)
    tasks = sorted(by_task)
    rng = np.random.default_rng(seed)
    diffs = np.array([np.mean(by_task[t]) for t in tasks])
    # cluster bootstrap: resample TASKS (keep both seeds of a task together)
    means = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(tasks), len(tasks))
        means.append(float(np.mean(diffs[idx])))
    lo, hi = np.percentile(means, [2.5, 97.5])
    return (float(np.mean([a - b for _, a, b in pairs])), float(lo), float(hi))


def summarize(rows):
    out = {"per_arm": {}, "comparisons": {}, "update_analysis": {}}
    for arm in ARMS:
        rows_a = [r for r in rows if r["arm"] == arm]
        if not rows_a:
            continue
        n = len(rows_a)
        final = sum(bool(r["final_success"]) for r in rows_a)
        a1 = sum(bool(r["attempt1_success"]) for r in rows_a)
        retried = [r for r in rows_a if r["retried"]]
        recovered = sum(bool(r["final_success"]) for r in retried)
        out["per_arm"][arm] = {
            "rows": n, "final_success_rate": final / n if n else None,
            "attempt1_success_rate": a1 / n if n else None,
            "retried_rows": len(retried),
            "recovery_rate": (recovered / len(retried)) if retried else None,
            "recovery_denominator": len(retried),
            "provider_calls": sum(r["provider_calls"] for r in rows_a),
            "input_tokens": sum(r["input_tokens"] for r in rows_a),
            "cache_read_tokens": sum(r["cache_read_tokens"] for r in rows_a),
            "output_tokens": sum(r["output_tokens"] for r in rows_a),
            "cost_cny": round(sum(r["cost_cny"] for r in rows_a), 8),
            "latency_ms_mean": (sum(r["latency_ms"] for r in rows_a) / n) if n else None,
        }
    comps = [("CEA-v2-online", "B1-random"),
             ("CEA-v2-online", "B5-v1-frozen-pareto"),
             ("CEA-v2-online", "B0-original"),
             ("B5-v1-frozen-pareto", "B1-random")]
    raw = []
    for a, b in comps:
        pairs = paired_diff(rows, a, b)
        disc_pos = sum(1 for _, x, y in pairs if x == 1 and y == 0)
        disc_neg = sum(1 for _, x, y in pairs if x == 0 and y == 1)
        diff, lo, hi = cluster_bootstrap_ci(pairs)
        p = mcnemar_exact(disc_pos, disc_neg)
        raw.append((a, b, pairs, disc_pos, disc_neg, diff, lo, hi, p))
        out["comparisons"][f"{a} vs {b}"] = {
            "paired_rows": len(pairs), "discordant_pos": disc_pos,
            "discordant_neg": disc_neg, "paired_diff": diff,
            "cluster_bootstrap_ci95": [lo, hi], "mcnemar_exact_p": p,
        }
    # Holm across the three CEA-v2 comparisons (primary = CEA-v2 vs B1)
    pvals = sorted((r[-1], i) for i, r in enumerate(raw))
    adj = {}
    m = len(pvals)
    for rank, (p, i) in enumerate(pvals):
        adj[i] = min(1.0, p * (m - rank))
    for i, (a, b, pairs, dp, dn, diff, lo, hi, p) in enumerate(raw):
        out["comparisons"][f"{a} vs {b}"]["holm_adj_p"] = adj[i]
        out["comparisons"][f"{a} vs {b}"]["evidence_of_benefit"] = bool(
            adj[i] < 0.05 and lo is not None and lo > 0)
    cea = [r for r in rows if r["arm"] == "CEA-v2-online"]
    evo = [r for r in cea if r.get("controller_update")]
    out["update_analysis"] = {
        "observed_rows": len(evo),
        "evolve_events": sum(1 for r in cea
                             if (r.get("population_version_after") or 0) > 0),
        "distinct_selected_genomes": len({r["selected_genome_id"] for r in cea
                                          if r.get("selected_genome_id")}),
        "distinct_population_versions": sorted({r["population_version"]
                                                for r in cea
                                                if r.get("population_version") is not None}),
    }
    return out


def main() -> int:
    run_dir = Path(sys.argv[1])
    rows = [json.loads(l) for l in (run_dir / "tasks.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    summary = summarize(rows)
    summary["run_dir"] = str(run_dir)
    summary["rows_total"] = len(rows)
    summary["protocol"] = "docs/PHASE4_R1_9_EXPERIMENT_PROTOCOL.md"
    summary["evidence_class"] = "exploratory_pilot (26 task clusters / 52 pairs)"
    (run_dir / "analysis.json").write_text(json.dumps(summary, indent=2,
                                                      ensure_ascii=False),
                                           encoding="utf-8")
    print(json.dumps(summary["per_arm"], indent=2, ensure_ascii=False))
    print(json.dumps(summary["comparisons"], indent=2, ensure_ascii=False))
    print(json.dumps(summary["update_analysis"], indent=2, ensure_ascii=False))
    print("analysis written:", run_dir / "analysis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
