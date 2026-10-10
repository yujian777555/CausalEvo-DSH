"""F3: API success vs task output validity are separate axes."""

from causalevo.benchmark import Benchmark
from causalevo.runner import RunnerOutcome

from test_benchmark import _config, usage_event
import csv


class ScriptedRunner:
    """Returns a fixed outcome per call."""

    def __init__(self, outcome):
        self._outcome = outcome

    def run(self, session_id, prompt):
        return self._outcome

    def close(self):
        return None


def _run_one(tmp_path, outcome):
    bench = Benchmark(config=_config(calls_per_group=1, max_retries=0), runner=ScriptedRunner(outcome),
                      output_dir=tmp_path, run_id="pytest", live=False)
    bench.run()
    return list(csv.DictReader((tmp_path / "calls.csv").open(encoding="utf-8")))


def test_completed_with_exact_json_is_valid(tmp_path):
    outcome = RunnerOutcome(
        ok=True, final_response='{"task":"T000","status":"ok"}', finish_reason="completed",
        events=[usage_event(700, 0, 12)],
    )
    rows = _run_one(tmp_path, outcome)
    # B row expects T000 -> valid; C row (index 0) also T000; A idx0 T000
    assert rows[0]["task_valid"] == "valid"  # position 0 = A0
    assert rows[0]["response_accepted"] == "True"


def test_max_tokens_is_metered_but_not_task_valid(tmp_path):
    outcome = RunnerOutcome(
        ok=True, final_response='{"task":"T0', finish_reason="max-tokens",
        events=[usage_event(700, 0, 64)],
    )
    rows = _run_one(tmp_path, outcome)
    assert all(r["response_accepted"] == "True" for r in rows)  # usage is trustworthy
    assert all(r["task_valid"] == "invalid" for r in rows)      # truncated output is not a task success


def test_completed_with_wrong_json_is_invalid(tmp_path):
    outcome = RunnerOutcome(
        ok=True, final_response='{"task":"T999","status":"ok"}', finish_reason="completed",
        events=[usage_event(700, 0, 12)],
    )
    rows = _run_one(tmp_path, outcome)
    assert all(r["task_valid"] == "invalid" for r in rows)


def test_completed_without_captured_response_is_unknown(tmp_path):
    outcome = RunnerOutcome(
        ok=True, final_response="", finish_reason="completed",
        events=[usage_event(700, 0, 12)],
    )
    rows = _run_one(tmp_path, outcome)
    assert all(r["task_valid"] == "unknown" for r in rows)
