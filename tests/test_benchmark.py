"""End-to-end dry-run orchestration + failure injection (offline, no key)."""

import csv
import json
from pathlib import Path

import pytest

from causalevo.benchmark import Benchmark, load_config, require_live_key
from causalevo.runner import FakeRunner, RunnerOutcome

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "cache_benchmark.yaml"


def usage_event(uncached: int, cache_read: int, output: int) -> dict:
    return {
        "type": "assistant/message",
        "data": {
            "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}]},
            "usage": {
                "inputTokens": uncached,
                "cacheReadTokens": cache_read,
                "outputTokens": output,
            },
        },
    }


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


def test_summary_overall_equals_group_sums(tmp_path):
    _, summary = _run(tmp_path)
    overall = summary["overall"]
    for key in ("uncached_input_tokens", "cache_read_tokens",
                "total_prompt_tokens", "output_tokens_all_attempts"):
        assert sum(summary["groups"][g][key] for g in "ABCD") == overall[key]
    assert summary["consistency"]["groups_sum_equals_overall"] is True
    assert overall["logical_calls"] == 8 == overall["provider_attempts"]


def test_fake_cache_trend_visible_in_group_a(tmp_path):
    """FakeRunner reads history as cache: A's second call must show cache_read."""
    _, summary = _run(tmp_path)
    assert summary["groups"]["A"]["cache_read_tokens"] > 0
    assert summary["groups"]["B"]["cache_read_tokens"] == 0  # fresh sessions


def test_task_valid_marked_for_fake_completed_responses(tmp_path):
    """FakeRunner answers T000 for everything: only T000-expecting rows validate."""
    _, summary = _run(tmp_path)
    counts = summary["overall"]["task_valid_counts"]
    # valid: A(idx0)+B(idx0,1)+C(idx0)+D(idx0,1) = 6; invalid: A(idx1)+C(idx1) = 2
    assert counts.get("valid") == 6
    assert counts.get("invalid") == 2


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
    assert "fail_closed" in summary["aborted_reason"]
    assert summary["executed_calls"] == 1, "must stop after the first corrupt call"


def test_budget_refusal_aborts_before_spend(tmp_path):
    config = _config(calls_per_group=2, max_cny=0.001)  # deliberately tiny
    bench, summary = _run(tmp_path, config=config)
    assert summary["executed_calls"] == 0
    assert summary["aborted_reason"] is not None
    assert summary["overall"]["cost_cny_peak"] == 0


def test_gate_counts_retry_upper_bound(tmp_path):
    """Preflight must price every remaining ATTEMPT, not just logical calls."""
    config = _config(calls_per_group=1, max_retries=3)
    bench = Benchmark(config=config, runner=FakeRunner(), output_dir=tmp_path,
                      run_id="pytest", live=False)
    preflight = bench.preflight()
    assert preflight["max_attempts_planned"] == 4 * 4
    expected = preflight["worst_case_cost_per_attempt_cny"] * 16
    assert abs(preflight["worst_case_total_cny"] - expected) < 1e-3  # 4dp rounding in preflight


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


def test_response_content_never_persisted_only_hash(tmp_path):
    """Rows store response_sha16, never the raw response text."""
    _run(tmp_path)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert '{"task":"T000","status":"ok"}' not in text
    rows = list(csv.DictReader((tmp_path / "calls.csv").open(encoding="utf-8")))
    assert all(len(r["response_sha16"]) == 16 for r in rows)
