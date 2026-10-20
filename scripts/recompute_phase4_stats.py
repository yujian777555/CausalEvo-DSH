"""Recompute Phase 4 statistics with task-level cluster bootstrap (R1.1).

Reads the auditable 312-row table, preserves the legacy IID paired numbers,
adds cluster bootstrap by task_id and per-task sensitivity. Writes a NEW
versioned artifact; the frozen originals are never modified.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import analyze_phase4 as analyze  # noqa: E402

RUN = Path("results/phase4/live/phase4-live-20261014T110259Z")


def main() -> int:
    rows = analyze.load_rows(RUN)
    legacy = json.loads((RUN / "statistical_tests.json").read_text(encoding="utf-8"))
    out = {
        "schema_version": "r1.1",
        "legacy_iid_paired": legacy,
        "cluster_bootstrap": [
            analyze.cluster_bootstrap_diff_ci(rows, "B5-cea-v1", "B0-original"),
            analyze.cluster_bootstrap_diff_ci(rows, "B5-cea-v1", "B1-random"),
            analyze.cluster_bootstrap_diff_ci(rows, "B4-cea-v0", "B5-cea-v1"),
        ],
        "task_level_summary": analyze.task_level_summary(rows),
        "retry_frequency": {
            arm: (sum(1 for r in rows if r["arm"] == arm and r["retried"])
                  / max(1, sum(1 for r in rows if r["arm"] == arm)))
            for arm in sorted({r["arm"] for r in rows})
        },
        "note": ("cluster bootstrap resamples 26 task clusters (both seeds kept "
                 "together); legacy IID values preserved verbatim; B5 vs B1 remains "
                 "the key causal control"),
    }
    path = RUN / "statistical_tests_r1_1.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    for cb in out["cluster_bootstrap"]:
        print(cb["arm_a"], "vs", cb["arm_b"], "cluster CI:", cb["ci95"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
