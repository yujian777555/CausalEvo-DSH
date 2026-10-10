"""End-to-end dry-run orchestration + failure injection (offline, no key)."""

import csv
import json
from pathlib import Path

import pytest

from causalevo.benchmark import Benchmark, load_config, require_live_key
from causalevo.runner import FakeRunner, RunnerOutcome

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "cache_benchmark.yaml"


def _config(calls_per_group=2, max_cny=10.0, max_retries=1):
    config = load_config(CONFIG_PATH)
    object.__setattr__(config, "calls_per_group", calls_per_group)
    object.__setattr__(config, "max_cny", max_cny)
    object.__setattr__(config, "max_retries_per_call", max_retries)
    return config


def _run(tmp_path, config=None, runner=None):
    config = config or _config()
    runner = runner or FakeRunner()
    bench = Benchmark(config=config, runner=runner, output_dir=tmp_path, run_id="pytest", live=False)
    return bench, bench.run()


def test_dry_run_completes_and_writes_evidence(tmp_path):
    bench, summary = _run(tmp_path)
    assert summary["executed_calls"] == 8  # 2 per group x 4
    assert summary["ok_calls"] == 8
    assert summary["aborted_reason"] is None
    for group in "ABCD":
        assert summary["groups"][group]["ok_calls"] == 2
    assert (tmp_path / "calls.csv").exists()
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "preflight.json").exists()
    assert (tmp_path / "config_snapshot.json").exists()
    rows = list(csv.DictReader((tmp_path / "calls.csv").open(encoding="utf-8")))
    assert len(rows) == 8
    assert {r["group"] for r in rows} == {"A", "B", "C", "D"}
    # session ids are published only as hashes
    assert all(len(r["session_id_hash"]) == 12 for r in rows)


def test_fake_cache_trend_visible_in_group_a(tmp_path):
    """FakeRunner reads history as cache: A's second call must show cache_read."""
    _, summary = _run(tmp_path)
    assert summary["groups"]["A"]["cache_read_tokens"] > 0
    assert summary["groups"]["B"]["cache_read_tokens"] == 0  # fresh sessions


class FlakyRunner(FakeRunner):
    """Fails the first attempt of every call, then succeeds."""

    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        if session_id not in self.__dict__.setdefault("_seen", set()):
            self._seen.add(session_id)
            return RunnerOutcome(ok=False, error="injected transport failure")
        return super().run(session_id, prompt)


def test_retry_accounting_meters_failed_attempts(tmp_path):
    config = _config(calls_per_group=1, max_retries=1)
    runner = FlakyRunner()
    bench = Benchmark(config=config, runner=runner, output_dir=tmp_path, run_id="pytest", live=False)
    summary = bench.run()
    assert summary["ok_calls"] == 4
    rows = list(csv.DictReader((tmp_path / "calls.csv").open(encoding="utf-8")))
    assert all(int(r["attempts"]) == 2 for r in rows), "retry must be recorded"


class CorruptUsageRunner(FakeRunner):
    """Returns ok-looking results with NO usage anywhere: must fail closed."""

    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        return RunnerOutcome(
            ok=True,
            final_response="{}",
            finish_reason="completed",
            events=[{"type": "assistant/message", "data": {"message": {}}}],
        )


def test_missing_usage_fails_closed_and_stops_run(tmp_path):
    config = _config(calls_per_group=2)
    bench = Benchmark(config=config, runner=CorruptUsageRunner(), output_dir=tmp_path,
                      run_id="pytest", live=False)
    summary = bench.run()
    assert summary["ok_calls"] == 0
    assert summary["aborted_reason"] is not None
    assert "fail-closed" in summary["aborted_reason"]
    assert summary["executed_calls"] == 1, "must stop after the first corrupt call"


class AlwaysFailRunner(FakeRunner):
    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        return RunnerOutcome(ok=False, error="permanent failure")


def test_persistent_failure_records_attempts_without_stopping(tmp_path):
    config = _config(calls_per_group=1, max_retries=1)
    bench = Benchmark(config=config, runner=AlwaysFailRunner(), output_dir=tmp_path,
                      run_id="pytest", live=False)
    summary = bench.run()
    assert summary["ok_calls"] == 0
    assert summary["executed_calls"] == 4  # errors don't abort; only fail-closed does
    rows = list(csv.DictReader((tmp_path / "calls.csv").open(encoding="utf-8")))
    assert all(r["status"] == "error" for r in rows)


def test_budget_refusal_aborts_before_spend(tmp_path):
    config = _config(calls_per_group=2, max_cny=0.001)  # deliberately tiny
    bench, summary = _run(tmp_path, config=config)
    assert summary["executed_calls"] == 0
    assert summary["aborted_reason"] is not None
    assert summary["total_cost_cny_peak"] == 0


def test_live_key_required(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(PermissionError):
        require_live_key()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    require_live_key()  # no raise


def test_no_key_material_in_any_output(tmp_path):
    monkey_key = "sk-" + "z9y8x7w6" * 4
    import os
    os.environ["DEEPSEEK_API_KEY"] = monkey_key
    try:
        _run(tmp_path)
    finally:
        del os.environ["DEEPSEEK_API_KEY"]
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert monkey_key not in path.read_text(encoding="utf-8", errors="replace")
