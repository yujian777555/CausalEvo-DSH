"""Phase 4 statistical analysis: reads results/phase4/live/<run>/tasks.jsonl.

Frozen metrics (docs/PHASE4_EXPERIMENT_PROTOCOL.md §4): pass rate, recovery
rate, evolution gain, McNemar exact, paired bootstrap CI, cost analysis.
No averages without intervals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def load_rows(run_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in (run_dir / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def pass_rate(rows: list[dict], arm: str) -> float | None:
    sel = [r for r in rows if r["arm"] == arm]
    return (sum(r["final_success"] for r in sel) / len(sel)) if sel else None


def recovery_rate(rows: list[dict], arm: str) -> float | None:
    """Among first-attempt failures that were retried: fraction recovered."""
    sel = [r for r in rows if r["arm"] == arm and not r["attempt1_success"] and r["retried"]]
    return (sum(r["final_success"] for r in sel) / len(sel)) if sel else None


def mcnemar_exact(rows: list[dict], arm_a: str, arm_b: str) -> dict[str, Any]:
    """Paired by (task_id, seed). Exact two-sided McNemar p-value."""
    from math import comb
    a = {(r["task_id"], r["seed"]): r["final_success"] for r in rows if r["arm"] == arm_a}
    b = {(r["task_id"], r["seed"]): r["final_success"] for r in rows if r["arm"] == arm_b}
    keys = sorted(set(a) & set(b))
    b01 = sum(1 for k in keys if a[k] and not b[k])
    b10 = sum(1 for k in keys if not a[k] and b[k])
    n = b01 + b10
    if n == 0:
        return {"arm_a": arm_a, "arm_b": arm_b, "b01": 0, "b10": 0, "p_value": None,
                "note": "no discordant pairs"}
    k = min(b01, b10)
    p = min(1.0, sum(comb(n, i) for i in range(0, k + 1)) / 2 ** (n - 1))
    return {"arm_a": arm_a, "arm_b": arm_b, "b01": b01, "b10": b10,
            "n_discordant": n, "p_value": p}


def bootstrap_diff_ci(rows: list[dict], arm_a: str, arm_b: str, *,
                      n_boot: int = 10000, seed: int = 20261014) -> dict[str, Any]:
    """Paired bootstrap 95% CI for success-rate difference (a - b)."""
    rng = np.random.default_rng(seed)
    a = {(r["task_id"], r["seed"]): int(r["final_success"]) for r in rows if r["arm"] == arm_a}
    b = {(r["task_id"], r["seed"]): int(r["final_success"]) for r in rows if r["arm"] == arm_b}
    keys = sorted(set(a) & set(b))
    if not keys:
        return {"arm_a": arm_a, "arm_b": arm_b, "ci": None, "note": "no paired keys"}
    diffs = np.array([a[k] - b[k] for k in keys], dtype=float)
    boots = [float(np.mean(rng.choice(diffs, size=len(diffs), replace=True)))
             for _ in range(n_boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"arm_a": arm_a, "arm_b": arm_b, "mean_diff": float(diffs.mean()),
            "ci95": [round(float(lo), 4), round(float(hi), 4)],
            "n_pairs": len(keys), "n_boot": n_boot}


def cost_analysis(rows: list[dict]) -> dict[str, Any]:
    per_arm: dict[str, Any] = {}
    for r in rows:
        arm = per_arm.setdefault(r["arm"], {
            "runs": 0, "cost_cny": 0.0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "provider_calls": 0, "latency_ms": 0})
        arm["runs"] += 1
        arm["cost_cny"] += r["cost_cny"]
        arm["input_tokens"] += r["input_tokens"]
        arm["output_tokens"] += r["output_tokens"]
        arm["cache_read_tokens"] += r["cache_read_tokens"]
        arm["provider_calls"] += r["provider_calls"]
        arm["latency_ms"] += r["latency_ms"]
    for arm in per_arm.values():
        arm["cost_cny"] = round(arm["cost_cny"], 6)
        arm["mean_latency_ms"] = round(arm.pop("latency_ms") / arm["runs"], 1)
    total = round(sum(a["cost_cny"] for a in per_arm.values()), 6)
    return {"per_arm": per_arm, "total_cost_cny": total}


def cluster_bootstrap_diff_ci(rows: list[dict], arm_a: str, arm_b: str, *,
                              n_boot: int = 10000, seed: int = 20261014) -> dict[str, Any]:
    """Task-level cluster bootstrap (P4-R1.1-S4): resample TASKS with
    replacement, keeping every (seed, arm) row of a task together — the two
    seeds of one task are not independent."""
    rng = np.random.default_rng(seed)
    by_task_a: dict[str, list[int]] = {}
    by_task_b: dict[str, list[int]] = {}
    for r in rows:
        if r["arm"] == arm_a:
            by_task_a.setdefault(r["task_id"], []).append(int(r["final_success"]))
        elif r["arm"] == arm_b:
            by_task_b.setdefault(r["task_id"], []).append(int(r["final_success"]))
    tasks = sorted(set(by_task_a) & set(by_task_b))
    if not tasks:
        return {"arm_a": arm_a, "arm_b": arm_b, "ci95": None, "note": "no shared tasks"}
    def _diff(sample_tasks):
        a_vals = [v for t in sample_tasks for v in by_task_a[t]]
        b_vals = [v for t in sample_tasks for v in by_task_b[t]]
        return float(np.mean(a_vals) - np.mean(b_vals))
    boots = [_diff([tasks[i] for i in rng.integers(0, len(tasks), len(tasks))])
             for _ in range(n_boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"arm_a": arm_a, "arm_b": arm_b,
            "mean_diff": _diff(tasks),
            "ci95": [round(float(lo), 4), round(float(hi), 4)],
            "n_task_clusters": len(tasks), "n_boot": n_boot}


def task_level_summary(rows: list[dict]) -> dict[str, Any]:
    """Per-task per-arm success means over seeds (sensitivity view)."""
    by_task: dict[str, dict[str, list[int]]] = {}
    for r in rows:
        by_task.setdefault(r["task_id"], {}).setdefault(r["arm"], []).append(
            int(r["final_success"]))
    return {
        t: {a: float(np.mean(v)) for a, v in arms_map.items()}
        for t, arms_map in by_task.items()
    }


def analyze(run_dir: Path) -> dict[str, Any]:
    rows = load_rows(run_dir)
    arms = sorted({r["arm"] for r in rows})
    result: dict[str, Any] = {
        "run_dir": str(run_dir),
        "n_rows": len(rows),
        "arms": arms,
        "pass_rate": {a: pass_rate(rows, a) for a in arms},
        "recovery_rate": {a: recovery_rate(rows, a) for a in arms},
        "mcnemar": [mcnemar_exact(rows, "B5-cea-v1", "B0-original"),
                    mcnemar_exact(rows, "B5-cea-v1", "B1-random"),
                    mcnemar_exact(rows, "B4-cea-v0", "B5-cea-v1")],
        "bootstrap": [bootstrap_diff_ci(rows, "B5-cea-v1", "B0-original"),
                      bootstrap_diff_ci(rows, "B5-cea-v1", "B1-random")],
        "cost": cost_analysis(rows),
    }
    if "B0-original" in arms and "B5-cea-v1" in arms:
        p0, p5 = pass_rate(rows, "B0-original"), pass_rate(rows, "B5-cea-v1")
        result["evolution_gain"] = (p5 - p0) if (p0 is not None and p5 is not None) else None
    return result


def main(run_dir: Path) -> int:
    out = analyze(run_dir)
    (run_dir / "baseline_results.json").write_text(json.dumps(
        {k: out[k] for k in ("pass_rate", "recovery_rate", "evolution_gain", "n_rows")},
        indent=2), encoding="utf-8")
    (run_dir / "statistical_tests.json").write_text(json.dumps(
        {"mcnemar": out["mcnemar"], "bootstrap": out["bootstrap"]}, indent=2),
        encoding="utf-8")
    (run_dir / "cost_analysis.json").write_text(json.dumps(out["cost"], indent=2),
                                                encoding="utf-8")
    print(json.dumps(out["pass_rate"], indent=1))
    print("evolution_gain:", out.get("evolution_gain"))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(Path(sys.argv[1])))
