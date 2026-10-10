"""Offline reconciliation of a stored calls.csv (R1.1-F1).

Reads the immutable raw CSV, recomputes every aggregate from scratch, checks
internal consistency (per-row bucket identities, group sums == overall,
recorded cost == cost recomputed from buckets at the recorded price tier),
and writes:
- reconciliation.json: file SHA-256, rules, aggregates, check results
- summary.json: regenerated from the CSV (marked as backfilled; run metadata
  preserved from the previous summary where present)

The raw CSV is NEVER modified. No network, no API spend.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .benchmark import aggregate_rows
from .pricing import cost_for_usage
from .usage import UsageRecord

COST_TOLERANCE_CNY = 1e-6


def _row_usage(row: dict[str, str]) -> UsageRecord:
    return UsageRecord(
        uncached_input_tokens=int(row["uncached_input_tokens"]),
        cache_read_tokens=int(row["cache_read_tokens"]),
        cache_write_tokens=int(row["cache_write_tokens"]) if row.get("cache_write_tokens") else None,
        output_tokens=int(row["output_tokens"]),
    )


def reconcile(csv_path: Path, *, usd_cny: float = 7.10) -> dict[str, Any]:
    csv_bytes = csv_path.read_bytes()
    csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    rows = list(csv.DictReader(csv_bytes.decode("utf-8").splitlines()))

    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # Per-row identity: total_prompt == uncached + cache_read (+ cache_write)
    identity_ok = True
    for r in rows:
        u = _row_usage(r)
        if u.total_prompt_tokens != int(r["total_prompt_tokens"]):
            identity_ok = False
    check("per_row_total_prompt_equals_bucket_sum", identity_ok)

    # Cost re-derivation per row (buckets x recorded tier rates)
    cost_ok = True
    for r in rows:
        u = _row_usage(r)
        recomputed = cost_for_usage(u, r["price_tier"], usd_cny).cost_cny
        if abs(recomputed - float(r["cost_cny_tiered"])) > COST_TOLERANCE_CNY:
            cost_ok = False
    check("per_row_cost_matches_bucket_rates", cost_ok)

    overall = aggregate_rows(rows)
    groups: dict[str, Any] = {}
    group_sum_ok = True
    for group in ("A", "B", "C", "D"):
        g_rows = [r for r in rows if r["group"] == group]
        groups[group] = aggregate_rows(g_rows)
    for key in ("uncached_input_tokens", "cache_read_tokens", "total_prompt_tokens",
                "output_tokens_all_attempts"):
        if sum(groups[g][key] for g in groups) != overall[key]:
            group_sum_ok = False
    check("group_sums_equal_overall", group_sum_ok)

    check("row_count_100", len(rows) == 100, f"rows={len(rows)}")
    check("groups_25_each", all(groups[g]["logical_calls"] == 25 for g in groups))

    return {
        "source_csv": str(csv_path),
        "source_csv_sha256": csv_sha256,
        "rules": [
            "total_prompt_tokens = uncached_input + cache_read (+ cache_write if reported)",
            "weighted_cache_hit_rate = sum(cache_read) / sum(total_prompt)",
            "mean_per_request_cache_hit_rate = mean of per-row cache_hit_rate",
            "cost recomputed per row from buckets at the row's recorded price tier",
            "raw CSV is immutable; this file is derived evidence",
        ],
        "overall": overall,
        "groups": groups,
        "checks": checks,
        "all_checks_ok": all(c["ok"] for c in checks),
    }


def backfill_summary(output_dir: Path, *, usd_cny: float = 7.10) -> dict[str, Any]:
    """Regenerate summary.json from calls.csv without touching the CSV."""
    csv_path = output_dir / "calls.csv"
    recon = reconcile(csv_path, usd_cny=usd_cny)
    (output_dir / "reconciliation.json").write_text(
        json.dumps(recon, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary_path = output_dir / "summary.json"
    old: dict[str, Any] = {}
    if summary_path.exists():
        old = json.loads(summary_path.read_text(encoding="utf-8"))

    overall = recon["overall"]
    groups = {
        g: {
            "ok_calls": recon["groups"][g]["completed_calls"],
            "cache_hit_rate_mean": recon["groups"][g]["mean_per_request_cache_hit_rate"],
            "weighted_cache_hit_rate": recon["groups"][g]["weighted_cache_hit_rate"],
            "cache_read_tokens": recon["groups"][g]["cache_read_tokens"],
            "uncached_input_tokens": recon["groups"][g]["uncached_input_tokens"],
            "cache_write_tokens": recon["groups"][g]["cache_write_tokens"],
            "output_tokens_all_attempts": recon["groups"][g]["output_tokens_all_attempts"],
            "total_prompt_tokens": recon["groups"][g]["total_prompt_tokens"],
            "finish_reason_distribution": recon["groups"][g]["finish_reason_distribution"],
            "cost_cny_peak": round(recon["groups"][g]["cost_cny_peak"], 6),
            "cost_cny_tiered": round(recon["groups"][g]["cost_cny_tiered"], 6),
        }
        for g in ("A", "B", "C", "D")
    }
    summary = {
        "run_id": old.get("run_id"),
        "live": old.get("live"),
        "config_hash_legacy_raw": old.get("config_hash") or old.get("config_hash_legacy_raw"),
        "planned_calls": old.get("planned_calls"),
        "executed_calls": overall["logical_calls"],
        "ok_calls": overall["completed_calls"],
        "failed_calls": overall["logical_calls"] - overall["completed_calls"],
        "aborted_reason": old.get("aborted_reason"),
        "overall": overall,
        "groups": groups,
        "task_validity_note": (
            "CSV persisted no response bodies: task_valid is 'unknown' for all "
            "100 rows. 41 rows finished with max-tokens (B=13, C=10, D=18) and "
            "are valid metering samples but NOT verified complete JSON outputs."
        ),
        "balance_reconciliation": old.get("balance_reconciliation"),
        "confounds": old.get("confounds"),
        "backfilled_from": {
            "path": "calls.csv",
            "sha256": recon["source_csv_sha256"],
            "note": "regenerated from the immutable raw CSV on 2026-10-10 (R1.1-F1); supersedes the original summary's hand-transcribed totals",
        },
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary
