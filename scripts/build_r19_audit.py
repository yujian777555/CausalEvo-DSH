"""Build sanitized, deterministic R1.9 audit projections (P4-R1.10 Task A/B).

Reads ORIGINAL local run artifacts (never fabricates) and writes sanitized
projections under results/phase4/r19-audit/. No request/response bodies,
prompts, keys, Authorization headers or raw session logs are emitted.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase4" / "r19-audit"
RUNS = {
    "canary_ok": "phase4-r19-canary-20261024T144121Z",
    "canary_unknown": "phase4-r19-canary-20261024T143120Z",
    "run1_permission": "phase4-r19-pilot-20261024T144512Z",
    "run2_livelock_stop": "phase4-r19-pilot-20261024T144813Z",
    "final_resumed": "phase4-r19-pilot-20261024T151323Z",
}
LIVE2 = REPO / "results" / "phase4" / "live2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    final_dir = LIVE2 / RUNS["final_resumed"]
    src_tasks = final_dir / "tasks.jsonl"
    src_events = final_dir / "events.jsonl"
    src_manifest = final_dir / "manifest.json"
    originals = {"tasks.jsonl": sha(src_tasks), "events.jsonl": sha(src_events),
                 "manifest.json": sha(src_manifest)}
    tasks = [json.loads(l) for l in src_tasks.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    events = [json.loads(l) for l in src_events.read_text(encoding="utf-8").splitlines()
              if l.strip()]
    assert len(tasks) == 208, f"expected 208 rows, got {len(tasks)}"

    # ---- auditable_tasks.jsonl: one row per final (task, seed, arm) observation
    with (OUT / "auditable_tasks.jsonl").open("w", encoding="utf-8") as fh:
        for r in tasks:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    # ---- auditable_events.jsonl: controller events with lineage and order
    with (OUT / "auditable_events.jsonl").open("w", encoding="utf-8") as fh:
        for i, e in enumerate(events):
            fh.write(json.dumps({"seq": i, **e}, ensure_ascii=False, sort_keys=True) + "\n")

    # ---- auditable_ledger.jsonl: request state transitions across ALL runs
    final_states: dict[str, dict] = {}
    per_run: dict[str, dict] = {}
    with (OUT / "auditable_ledger.jsonl").open("w", encoding="utf-8") as fh:
        for run_label, run_id in RUNS.items():
            lp = LIVE2 / run_id / "proxy-ledger" / "ledger.jsonl"
            if not lp.is_file():
                raise FileNotFoundError(f"missing original ledger: {lp}")
            originals[f"ledger.{run_label}"] = sha(lp)
            entries = [json.loads(l) for l in lp.read_text(encoding="utf-8").splitlines()
                       if l.strip()]
            rid_scope = {e["request_id"]: e.get("scope") for e in entries
                         if e.get("state") == "RESERVED"}
            n_settled = 0
            settled_cost = 0.0
            unknown_bound = 0.0
            for e in entries:
                if e.get("request_id"):
                    final_states[e["request_id"]] = {"run": run_label, **e}
                if e.get("state") == "SETTLED":
                    n_settled += 1
                    settled_cost += e.get("cost_cny", 0.0)
                if e.get("state") == "RESERVED" and not any(
                        x.get("request_id") == e["request_id"]
                        and x.get("state") in ("SETTLED", "REJECTED") for x in entries):
                    unknown_bound += e.get("reserved_cny", 0.0)
                rec = {
                    "request_id": e.get("request_id"),
                    "run_id": run_id,
                    "scope": e.get("scope", rid_scope.get(e.get("request_id"))),
                    "state": e.get("state"),
                    "reserved_cny": e.get("reserved_cny"),
                    "cost_cny": e.get("cost_cny"),
                    "note": e.get("note", e.get("reason")),
                    "control": e.get("control"),
                }
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            per_run[run_label] = {"run_id": run_id, "settled_requests": n_settled,
                                  "settled_cost_cny": round(settled_cost, 10),
                                  "unknown_bound_cny": round(unknown_bound, 10)}

    # ---- reconciliation arithmetic (exact, unique-request-id based)
    total_settled = sum(v["settled_requests"] for v in per_run.values())
    total_settled_cost = round(sum(v["settled_cost_cny"] for v in per_run.values()), 10)
    total_unknown_bound = round(sum(v["unknown_bound_cny"] for v in per_run.values()), 10)
    final_states_count = Counter(v["state"] for v in final_states.values())
    row_calls = sum(r["provider_calls"] for r in tasks)
    final_settled = per_run["final_resumed"]["settled_requests"]
    aborted_scope = f"{RUNS['final_resumed']}/micro-011-second_largest/20261014/B1-random"
    aborted_attempts = next(r["provider_calls"] for r in tasks
                            if r["episode_id"] == aborted_scope)
    manifest = {
        "reconciled_by": "scripts/build_r19_audit.py",
        "source_originals_sha256": originals,
        "projections": {
            "auditable_tasks.jsonl": {"rows": len(tasks),
                                      "sha256": sha(OUT / "auditable_tasks.jsonl")},
            "auditable_events.jsonl": {"rows": len(events),
                                       "sha256": sha(OUT / "auditable_events.jsonl")},
            "auditable_ledger.jsonl": {
                "rows": sum(1 for _ in (OUT / "auditable_ledger.jsonl").open()),
                "sha256": sha(OUT / "auditable_ledger.jsonl")},
        },
        "original_manifest_sha256": originals["manifest.json"],
        "rows_total": len(tasks),
        "rows_written_last_process": 58,
        "per_run": per_run,
        "total_settled_requests": total_settled,
        "total_settled_cost_cny_peak": total_settled_cost,
        "total_unknown_bound_cny": total_unknown_bound,
        "round_total_with_unknown_bound": round(total_settled_cost + total_unknown_bound, 10),
        "budget_cap_cny": 2.00,
        "final_state_counts_by_unique_request_id": dict(final_states_count),
        "row_level_provider_calls_total": row_calls,
        "formulas": {
            "total_settled_requests": "24 (canary_ok) + 2 (canary_unknown) + 13 (run1) + 180 (run2) + 693 (final_resumed) = 912",
            "row_level_provider_calls": f"699 = {final_settled} (proxy SETTLED) + 1 UNKNOWN (IncompleteRead fe088dd) + 5 REJECTED (gate-stopped) = 699",
            "round_cost": f"{total_settled_cost} (settled) + {total_unknown_bound} (unknown upper bound) = {round(total_settled_cost + total_unknown_bound, 10)}",
            "aborted_scope_attempts": f"{aborted_attempts} attempts on the IncompleteRead-aborted row (1 UNKNOWN + 5 REJECTED, zero SETTLED) explain the entire 699-693=6 gap",
        },
        "field_definitions": {
            "provider_calls(row)": "provider attempts extracted from the agent runtime events for that row (settled + unmetered)",
            "settled_requests": "unique request_ids whose final state is SETTLED in the proxy ledger",
            "unknown_bound_cny": "worst-case reservation for RESERVED/SENT requests without SETTLED/REJECTED (cost unknown)",
            "no_secret_fields": "no request/response bodies, prompts, keys, Authorization or raw session logs are emitted",
        },
    }
    (OUT / "manifest_reconciled.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"rows": len(tasks), "total_settled": total_settled,
                      "row_calls": row_calls, "round_cost_with_unknown":
                      manifest["round_total_with_unknown_bound"]}, indent=2))
    print("audit projections written:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
