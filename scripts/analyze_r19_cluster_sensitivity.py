"""Exact task-cluster sign-flip sensitivity for the R1.9 pilot (P4-R1.11 Task A).

Method: for each comparison, compute per-task mean paired differences with
BOTH seeds of a task kept together (26 clusters). Under the null, each
cluster's mean difference sign is exchangeable. We enumerate the exact
distribution of the signed sum via dynamic programming over the discrete
support (task means are multiples of 0.5), then take the exact two-sided
tail probability. No Monte Carlo noise, fully deterministic.

Label: POST_HOC_CLUSTER_AWARE_SENSITIVITY (never the preregistered primary
McNemar analysis, which is preserved unchanged).
"""
import json
from collections import defaultdict
from pathlib import Path

from analyze_r19_pilot import ARMS, paired_diff

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "results" / "phase4" / "r19-audit"


def task_mean_differences(pairs):
    """Return (scaled integer task differences, observed signed sum).

    Each task contributes its mean paired difference over BOTH seeds. Values
    are multiples of 0.5, so we scale by 2 to integers {-2,-1,0,1,2}.
    """
    by_task = defaultdict(list)
    for key, a, b in pairs:
        by_task[key[0]].append(a - b)
    scaled = [int(round(2 * (sum(by_task[t]) / len(by_task[t]))))
              for t in sorted(by_task)]
    return scaled, sum(scaled)


def exact_signflip_p(scaled_diffs, observed_sum):
    """Exact two-sided sign-flip p via DP over integer signed sums.

    DP[s] = number of sign assignments whose sum of scaled differences is s.
    p = P(|S| >= |observed_sum|) = count(|s| >= |observed_sum|) / 2^n.
    """
    n = len(scaled_diffs)
    dp = {0: 1}
    for d in scaled_diffs:
        nxt = defaultdict(int)
        for s, c in dp.items():
            nxt[s + d] += c
            nxt[s - d] += c
        dp = nxt
    threshold = abs(observed_sum)
    tail = sum(c for s, c in dp.items() if abs(s) >= threshold)
    return tail / (2 ** n), dp


def validate_rows(rows):
    """Reject malformed datasets instead of silently computing on them."""
    keys = [(r["task_id"], r["seed"], r["arm"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate (task_id, seed, arm) keys")
    tasks = {r["task_id"] for r in rows}
    seeds = {r["seed"] for r in rows}
    arms = {r["arm"] for r in rows}
    if len(tasks) != 26:
        raise ValueError(f"expected 26 tasks, got {len(tasks)}")
    if seeds != {20261014, 20261015}:
        raise ValueError(f"unexpected seed set: {sorted(seeds)}")
    if set(ARMS) != arms:
        raise ValueError(f"missing or unexpected arms: {sorted(arms)}")
    for t in tasks:
        for s in seeds:
            for a in ARMS:
                if (t, s, a) not in keys:
                    raise ValueError(f"missing row: {t}/{s}/{a}")


def analyze(rows):
    validate_rows(rows)
    comparisons = [("CEA-v2-online", "B1-random"),
                   ("CEA-v2-online", "B5-v1-frozen-pareto"),
                   ("CEA-v2-online", "B0-original"),
                   ("B5-v1-frozen-pareto", "B1-random")]
    out = {}
    for a, b in comparisons:
        pairs = paired_diff(rows, a, b)
        if not pairs:
            raise ValueError(f"no paired rows for comparison {a} vs {b}")
        scaled, obs = task_mean_differences(pairs)
        p, _dp = exact_signflip_p(scaled, obs)
        out[f"{a} vs {b}"] = {
            "n_clusters": len(scaled),
            "seeds_kept_together": True,
            "observed_scaled_sum": obs,
            "exact_two_sided_p": p,
        }
    return out


def main() -> int:
    rows = [json.loads(l) for l in (AUDIT / "auditable_tasks.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 208, f"expected 208 rows, got {len(rows)}"
    results = analyze(rows)
    previous_path = AUDIT / "sensitivity.json"
    previous = {}
    if previous_path.is_file():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
    out = {
        "method": "exact_sign_flip_dynamic_programming",
        "label": "POST_HOC_CLUSTER_AWARE_SENSITIVITY",
        "not_preregistered_primary": True,
        "n_clusters": 26,
        "seeds_kept_together": True,
        "rows_total": len(rows),
        "comparisons": results,
        "previous_monte_carlo_estimates": {
            k: v.get("cluster_permutation_sensitivity")
            for k, v in previous.get("comparisons", {}).items()
            if "cluster_permutation_sensitivity" in v
        },
        "note": "exact DP enumeration over 2^26 sign assignments; previous 20000-permutation estimates are preserved in previous_monte_carlo_estimates and are not overwritten by this exact computation",
    }
    (AUDIT / "sensitivity.json").write_text(json.dumps(out, indent=2,
                                                       ensure_ascii=False),
                                            encoding="utf-8")
    print(json.dumps(results, indent=2))
    print("sensitivity written:", AUDIT / "sensitivity.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
