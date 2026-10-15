"""Reconcile Phase 4 per-task evidence (P4-R1.1-S1).

Reads the FROZEN original tasks.jsonl (never modifies it), emits a de-identified
auditable table (auditable_tasks.jsonl) with per-row hashes, then recomputes
pass rates / McNemar / bootstrap / cost and asserts equality with the committed
analysis files. A fresh clone must be able to rerun this and get the same
numbers.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import analyze_phase4 as analyze  # noqa: E402

RUN = Path("results/phase4/live/phase4-live-20261014T110259Z")
ORIGINAL = RUN / "tasks.jsonl"
AUDIT = RUN / "auditable_tasks.jsonl"
ORIGINAL_SHA256 = "21dd5dc09cae4f7d2647b3d7129942c37bd75c824d1619e86c2e10fb3c13bcbc"

AUDIT_FIELDS = ["task_id", "arm", "seed", "attempt1_success", "retried",
                "final_success", "invalid", "timeout", "failure_kind",
                "intervention", "provider_calls", "tool_calls", "input_tokens",
                "cache_read_tokens", "output_tokens", "cost_cny", "latency_ms",
                "run_id"]


def main() -> int:
    raw = ORIGINAL.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == ORIGINAL_SHA256, f"original file hash drift: {sha}"
    rows = analyze.load_rows(RUN)
    assert len(rows) == 312, f"expected 312 rows, got {len(rows)}"

    # uniqueness of (task, arm, seed)
    keys = [(r["task_id"], r["arm"], r["seed"]) for r in rows]
    assert len(set(keys)) == 312, "duplicate (task, arm, seed)"

    # de-identified auditable table (fields are already safe; re-project + hash)
    with AUDIT.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("# auditable projection of tasks.jsonl (sha256 %s)\n" % sha)
        fh.write("# schema_version=1 derived_from_sha256=%s rows=312\n" % sha)
        for r in rows:
            proj = {k: r[k] for k in AUDIT_FIELDS}
            row_hash = hashlib.sha256(
                json.dumps(proj, sort_keys=True).encode()).hexdigest()[:16]
            proj["row_sha16"] = row_hash
            fh.write(json.dumps(proj, ensure_ascii=False, sort_keys=True) + "\n")

    # recompute everything from the auditable table and compare
    out = analyze.analyze(RUN)
    committed = json.loads((RUN / "baseline_results.json").read_text(encoding="utf-8"))
    assert out["pass_rate"] == committed["pass_rate"]
    assert out["recovery_rate"] == committed["recovery_rate"]
    st = json.loads((RUN / "statistical_tests.json").read_text(encoding="utf-8"))
    assert out["mcnemar"] == st["mcnemar"]
    assert out["bootstrap"] == st["bootstrap"]
    cost = json.loads((RUN / "cost_analysis.json").read_text(encoding="utf-8"))
    assert out["cost"]["total_cost_cny"] == cost["total_cost_cny"]
    print(f"reconciled 312 rows; original sha256={sha[:16]}...; all recomputed "
          f"metrics match committed analysis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
