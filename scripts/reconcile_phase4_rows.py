"""Reconcile Phase 4 per-task evidence (P4-R1.2-S1).

Default (verify) mode: reads the COMMITTED auditable_tasks.jsonl (works on a
fresh clone), recomputes pass rates / McNemar / bootstrap / cluster bootstrap /
cost, and asserts equality with the committed analysis files.

--local-project mode: regenerates the projection from the raw tasks.jsonl —
LOCAL-ONLY (raw file is never committed); refuses if the raw file is absent.
Never fabricates rows.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import analyze_phase4 as analyze  # noqa: E402
from causalevo.eval.auditable import read_auditable_rows, row_sha16  # noqa: E402

RUN = Path("results/phase4/live/phase4-live-20261014T110259Z")
ORIGINAL = RUN / "tasks.jsonl"
AUDIT = RUN / "auditable_tasks.jsonl"
ORIGINAL_SHA256 = "21dd5dc09cae4f7d2647b3d7129942c37bd75c824d1619e86c2e10fb3c13bcbc"
AUDIT_FIELDS = ["task_id", "arm", "seed", "attempt1_success", "retried",
                "final_success", "invalid", "timeout", "failure_kind",
                "intervention", "provider_calls", "tool_calls", "input_tokens",
                "cache_read_tokens", "output_tokens", "cost_cny", "latency_ms",
                "run_id"]


def verify() -> int:
    rows = read_auditable_rows(AUDIT)  # validates schema/hash/uniqueness/count
    out = analyze.analyze(RUN)  # analyze() defaults to the auditable source
    committed = json.loads((RUN / "baseline_results.json").read_text(encoding="utf-8"))
    assert out["pass_rate"] == committed["pass_rate"], "pass_rate mismatch"
    assert out["recovery_rate"] == committed["recovery_rate"]
    st = json.loads((RUN / "statistical_tests.json").read_text(encoding="utf-8"))
    assert out["mcnemar"] == st["mcnemar"]
    assert out["bootstrap"] == st["bootstrap"]
    r11 = json.loads((RUN / "statistical_tests_r1_1.json").read_text(encoding="utf-8"))
    assert out["cluster"] == r11["cluster_bootstrap"], "cluster bootstrap mismatch"
    cost = json.loads((RUN / "cost_analysis.json").read_text(encoding="utf-8"))
    assert out["cost"]["total_cost_cny"] == cost["total_cost_cny"]
    print("verified: 312 auditable rows recompute to the committed analysis "
          "(incl. cluster bootstrap)")
    return 0


def local_project() -> int:
    if not ORIGINAL.is_file():
        print(f"EVIDENCE_UNAVAILABLE: raw {ORIGINAL} not present on this machine; "
              "refusing to synthesize rows")
        return 2
    raw = ORIGINAL.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == ORIGINAL_SHA256, f"original file hash drift: {sha}"
    rows = analyze.load_rows(RUN, source="original")
    assert len(rows) == 312
    with AUDIT.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("# auditable projection of tasks.jsonl (sha256 %s)\n" % sha)
        fh.write("# schema_version=1 derived_from_sha256=%s rows=312\n" % sha)
        for r in rows:
            proj = {k: r[k] for k in AUDIT_FIELDS}
            proj["row_sha16"] = row_sha16(proj)
            fh.write(json.dumps(proj, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"projected 312 rows from local original (sha256={sha[:16]}...)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-project", action="store_true",
                        help="LOCAL-ONLY: rebuild projection from raw tasks.jsonl")
    args = parser.parse_args()
    return local_project() if args.local_project else verify()


if __name__ == "__main__":
    raise SystemExit(main())
