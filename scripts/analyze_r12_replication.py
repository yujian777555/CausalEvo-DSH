"""Analysis for the R1.12 fresh-seed replication (frozen protocol in
docs/PHASE4_R1_12_REPLICATION_PROTOCOL.md).

Primary: binary final_success on all planned rows. Primary comparison:
CEA-v2-online vs B1-random with exact task-cluster sign-flip p (26 clusters,
both seeds together) + 10,000-resample task-cluster bootstrap 95% CI.
Secondary comparisons Holm-corrected. NSGA-III invocation counters are read
from the live event log (not fabricated). Rejects missing/duplicate
(task_id, seed, arm) keys before analysis.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from analyze_r19_pilot import (ARMS, cluster_bootstrap_ci, mcnemar_exact,
                               paired_diff, summarize)
from analyze_r19_cluster_sensitivity import (analyze as exact_analyze,
                                             exact_signflip_p,
                                             task_mean_differences)

ARMS_R12 = ["B0-original", "B1-random", "B5-v1-frozen-pareto", "CEA-v2-online"]


def main() -> int:
    import sys
    run_dir = Path(sys.argv[1])
    rows = [json.loads(l) for l in (run_dir / "tasks.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    keys = Counter((r["task_id"], r["seed"], r["arm"]) for r in rows)
    dups = [k for k, n in keys.items() if n > 1]
    if dups:
        raise ValueError(f"duplicate (task_id, seed, arm) keys: {dups}")
    seeds = sorted({r["seed"] for r in rows})
    if seeds != [20261027, 20261028]:
        raise ValueError(f"unexpected seeds for R1.12: {seeds}")
    for t in sorted({r["task_id"] for r in rows}):
        for s in seeds:
            for arm in ARMS_R12:
                if (t, s, arm) not in keys:
                    raise ValueError(f"missing row {t}/{s}/{arm}")

    out = {"run_dir": str(run_dir), "rows_total": len(rows),
           "coverage": {"tasks": len({r["task_id"] for r in rows}),
                        "seeds": seeds, "unique_keys": len(keys),
                        "duplicates": dups},
           "protocol": "docs/PHASE4_R1_12_REPLICATION_PROTOCOL.md",
           "per_arm": summarize(rows)["per_arm"]}
    comparisons = [("CEA-v2-online", "B1-random"),
                   ("CEA-v2-online", "B5-v1-frozen-pareto"),
                   ("CEA-v2-online", "B0-original"),
                   ("B5-v1-frozen-pareto", "B1-random")]
    comps = {}
    for a, b in comparisons:
        pairs = paired_diff(rows, a, b)
        dp = sum(1 for _, x, y in pairs if x == 1 and y == 0)
        dn = sum(1 for _, x, y in pairs if x == 0 and y == 1)
        diff, lo, hi = cluster_bootstrap_ci(pairs, n_boot=10000)
        scaled, obs = task_mean_differences(pairs)
        p_exact, _ = exact_signflip_p(scaled, obs)
        p_mcn = mcnemar_exact(dp, dn)
        comps[f"{a} vs {b}"] = {
            "paired_rows": len(pairs), "discordant_pos": dp, "discordant_neg": dn,
            "paired_diff": diff, "cluster_bootstrap_ci95": [lo, hi],
            "exact_cluster_signflip_p": p_exact,
            "mcnemar_exact_p": p_mcn,
        }
    # Holm across all comparisons
    pvals = sorted((v["exact_cluster_signflip_p"], k) for k, v in comps.items())
    m = len(pvals)
    for rank, (p, key) in enumerate(pvals):
        comps[key]["holm_adj_p"] = min(1.0, p * (m - rank))
    for k, v in comps.items():
        v["evidence_of_improvement"] = bool(
            v["paired_diff"] is not None and v["paired_diff"] >= 0.10
            and v["holm_adj_p"] < 0.05 and v["cluster_bootstrap_ci95"][0] > 0)
    out["comparisons"] = comps
    # algorithm-fidelity counters from the live event log (never fabricated)
    events_file = run_dir / "events.jsonl"
    nsga_parent = 0
    nsga_survivor = 0
    evolve_events = 0
    if events_file.is_file():
        for line in events_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("kind") == "evolve":
                evolve_events += 1
                nsga_parent += int(e.get("nsga3_parent_selection_calls", 0))
                nsga_survivor += int(e.get("nsga3_survivor_selection_calls", 0))
    out["algorithm_fidelity"] = {
        "evolve_events": evolve_events,
        "nsga3_parent_selection_calls": nsga_parent,
        "nsga3_survivor_selection_calls": nsga_survivor,
        "claim_rule": "claim NSGA-III selection only if the actual counters are positive",
    }
    cea = [r for r in rows if r["arm"] == "CEA-v2-online"]
    out["online_updates"] = {
        "behavioral_observations": sum(1 for r in cea if r.get("controller_update")
                                       and r["controller_update"].get("updated")),
        "distinct_selected_genomes": len({r["selected_genome_id"] for r in cea
                                          if r.get("selected_genome_id")}),
        "distinct_population_versions": sorted({r["population_version"] for r in cea
                                                if r.get("population_version") is not None}),
    }
    out["evidence_class"] = "fresh-seed same-suite replication; NOT unseen-task generalization; exploratory"
    (run_dir / "analysis.json").write_text(json.dumps(out, indent=2,
                                                      ensure_ascii=False),
                                           encoding="utf-8")
    print(json.dumps(out["per_arm"], indent=2, ensure_ascii=False))
    print(json.dumps(comps, indent=2, ensure_ascii=False))
    print(json.dumps(out["algorithm_fidelity"], indent=2))
    print("analysis written:", run_dir / "analysis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
