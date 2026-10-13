"""F2 failure-injection matrix: every failure mode's billing semantics.

The old FlakyRunner test (failure WITHOUT usage, retried silently) was not a
complete billing test. This matrix pins the required behavior:
- failed attempt WITH usage      -> metered, retry proceeds, both billed
- failed attempt WITHOUT usage   -> unknown_cost, run STOPS, never claimed ¥0
- provider/HTTP failure w/ usage -> metered error
- local rejection before send    -> no spend, run continues
- retry-then-success             -> both attempts metered
"""

import csv
from pathlib import Path

import pytest

from causalevo.benchmark import Benchmark, load_config
from causalevo.runner import FakeRunner, RunnerOutcome
from test_benchmark import usage_event  # same-dir helper (pytest prepends tests/ to sys.path)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "cache_benchmark.yaml"


def _config(calls=2, retries=1):
    config = load_config(CONFIG_PATH)
    object.__setattr__(config, "calls_per_group", calls)
    object.__setattr__(config, "max_retries_per_call", retries)
    return config


def _rows(tmp_path):
    return list(csv.DictReader((tmp_path / "calls.csv").open(encoding="utf-8")))


class TransportFailNoUsage(FakeRunner):
    """Transport exception: request may have left; no usage came back."""

    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        return RunnerOutcome(ok=False, error="ConnectionReset", error_kind="transport", events=[])


class TransportFailWithUsage(FakeRunner):
    """Transport error after a partial response: usage IS available."""

    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        return RunnerOutcome(
            ok=False, error="stream aborted", error_kind="transport",
            events=[usage_event(700, 0, 30)],
        )


class HttpFailWithUsage(FakeRunner):
    """Provider HTTP error carrying billable usage in events."""

    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        return RunnerOutcome(
            ok=False, error="HTTP 500", error_kind="provider",
            events=[usage_event(700, 0, 5)],
        )


class MeteredFlakyRunner(FakeRunner):
    """First attempt fails WITH billable usage; retry succeeds."""

    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        seen = self.__dict__.setdefault("_seen", set())
        if session_id not in seen:
            seen.add(session_id)
            return RunnerOutcome(
                ok=False, error="injected provider 500", error_kind="provider",
                events=[usage_event(700, 0, 10)],
            )
        return super().run(session_id, prompt)


class LocallyRejected(FakeRunner):
    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        return RunnerOutcome(ok=False, error="client-side validation", error_kind="local_rejected")


def test_transport_failure_without_usage_stops_run_unknown_cost(tmp_path):
    bench = Benchmark(config=_config(), runner=TransportFailNoUsage(),
                      output_dir=tmp_path, run_id="pytest", live=False)
    summary = bench.run()
    assert summary["executed_calls"] == 1, "fail-closed: stop after unknown spend"
    assert summary["overall"]["unknown_spend_calls"] == 1
    assert "unknown_cost" in summary["aborted_reason"]
    row = _rows(tmp_path)[0]
    assert row["status"] == "unknown_cost"
    assert float(row["cost_cny_tiered"]) == 0.0  # measured=0 but flagged unknown, not claimed free
    assert summary["overall"]["response_accepted"] == 0


def test_transport_failure_with_usage_is_metered_and_retried(tmp_path):
    bench = Benchmark(config=_config(calls=1), runner=TransportFailWithUsage(),
                      output_dir=tmp_path, run_id="pytest", live=False)
    summary = bench.run()
    assert summary["overall"]["unknown_spend_calls"] == 0
    rows = _rows(tmp_path)
    assert all(r["status"] == "error" for r in rows)
    assert all(int(r["metered_attempts"]) >= 1 for r in rows)
    assert summary["overall"]["cost_cny_tiered"] > 0, "failed attempts still bill"


def test_http_failure_with_usage_metered(tmp_path):
    bench = Benchmark(config=_config(calls=1, retries=0), runner=HttpFailWithUsage(),
                      output_dir=tmp_path, run_id="pytest", live=False)
    summary = bench.run()
    rows = _rows(tmp_path)
    assert len(rows) == 4 and all(r["status"] == "error" for r in rows)
    assert all(int(r["output_tokens_all_attempts"]) == 5 for r in rows)
    assert summary["overall"]["metered_attempts"] == 4  # failed but billed attempts count
    assert summary["overall"]["cost_cny_tiered"] > 0


def test_retry_success_meters_both_attempts(tmp_path):
    bench = Benchmark(config=_config(calls=1), runner=MeteredFlakyRunner(),
                      output_dir=tmp_path, run_id="pytest", live=False)
    summary = bench.run()
    assert summary["ok_calls"] == 4
    rows = _rows(tmp_path)
    assert all(int(r["attempts"]) == 2 for r in rows), "retry must be recorded"
    assert all(int(r["metered_attempts"]) == 2 for r in rows), "failed attempt usage must count"
    assert all(int(r["output_tokens_all_attempts"]) == 10 + 12 for r in rows)
    # R1.2-F2.1: INPUT buckets must also accumulate across failed+success attempts.
    # The injected failed attempt billed (uncached=700, read=0); the legacy
    # columns hold the final (successful) attempt only.
    for r in rows:
        assert int(r["uncached_input_tokens_all_attempts"]) == 700 + int(r["uncached_input_tokens"])
        assert int(r["cache_read_tokens_all_attempts"]) == 0 + int(r["cache_read_tokens"])
        assert int(r["total_prompt_tokens_all_attempts"]) == 700 + int(r["total_prompt_tokens"])
    # costs are computed from ALL attempts: overall input totals must match the rows
    overall = summary["overall"]
    assert overall["uncached_input_tokens"] == sum(
        int(r["uncached_input_tokens_all_attempts"]) for r in rows
    )
    assert overall["cache_read_tokens"] == sum(
        int(r["cache_read_tokens_all_attempts"]) for r in rows
    )


def test_two_metered_failures_both_bill(tmp_path):
    """Fail twice, both with usage: both attempts' buckets and cost accumulate."""
    bench = Benchmark(config=_config(calls=1, retries=1), runner=TransportFailWithUsage(),
                      output_dir=tmp_path, run_id="pytest", live=False)
    summary = bench.run()
    assert summary["ok_calls"] == 0
    rows = _rows(tmp_path)
    assert all(int(r["attempts"]) == 2 and int(r["metered_attempts"]) == 2 for r in rows)
    for r in rows:
        assert int(r["uncached_input_tokens_all_attempts"]) == 1400
        assert int(r["output_tokens_all_attempts"]) == 60
    # cost must equal the bucket sum at EACH ROW's recorded price tier
    # (weekday peak windows make a hard-coded tier calendar-dependent)
    from causalevo.pricing import cost_for_usage
    from causalevo.usage import UsageRecord
    for r in rows:
        per_row = cost_for_usage(UsageRecord(1400, 0, 60, None), r["price_tier"]).cost_cny
        assert abs(float(r["cost_cny_tiered"]) - per_row) < 1e-9
        peak_row = cost_for_usage(UsageRecord(1400, 0, 60, None), "peak").cost_cny
        assert abs(float(r["cost_cny_peak"]) - peak_row) < 1e-9
    expected_tiered = sum(
        cost_for_usage(UsageRecord(1400, 0, 60, None), r["price_tier"]).cost_cny for r in rows
    )
    assert abs(summary["overall"]["cost_cny_tiered"] - expected_tiered) < 1e-9


def test_local_rejection_costs_nothing_and_continues(tmp_path):
    bench = Benchmark(config=_config(calls=1), runner=LocallyRejected(),
                      output_dir=tmp_path, run_id="pytest", live=False)
    summary = bench.run()
    assert summary["executed_calls"] == 4, "local rejections do not stop the run"
    assert summary["aborted_reason"] is None
    assert summary["overall"]["cost_cny_tiered"] == 0
    assert all(r["status"] == "locally_rejected" for r in _rows(tmp_path))
