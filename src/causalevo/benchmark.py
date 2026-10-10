"""Benchmark orchestration: plan -> preflight -> gated calls -> evidence.

Safety properties:
- dry-run is the default; --live is an explicit opt-in requiring the key.
- a BudgetGate refuses any new live call that cannot be proven within cap,
  counting every remaining ATTEMPT (retries included) at worst-case price.
- usage is extracted from EVERY attempt, success or failure; a failed attempt
  with usage is metered and billed.
- a failed attempt WITHOUT usage means the request may have left the machine
  with unmeasurable cost: the call is marked unknown_cost and the run STOPS
  (fail-closed). Only errors proven to happen before any bytes were sent
  (error_kind="local_rejected") may continue without spend.
- successful-looking responses without parseable usage are fail-closed too.
- every attempt (including failures/retries) is metered and persisted.

R1.1-F3: API success and task validity are separate axes. response_accepted
means "valid metered API observation" (turn finished AND usage present).
task_valid additionally requires finish_reason == "completed" and the exact
expected minified JSON. Truncated (max-tokens) responses are valid metering
samples but not valid task outputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .budget import BudgetExceeded, BudgetGate
from .pricing import (
    DEFAULT_USD_CNY,
    PRICE_TABLE_META,
    classify_price_tier,
    cost_for_usage,
    worst_case_cost_cny,
)
from .redaction import hash_identifier, redact_obj
from .runner import Runner, RunnerOutcome, estimate_tokens
from .scenarios import PlannedCall, build_call_plan, check_length_invariants, expected_response
from .usage import AttemptRecord, UsageRecord, UsageUnavailable, extract_settled_usage

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "cache_benchmark.yaml"
USAGE_UNAVAILABLE_PREFIX = "usage unavailable: "


@dataclass(frozen=True, slots=True)
class BenchConfig:
    model: str
    reasoning_effort: str | None
    max_tokens: int
    calls_per_group: int
    max_cny: float
    max_retries_per_call: int
    interleave: bool
    usd_cny: float
    prompt_overhead_tokens: int
    raw: dict[str, Any]


def load_config(path: Path) -> BenchConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"config {path} must be a mapping")
    bench = data.get("benchmark", {})
    return BenchConfig(
        model=str(bench["model"]),
        reasoning_effort=bench.get("reasoning_effort"),
        max_tokens=int(bench["max_tokens"]),
        calls_per_group=int(bench["calls_per_group"]),
        max_cny=float(bench["max_cny"]),
        max_retries_per_call=int(bench.get("max_retries_per_call", 1)),
        interleave=bool(bench.get("interleave", True)),
        usd_cny=float(bench.get("usd_cny", DEFAULT_USD_CNY)),
        prompt_overhead_tokens=int(bench.get("prompt_overhead_tokens", 2000)),
        raw=data,
    )


def config_hash(config: BenchConfig) -> str:
    """LEGACY raw-YAML hash (R1 definition). Kept for continuity with run
    p0live02 (a4f11755ea27380c); new code should cite effective_config_fingerprint."""
    canonical = json.dumps(config.raw, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sdk_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("deepseek-harness-sdk")
    except Exception:
        return None


def effective_config_fingerprint(
    config: BenchConfig,
    *,
    patch_path: Path | None = None,
    sdk: str | None = None,
) -> str:
    """Hash of the EFFECTIVE experiment configuration (R1.1-F4).

    Covers every field that changes the experiment's semantics — including
    CLI overrides, because they mutate the BenchConfig before this is called —
    plus the no-tools patch content and the SDK version. Budget caps are
    deliberately NOT part of the fingerprint: tightening the cap to the
    platform balance changes spend authorization, not the experiment; the
    runtime cap is recorded separately in the config snapshot.
    """
    payload: dict[str, Any] = {
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "max_tokens": config.max_tokens,
        "calls_per_group": config.calls_per_group,
        "interleave": config.interleave,
        "max_retries_per_call": config.max_retries_per_call,
        "prompt_overhead_tokens": config.prompt_overhead_tokens,
        "patch_sha256": _sha256_file(patch_path) if patch_path else None,
        "deepseek_harness_sdk": sdk if sdk is not None else sdk_version(),
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def preflight_report(config: BenchConfig, plan: list[PlannedCall], live: bool) -> dict[str, Any]:
    """Config + safety summary printed before anything runs."""
    max_prompt = max(p.prompt_chars for p in plan)
    worst_prompt_tokens = estimate_tokens("x" * max_prompt) + config.prompt_overhead_tokens
    worst_per_call = worst_case_cost_cny(worst_prompt_tokens, config.max_tokens, config.usd_cny)
    attempts_per_call = 1 + config.max_retries_per_call
    total_worst = worst_per_call * len(plan) * attempts_per_call
    return {
        "live": live,
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "max_tokens": config.max_tokens,
        "planned_calls": len(plan),
        "calls_per_group": config.calls_per_group,
        "max_retries_per_call": config.max_retries_per_call,
        "max_attempts_planned": len(plan) * attempts_per_call,
        "interleave": config.interleave,
        "config_hash_legacy_raw": config_hash(config),
        "max_prompt_chars": max_prompt,
        "worst_case_prompt_tokens_estimate": worst_prompt_tokens,
        "worst_case_cost_per_attempt_cny": round(worst_per_call, 6),
        "worst_case_total_cny": round(total_worst, 4),
        "budget_cap_cny": config.max_cny,
        "budget_ok": total_worst <= config.max_cny,
        "price_table": PRICE_TABLE_META,
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Shared aggregation for live summaries and offline CSV reconciliation.

    ALL totals use the all-attempts billed buckets: the `*_all_attempts`
    columns when present (post-R1.2 CSVs), falling back to the legacy columns
    for the pre-R1.2 stored CSV (100 rows, each exactly 1 attempt, so legacy
    final-attempt values equal all-attempts values — lossless).

    weighted_cache_hit_rate divides the summed buckets; mean_per_request
    averages per-row all-attempts rates. They are not the same measure.
    """
    def _int(row: dict[str, Any], key: str) -> int:
        value = row.get(key)
        return int(value) if value not in (None, "") else 0

    def _bucket(row: dict[str, Any], base: str) -> int:
        value = row.get(f"{base}_all_attempts")
        if value not in (None, ""):
            return int(value)
        return _int(row, base)

    def _row_hit_rate(row: dict[str, Any]) -> float | None:
        value = row.get("cache_hit_rate_all_attempts")
        if value not in (None, ""):
            return float(value)
        value = row.get("cache_hit_rate")
        return float(value) if value not in (None, "") else None

    def _metered(row: dict[str, Any]) -> int:
        value = row.get("metered_attempts")
        if value in (None, ""):
            # legacy rows (pre-R1.1 CSV): ok rows always carried one metered attempt
            return int(row.get("attempts") or 1) if row.get("status") == "ok" else 0
        return int(value)

    def _unknown_spend(row: dict[str, Any]) -> int:
        value = row.get("unknown_spend_attempts")
        if value in (None, ""):
            return 1 if row.get("status") == "unknown_cost" else 0
        return int(value)

    ok_rows = [r for r in rows if r.get("status") == "ok"]
    hit_rates = [rate for r in ok_rows if (rate := _row_hit_rate(r)) is not None]
    finish: dict[str, int] = {}
    for r in rows:
        key = str(r.get("finish_reason") or "none")
        finish[key] = finish.get(key, 0) + 1
    task_valid: dict[str, int] = {}
    for r in rows:
        key = str(r.get("task_valid") or "unknown")
        task_valid[key] = task_valid.get(key, 0) + 1
    uncached = sum(_bucket(r, "uncached_input_tokens") for r in rows)
    cache_read = sum(_bucket(r, "cache_read_tokens") for r in rows)
    cache_write = sum(_bucket(r, "cache_write_tokens") for r in rows)
    total_prompt = sum(_bucket(r, "total_prompt_tokens") for r in rows)
    output_all = sum(_bucket(r, "output_tokens") for r in rows)
    unknown_spend_attempts = sum(_unknown_spend(r) for r in rows)
    return {
        "logical_calls": len(rows),
        "completed_calls": len(ok_rows),
        "provider_attempts": sum(_int(r, "attempts") or 1 for r in rows),
        "metered_attempts": sum(_metered(r) for r in rows),
        "unknown_spend_calls": sum(1 for r in rows if r.get("status") == "unknown_cost"),
        "unknown_spend_attempts": unknown_spend_attempts,
        "response_accepted": len(ok_rows),
        "task_valid_counts": task_valid,
        "uncached_input_tokens": uncached,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "cache_write_reported": any(
            str(r.get("cache_write_reported_all_attempts",
                      r.get("cache_write_reported", ""))).lower() == "true" for r in rows
        ),
        "total_prompt_tokens": total_prompt,
        "output_tokens_all_attempts": output_all,
        "weighted_cache_hit_rate": (cache_read / total_prompt) if total_prompt > 0 else None,
        "mean_per_request_cache_hit_rate": (
            sum(hit_rates) / len(hit_rates) if hit_rates else None
        ),
        "finish_reason_distribution": finish,
        "cost_cny_peak": round(sum(float(r.get("cost_cny_peak") or 0) for r in rows), 10),
        "cost_cny_tiered": round(sum(float(r.get("cost_cny_tiered") or 0) for r in rows), 10),
        "cost_completeness": "complete" if unknown_spend_attempts == 0 else "partial_unknown",
    }


class Benchmark:
    def __init__(
        self,
        config: BenchConfig,
        runner: Runner,
        output_dir: Path,
        run_id: str,
        live: bool,
        patch_path: Path | None = None,
        authorized_cap_cny: float | None = None,
    ) -> None:
        self.config = config
        self.runner = runner
        self.output_dir = output_dir
        self.run_id = run_id
        self.live = live
        self.patch_path = patch_path
        self.authorized_cap_cny = authorized_cap_cny if authorized_cap_cny is not None else config.max_cny
        self.plan = build_call_plan(config.calls_per_group, run_id, config.interleave)
        self.rows: list[dict[str, Any]] = []
        self.aborted_reason: str | None = None
        self._salt = config_hash(config) + ":" + run_id

    def run(self) -> dict[str, Any]:
        check_length_invariants(self.config.calls_per_group)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "preflight.json").write_text(
            json.dumps(self.preflight(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if not self.preflight()["budget_ok"]:
            self.aborted_reason = "preflight: worst-case total exceeds budget cap"
            return self._finalize()

        max_prompt = max(p.prompt_chars for p in self.plan)
        worst_prompt_tokens = estimate_tokens("x" * max_prompt) + self.config.prompt_overhead_tokens
        gate = BudgetGate(
            cap_cny=self.config.max_cny,
            worst_case_per_call_cny=worst_case_cost_cny(
                worst_prompt_tokens, self.config.max_tokens, self.config.usd_cny
            ),
        )

        attempts_per_call = 1 + self.config.max_retries_per_call
        for position, planned in enumerate(self.plan):
            remaining_attempts = (len(self.plan) - position) * attempts_per_call
            try:
                gate.check_can_start(remaining_attempts)
            except BudgetExceeded as exc:
                self.aborted_reason = str(exc)
                break
            row = self._execute_call(planned, position)
            self.rows.append(row)
            gate.record_spend(row["cost_cny_peak"])  # conservative: meter at peak
            self._write_calls_csv()  # persist after every call: crash-safe
            if row["status"] in ("fail_closed", "unknown_cost"):
                self.aborted_reason = f"{row['status']} stop: " + (row.get("error") or "unknown")
                break
        return self._finalize()

    def _execute_call(self, planned: PlannedCall, position: int) -> dict[str, Any]:
        attempts: list[AttemptRecord] = []
        last_outcome: RunnerOutcome | None = None
        started = ended = _utcnow()
        for attempt_index in range(1 + self.config.max_retries_per_call):
            started = _utcnow()
            outcome = self.runner.run(planned.session_id, planned.prompt)
            ended = _utcnow()
            last_outcome = outcome
            # Usage is extracted from EVERY attempt, success or failure:
            # a failed attempt with usage still bills.
            usage: UsageRecord | None = None
            usage_error: str | None = None
            if outcome.events:
                try:
                    usage = extract_settled_usage(outcome.events)
                except UsageUnavailable as exc:
                    usage_error = f"{USAGE_UNAVAILABLE_PREFIX}{exc}"
            error: str | None = outcome.error
            if outcome.ok:
                if usage is None:
                    # Fail-closed: a successful-looking response without
                    # trustworthy usage corrupts all downstream accounting.
                    status = "fail_closed"
                    error = usage_error or f"{USAGE_UNAVAILABLE_PREFIX}no usage events"
                else:
                    status = "ok"
            else:
                if usage is not None:
                    status = "error"  # metered failure: billed, retryable
                elif outcome.error_kind == "local_rejected":
                    status = "locally_rejected"  # proven never sent: no spend
                else:
                    status = "unknown_cost"  # may have left the machine: STOP
                    error = error or "failed attempt without usage"
            attempts.append(
                AttemptRecord(
                    attempt_index=attempt_index,
                    status=status,
                    usage=usage,
                    finish_reason=outcome.finish_reason,
                    error=error,
                )
            )
            if status == "ok":
                break
            if status in ("unknown_cost",) or (error or "").startswith(USAGE_UNAVAILABLE_PREFIX):
                break  # fail-closed: retrying cannot fix unknown/corrupt accounting
        row = self._row(planned, position, attempts, last_outcome, started, ended)
        return row

    def _row(
        self,
        planned: PlannedCall,
        position: int,
        attempts: list[AttemptRecord],
        outcome: RunnerOutcome | None,
        started: datetime,
        ended: datetime,
    ) -> dict[str, Any]:
        final = attempts[-1]
        usage = final.usage
        status = final.status
        response_accepted = status == "ok" and usage is not None
        task_valid = self._assess_task_valid(planned, outcome, final)
        response_sha16 = None
        if outcome is not None and outcome.final_response:
            response_sha16 = hashlib.sha256(outcome.final_response.encode("utf-8")).hexdigest()[:16]
        tier = classify_price_tier(started)
        metered = [a.usage for a in attempts if a.usage is not None]
        cost_peak = sum(
            cost_for_usage(u, "peak", self.config.usd_cny).cost_cny for u in metered
        )
        cost_tiered = sum(
            cost_for_usage(u, classify_price_tier(started), self.config.usd_cny).cost_cny
            for u in metered
        )
        # R1.2-F2.1: billed totals across ALL metered attempts. The legacy
        # columns keep their final-attempt meaning; the *_all_attempts columns
        # are the only source for aggregation, billing and assertions.
        all_uncached = sum(u.uncached_input_tokens for u in metered)
        all_read = sum(u.cache_read_tokens for u in metered)
        all_write_reported = bool(metered) and all(u.cache_write_reported for u in metered)
        all_write = sum(u.cache_write_tokens or 0 for u in metered) if all_write_reported else None
        all_output = sum(u.output_tokens for u in metered)
        all_total_prompt = all_uncached + all_read + (all_write or 0)
        all_hit_rate = (all_read / all_total_prompt) if all_total_prompt > 0 else None
        unknown_spend_attempts = sum(1 for a in attempts if a.usage is None and a.status == "unknown_cost")
        return {
            "position": position,
            "group": planned.group,
            "index": planned.index,
            "session_id_hash": hash_identifier(planned.session_id, salt=self._salt),
            "prompt_sha16": planned.prompt_sha16,
            "prompt_chars": planned.prompt_chars,
            "utc_start": started.isoformat(),
            "utc_end": ended.isoformat(),
            "latency_ms": int((ended - started).total_seconds() * 1000),
            "attempts": len(attempts),
            "metered_attempts": len(metered),
            "unknown_spend_attempts": unknown_spend_attempts,
            "status": status,
            "finish_reason": final.finish_reason,
            "response_accepted": response_accepted,
            "task_valid": task_valid,
            "response_sha16": response_sha16,
            "wire_model": outcome.wire_model if outcome else None,
            "price_tier": tier,
            # --- legacy columns: FINAL attempt only (kept for old-CSV continuity) ---
            "uncached_input_tokens": usage.uncached_input_tokens if usage else None,
            "cache_read_tokens": usage.cache_read_tokens if usage else None,
            "cache_write_tokens": usage.cache_write_tokens if usage else None,
            "cache_write_reported": usage.cache_write_reported if usage else False,
            "output_tokens": usage.output_tokens if usage else None,
            "total_prompt_tokens": usage.total_prompt_tokens if usage else None,
            "cache_hit_rate": usage.cache_hit_rate if usage else None,
            "final_attempt_usage": (
                json.dumps(usage.as_dict(), sort_keys=True) if usage else None
            ),
            # --- billed totals across ALL metered attempts (aggregation source) ---
            "uncached_input_tokens_all_attempts": all_uncached,
            "cache_read_tokens_all_attempts": all_read,
            "cache_write_tokens_all_attempts": all_write,
            "cache_write_reported_all_attempts": all_write_reported,
            "output_tokens_all_attempts": all_output,
            "total_prompt_tokens_all_attempts": all_total_prompt,
            "cache_hit_rate_all_attempts": all_hit_rate,
            "cost_cny_peak": cost_peak,
            "cost_cny_tiered": cost_tiered,
            "error": final.error,
        }

    @staticmethod
    def _assess_task_valid(
        planned: PlannedCall, outcome: RunnerOutcome | None, final: AttemptRecord
    ) -> str:
        """R1.1-F3: 'valid' requires completed finish AND exact expected JSON.
        Truncated (max-tokens) or wrong content -> 'invalid'; nothing to
        check (no response captured) -> 'unknown'."""
        if final.finish_reason != "completed":
            return "invalid" if (outcome and outcome.final_response) else "unknown"
        if outcome is None or not outcome.final_response:
            return "unknown"
        return "valid" if outcome.final_response.strip() == expected_response(
            planned.group, planned.index
        ) else "invalid"

    def preflight(self) -> dict[str, Any]:
        return preflight_report(self.config, self.plan, self.live)

    def summary(self) -> dict[str, Any]:
        groups: dict[str, Any] = {}
        for group in ("A", "B", "C", "D"):
            group_rows = [r for r in self.rows if r["group"] == group]
            agg = aggregate_rows(group_rows)
            groups[group] = {
                "ok_calls": agg["completed_calls"],
                "cache_hit_rate_mean": agg["mean_per_request_cache_hit_rate"],
                "weighted_cache_hit_rate": agg["weighted_cache_hit_rate"],
                "cache_read_tokens": agg["cache_read_tokens"],
                "uncached_input_tokens": agg["uncached_input_tokens"],
                "cache_write_tokens": agg["cache_write_tokens"],
                "output_tokens_all_attempts": agg["output_tokens_all_attempts"],
                "total_prompt_tokens": agg["total_prompt_tokens"],
                "finish_reason_distribution": agg["finish_reason_distribution"],
                "cost_cny_peak": round(agg["cost_cny_peak"], 6),
                "cost_cny_tiered": round(agg["cost_cny_tiered"], 6),
            }
        overall = aggregate_rows(self.rows)
        overall["known_measured_cost_cny_peak"] = overall["cost_cny_peak"]
        overall["known_measured_cost_cny_tiered"] = overall["cost_cny_tiered"]
        return {
            "run_id": self.run_id,
            "live": self.live,
            "config_hash_legacy_raw": config_hash(self.config),
            "effective_config_fingerprint": effective_config_fingerprint(
                self.config, patch_path=self.patch_path
            ),
            "planned_calls": len(self.plan),
            "executed_calls": len(self.rows),
            "ok_calls": overall["completed_calls"],
            "failed_calls": len(self.rows) - overall["completed_calls"],
            "aborted_reason": self.aborted_reason,
            "overall": overall,
            "groups": groups,
            "consistency": {
                "groups_sum_equals_overall": all(
                    sum(groups[g][field] for g in groups) == overall[key]
                    for field, key in (
                        ("uncached_input_tokens", "uncached_input_tokens"),
                        ("cache_read_tokens", "cache_read_tokens"),
                        ("total_prompt_tokens", "total_prompt_tokens"),
                        ("output_tokens_all_attempts", "output_tokens_all_attempts"),
                    )
                ),
            },
            "confounds": [
                "Group A reuses one session: hit-rate trend is confounded by growing history length.",
                "Group D varies early prefix bytes: it measures prefix sensitivity, not the API's in-history system-prompt-update feature.",
                "Costs labeled 'peak' are conservative upper bounds; 'tiered' uses per-call timestamps (weekend/off-peak rule).",
                "mean_per_request_cache_hit_rate averages per-call ratios; weighted_cache_hit_rate divides token totals. They are not the same measure.",
            ],
        }

    def _csv_fields(self) -> list[str]:
        return [
            "position", "group", "index", "session_id_hash", "prompt_sha16", "prompt_chars",
            "utc_start", "utc_end", "latency_ms", "attempts", "metered_attempts",
            "unknown_spend_attempts", "status",
            "finish_reason", "response_accepted", "task_valid", "response_sha16",
            "wire_model", "price_tier",
            # legacy final-attempt columns (unchanged meaning; old CSV reads losslessly)
            "uncached_input_tokens", "cache_read_tokens",
            "cache_write_tokens", "cache_write_reported", "output_tokens", "total_prompt_tokens",
            "cache_hit_rate", "final_attempt_usage",
            # billed totals across all metered attempts (the aggregation/billing source)
            "uncached_input_tokens_all_attempts", "cache_read_tokens_all_attempts",
            "cache_write_tokens_all_attempts", "cache_write_reported_all_attempts",
            "output_tokens_all_attempts", "total_prompt_tokens_all_attempts",
            "cache_hit_rate_all_attempts",
            "cost_cny_peak", "cost_cny_tiered",
            "error",
        ]

    def _write_calls_csv(self) -> None:
        path = self.output_dir / "calls.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self._csv_fields())
            writer.writeheader()
            for row in self.rows:
                writer.writerow({k: redact_obj(v) if isinstance(v, str) else v for k, v in row.items()})

    def _finalize(self) -> dict[str, Any]:
        self.runner.close()
        self._write_calls_csv()
        summary = self.summary()
        (self.output_dir / "summary.json").write_text(
            json.dumps(redact_obj(summary), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        snapshot = {
            "config": redact_obj(self.config.raw),
            "effective_config": {
                "model": self.config.model,
                "reasoning_effort": self.config.reasoning_effort,
                "max_tokens": self.config.max_tokens,
                "calls_per_group": self.config.calls_per_group,
                "interleave": self.config.interleave,
                "max_retries_per_call": self.config.max_retries_per_call,
                "prompt_overhead_tokens": self.config.prompt_overhead_tokens,
                "patch_sha256": (
                    _sha256_file(self.patch_path) if self.patch_path else None
                ),
                "deepseek_harness_sdk": sdk_version(),
            },
            "budget": {
                "authorized_cap_cny": self.authorized_cap_cny,
                "runtime_cap_cny": self.config.max_cny,
                "note": "runtime cap may be tightened to the platform balance; that changes spend authorization, not the experiment fingerprint",
            },
            "config_hash_legacy_raw": config_hash(self.config),
            "effective_config_fingerprint": effective_config_fingerprint(
                self.config, patch_path=self.patch_path
            ),
            "run_id": self.run_id,
            "live": self.live,
            "created_utc": _utcnow().isoformat(),
        }
        (self.output_dir / "config_snapshot.json").write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return summary


def require_live_key(env: dict[str, str] | None = None) -> None:
    """Live mode is forbidden without an explicit key in the environment."""
    env = os.environ if env is None else env
    if not env.get("DEEPSEEK_API_KEY", "").strip():
        raise PermissionError(
            "live mode requires DEEPSEEK_API_KEY in the environment; refusing to run"
        )
