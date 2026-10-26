"""R1.10 Task E: recompute reported statistics from the sanitized 208-row
projection, validate coverage/keys/hash, and add a separately labeled
cluster-aware sensitivity test (paired sign-flip permutation on task means).

The preregistered McNemar result is preserved as primary; the permutation
test is explicitly a POST-HOC sensitivity analysis, not the primary test.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from analyze_r19_pilot import (ARMS, cluster_bootstrap_ci, mcnemar_exact,
                               paired_diff, summarize)

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "results" / "phase4" / "r19-audit"


def cluster_permutation_p(pairs, n_perm=20000, seed=20261026):
    """Two-sided paired sign-flip permutation on task-mean differences.

    Both seeds of a task stay together: the statistic is the mean over
    (task mean of (arm_a - arm_b)) across the 26 task clusters. Under the
    null, each task's mean difference sign is exchangeable.
    """
    by_task = defaultdict(list)
    for key, a, b in pairs:
        by_task[key[0]].append(a - b)
    if not by_task:
        return {"p": None, "stat": None, "n_clusters": 0}
    means = np.array([np.mean(by_task[t]) for t in sorted(by_task)])
    observed = float(np.mean(means))
    rng = np.random.default_rng(seed)
    flips = rng.choice([-1.0, 1.0], size=(n_perm, len(means)))
    perm_stats = (flips * means).mean(axis=1)
    p = float(np.mean(np.abs(perm_stats) >= abs(observed)))
    return {"p": p, "stat": observed, "n_clusters": len(means),
            "n_permutations": n_perm, "seed": seed}


def main() -> int:
    tasks_file = AUDIT / "auditable_tasks.jsonl"
    rows = [json.loads(l) for l in tasks_file.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    # ---- coverage / key / hash validation
    keys = Counter((r["task_id"], r["seed"], r["arm"]) for r in rows)
    duplicates = [k for k, n in keys.items() if n > 1]
    assert not duplicates, f"duplicate keys: {duplicates}"
    tasks = sorted({r["task_id"] for r in rows})
    seeds = sorted({r["seed"] for r in rows})
    assert len(tasks) == 26, f"expected 26 tasks, got {len(tasks)}"
    assert seeds == [20261014, 20261015], seeds
    for t in tasks:
        for s in seeds:
            for arm in ARMS:
                assert (t, s, arm) in keys, f"missing {t}/{s}/{arm}"

    # ---- recompute the preregistered summary from the projection
    summary = summarize(rows)
    comparisons = {}
    for a, b in [("CEA-v2-online", "B1-random"),
                 ("CEA-v2-online", "B5-v1-frozen-pareto"),
                 ("CEA-v2-online", "B0-original"),
                 ("B5-v1-frozen-pareto", "B1-random")]:
        pairs = paired_diff(rows, a, b)
        dp = sum(1 for _, x, y in pairs if x == 1 and y == 0)
        dn = sum(1 for _, x, y in pairs if x == 0 and y == 1)
        diff, lo, hi = cluster_bootstrap_ci(pairs)
        comparisons[f"{a} vs {b}"] = {
            "paired_diff": diff, "discordant_pos": dp, "discordant_neg": dn,
            "cluster_bootstrap_ci95": [lo, hi],
            "mcnemar_exact_p": mcnemar_exact(dp, dn),
        }
        if a == "CEA-v2-online":
            comparisons[f"{a} vs {b}"]["cluster_permutation_sensitivity"] = \
                cluster_permutation_p(pairs)
    out = {
        "rows_total": len(rows),
        "coverage": {"tasks": len(tasks), "seeds": seeds, "arms": ARMS,
                     "unique_keys": len(keys), "duplicates": duplicates},
        "per_arm": summary["per_arm"],
        "comparisons": comparisons,
        "preregistered_primary": "paired McNemar exact + task-cluster bootstrap CI (preserved from R1.9)",
        "sensitivity_label": "POST-HOC cluster-aware paired sign-flip permutation on task means (both seeds of a task stay together); NOT the preregistered primary test",
        "note_on_clustering": "the two seed rows of each task are clustered; the exact McNemar p treats discordant pairs as independent and is therefore NOT cluster-adjusted confirmatory evidence; any future confirmatory protocol must use a cluster-aware primary method",
    }
    (AUDIT / "sensitivity.json").write_text(json.dumps(out, indent=2,
                                                       ensure_ascii=False),
                                            encoding="utf-8")
    print(json.dumps(comparisons, indent=2, ensure_ascii=False))
    print("coverage OK:", out["coverage"])
    print("sensitivity written:", AUDIT / "sensitivity.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
