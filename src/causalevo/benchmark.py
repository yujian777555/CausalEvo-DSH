"""Benchmark orchestration: plan -> preflight -> gated calls -> evidence.

Safety properties:
- dry-run is the default; --live is an explicit opt-in requiring the key.
- a BudgetGate refuses any new live call that cannot be proven within cap.
- usage missing/malformed after a live attempt -> fail-closed: stop the run,
  keep already-incurred costs marked, never fabricate numbers.
- every attempt (including failures/retries) is metered and persisted.
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
from .scenarios import PlannedCall, build_call_plan, check_length_invariants
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
    canonical = json.dumps(config.raw, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def preflight_report(config: BenchConfig, plan: list[PlannedCall], live: bool) -> dict[str, Any]:
    """Config + safety summary printed before anything runs."""
    max_prompt = max(p.prompt_chars for p in plan)
    worst_prompt_tokens = estimate_tokens("x" * max_prompt) + config.prompt_overhead_tokens
    worst_per_call = worst_case_cost_cny(worst_prompt_tokens, config.max_tokens, config.usd_cny)
    total_worst = worst_per_call * len(plan) * (1 + config.max_retries_per_call)
    return {
        "live": live,
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "max_tokens": config.max_tokens,
        "planned_calls": len(plan),
        "calls_per_group": config.calls_per_group,
        "max_retries_per_call": config.max_retries_per_call,
        "interleave": config.interleave,
        "config_hash": config_hash(config),
        "max_prompt_chars": max_prompt,
        "worst_case_prompt_tokens_estimate": worst_prompt_tokens,
        "worst_case_cost_per_call_cny": round(worst_per_call, 6),
        "worst_case_total_cny": round(total_worst, 4),
        "budget_cap_cny": config.max_cny,
        "budget_ok": total_worst <= config.max_cny,
        "price_table": PRICE_TABLE_META,
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Benchmark:
    def __init__(
        self,
        config: BenchConfig,
        runner: Runner,
        output_dir: Path,
        run_id: str,
        live: bool,
    ) -> None:
        self.config = config
        self.runner = runner
        self.output_dir = output_dir
        self.run_id = run_id
        self.live = live
        self.plan = build_call_plan(config.calls_per_group, run_id, config.interleave)
        self.rows: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
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

        for position, planned in enumerate(self.plan):
            remaining = len(self.plan) - position
            try:
                gate.check_can_start(remaining)
            except BudgetExceeded as exc:
                self.aborted_reason = str(exc)
                break
            row = self._execute_call(planned, position)
            self.rows.append(row)
            gate.record_spend(row["cost_cny_peak"])  # conservative: meter at peak
            self._write_calls_csv()  # persist after every call: crash-safe
            if row["status"] == "fail_closed":
                self.aborted_reason = "fail-closed stop: " + (row.get("error") or "unknown")
                break
        return self._finalize()

    def _execute_call(self, planned: PlannedCall, position: int) -> dict[str, Any]:
        attempts: list[AttemptRecord] = []
        last_outcome: RunnerOutcome | None = None
        for attempt_index in range(1 + self.config.max_retries_per_call):
            started = _utcnow()
            outcome = self.runner.run(planned.session_id, planned.prompt)
            ended = _utcnow()
            last_outcome = outcome
            usage: UsageRecord | None = None
            error: str | None = outcome.error
            if outcome.ok:
                try:
                    usage = extract_settled_usage(outcome.events)
                except UsageUnavailable as exc:
                    # Fail-closed: a successful-looking response without
                    # trustworthy usage corrupts all downstream accounting.
                    outcome = RunnerOutcome(ok=False, error=f"{USAGE_UNAVAILABLE_PREFIX}{exc}")
                    error = outcome.error
            attempts.append(
                AttemptRecord(
                    attempt_index=attempt_index,
                    status="ok" if outcome.ok else "error",
                    usage=usage,
                    finish_reason=outcome.finish_reason,
                    error=error,
                )
            )
            if outcome.ok:
                break
            if error and error.startswith(USAGE_UNAVAILABLE_PREFIX):
                break  # fail-closed: retrying cannot fix accounting corruption
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
        if final.error and final.error.startswith(USAGE_UNAVAILABLE_PREFIX):
            status = "fail_closed"
        elif final.status == "ok" and usage is None:
            status = "fail_closed"
        elif final.status == "ok":
            status = "ok"
        else:
            status = "error" if usage is None else "fail_closed"
        tier = classify_price_tier(started)
        cost_peak = sum(
            cost_for_usage(a.usage, "peak", self.config.usd_cny).cost_cny
            for a in attempts if a.usage is not None
        )
        cost_tiered = sum(
            cost_for_usage(a.usage, classify_price_tier(started), self.config.usd_cny).cost_cny
            for a in attempts if a.usage is not None
        )
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
            "status": status,
            "finish_reason": final.finish_reason,
            "wire_model": outcome.wire_model if outcome else None,
            "price_tier": tier,
            "uncached_input_tokens": usage.uncached_input_tokens if usage else None,
            "cache_read_tokens": usage.cache_read_tokens if usage else None,
            "cache_write_tokens": usage.cache_write_tokens if usage else None,
            "output_tokens": usage.output_tokens if usage else None,
            "total_prompt_tokens": usage.total_prompt_tokens if usage else None,
            "cache_hit_rate": usage.cache_hit_rate if usage else None,
            "output_tokens_all_attempts": sum(
                a.usage.output_tokens for a in attempts if a.usage is not None
            ),
            "cost_cny_peak": cost_peak,
            "cost_cny_tiered": cost_tiered,
            "error": final.error,
        }

    def preflight(self) -> dict[str, Any]:
        return preflight_report(self.config, self.plan, self.live)

    def summary(self) -> dict[str, Any]:
        groups: dict[str, Any] = {}
        for group in ("A", "B", "C", "D"):
            rows = [r for r in self.rows if r["group"] == group and r["status"] == "ok"]
            hits = [r["cache_hit_rate"] for r in rows if r["cache_hit_rate"] is not None]
            groups[group] = {
                "ok_calls": len(rows),
                "cache_hit_rate_mean": (sum(hits) / len(hits)) if hits else None,
                "cache_read_tokens": sum(r["cache_read_tokens"] or 0 for r in rows),
                "uncached_input_tokens": sum(r["uncached_input_tokens"] or 0 for r in rows),
                "cache_write_tokens": sum(r["cache_write_tokens"] or 0 for r in rows),
                "output_tokens_all_attempts": sum(r["output_tokens_all_attempts"] for r in rows),
                "total_prompt_tokens": sum(r["total_prompt_tokens"] or 0 for r in rows),
                "cost_cny_peak": round(sum(r["cost_cny_peak"] for r in rows), 6),
                "cost_cny_tiered": round(sum(r["cost_cny_tiered"] for r in rows), 6),
            }
        ok_total = sum(1 for r in self.rows if r["status"] == "ok")
        return {
            "run_id": self.run_id,
            "live": self.live,
            "config_hash": config_hash(self.config),
            "planned_calls": len(self.plan),
            "executed_calls": len(self.rows),
            "ok_calls": ok_total,
            "failed_calls": len(self.rows) - ok_total,
            "aborted_reason": self.aborted_reason,
            "total_cost_cny_peak": round(sum(r["cost_cny_peak"] for r in self.rows), 6),
            "total_cost_cny_tiered": round(sum(r["cost_cny_tiered"] for r in self.rows), 6),
            "groups": groups,
            "confounds": [
                "Group A reuses one session: hit-rate trend is confounded by growing history length.",
                "Group D varies early prefix bytes: it measures prefix sensitivity, not the API's in-history system-prompt-update feature.",
                "Costs labeled 'peak' are conservative upper bounds; 'tiered' uses per-call timestamps (weekend/off-peak rule).",
            ],
        }

    def _csv_fields(self) -> list[str]:
        return [
            "position", "group", "index", "session_id_hash", "prompt_sha16", "prompt_chars",
            "utc_start", "utc_end", "latency_ms", "attempts", "status", "finish_reason",
            "wire_model", "price_tier", "uncached_input_tokens", "cache_read_tokens",
            "cache_write_tokens", "output_tokens", "total_prompt_tokens", "cache_hit_rate",
            "output_tokens_all_attempts", "cost_cny_peak", "cost_cny_tiered", "error",
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
            "config_hash": config_hash(self.config),
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
