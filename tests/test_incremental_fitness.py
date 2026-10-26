"""R1.10 Task D tests: incremental intervention cost/calls, no-op feedback,
infra exclusion, and replay consistency. Uses stub runners/judges (no docker)."""

import json
from pathlib import Path

import numpy as np
import pytest

from causalevo.eval.harness_agent import AgentRunOutcome
from causalevo.eval.runtime_budget import RuntimeBudget
from causalevo.eval.task_spec import load_task
from causalevo.evolution.online_evolution import OnlineEvolutionController
from causalevo.usage import UsageRecord

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_phase4_r19_pilot import run_row  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FRONT = REPO / "results" / "phase3" / "evolution" / "pareto_front.json"
MANIFEST = REPO / "configs" / "phase3_artifact_manifest.json"
CTX = {"failure_type": "knowledge", "edited": True, "invalid": False,
       "failure_kind": "none"}


class _Report:
    def __init__(self, ok, invalid_reason=None):
        self.visible_passed = ok
        self.sealed_passed = ok
        self.invalid_reason = invalid_reason
        self.timed_out = False
        self.visible_failures = [] if ok else ["visible-check-1"]


class _Judge:
    """Attempt-1 fails, attempt-2 passes (drives the retry path)."""

    def __init__(self):
        self._n = 0

    def grade(self, spec, ws_root):
        self._n += 1
        return _Report(ok=self._n > 1)


class _StubRunner:
    """Simulates a provider run: settles N usage records into the budget and
    writes the reference fix (or a wrong file for attempt 1)."""

    def __init__(self, n_usage, wrong=False, failure_kind="none"):
        self.n_usage = n_usage
        self.wrong = wrong
        self.failure_kind = failure_kind

    def run_task(self, spec, workspace, policy_id, budget, api_key,
                 extra_prompt=None):
        for _ in range(self.n_usage):
            budget.after_provider_request(
                UsageRecord(uncached_input_tokens=100, cache_read_tokens=50,
                            output_tokens=10),
                price_tier="off_peak", usd_cny=7.10)
        content = ("def clamp_value(x, lo, hi):\n    return min(max(x, lo), lo)\n"
                   if self.wrong else
                   "def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi)\n")
        (workspace / spec.entry_file).write_text(content, encoding="utf-8")
        return AgentRunOutcome(
            task_id=spec.task_id, policy_id=policy_id,
            finish_reason="completed", final_response_sha16=None,
            failure_kind=self.failure_kind, budget_stop_reason=None,
            usage=None, ledger=budget.snapshot(), events_slim=[],
            duration_ms=1, runner="stub", provider_kind="fake")


def _ctl():
    return OnlineEvolutionController(pareto_front_path=FRONT,
                                     manifest_path=MANIFEST)


def test_incremental_cost_excludes_attempt1():
    spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")
    ctl = _ctl()
    rng = np.random.default_rng(1)
    record = run_row(spec, "CEA-v2-online", 20261026, _Judge(),
                     lambda attempt: _StubRunner(3 if attempt == 0 else 2,
                                                 wrong=attempt == 0),
                     rng=rng, controller=ctl, run_id="inc", task_index=0)
    assert record["retried"] is True
    # attempt 1 = 3 usage records, attempt 2 = 2 records (incremental)
    a1_cost = record["attempt_1_cost_cny"]
    a2_cost = record["attempt_2_cost_cny"]
    assert a1_cost > 0 and a2_cost > 0
    assert record["attempt_2_provider_requests"] == 2
    assert record["attempt_1_provider_requests"] == 3
    cand = next(c for c in ctl.population if c.genome_id == record["selected_genome_id"])
    assert cand.costs == pytest.approx(a2_cost), \
        "candidate fitness must use incremental intervention cost only"
    assert cand.calls == 2
    assert cand.costs != pytest.approx(a1_cost + a2_cost), \
        "attempt-1 cost must NOT enter candidate fitness"


def test_noop_selection_measured_exactly_once():
    spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")
    ctl = _ctl()
    # force the no-op genome (all genes off) to be selected
    from causalevo.evolution.genome import InterventionGenome
    noop = InterventionGenome((0, 0, 0, 0, 0, 0))
    for c in ctl.population:
        c.genome = noop
    rng = np.random.default_rng(2)
    record = run_row(spec, "CEA-v2-online", 20261026, _Judge(),
                     lambda attempt: _StubRunner(1, wrong=True),
                     rng=rng, controller=ctl, run_id="noop", task_index=0)
    assert record["retried"] is False, "no-op must not trigger a model retry"
    assert record["controller_update"] is not None
    cand = ctl.population[0]
    assert cand.n == 1, "no-op must be measured exactly once"
    assert cand.costs == 0.0 and cand.calls == 0
    assert record["controller_update"]["updated"] is True


def test_infra_never_becomes_behavioral_reward():
    spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")
    ctl = _ctl()
    rng = np.random.default_rng(3)
    record = run_row(spec, "CEA-v2-online", 20261026, _Judge(),
                     lambda attempt: _StubRunner(1, wrong=True,
                                                 failure_kind="unknown_cost"),
                     rng=rng, controller=ctl, run_id="infra", task_index=0)
    cand = next(c for c in ctl.population
                if c.genome_id == record["selected_genome_id"]) \
        if record["selected_genome_id"] else None
    assert record["controller_update"]["updated"] is False
    if cand is not None:
        assert cand.n == 0, "infra must not update behavior statistics"


def test_event_log_replays_to_same_state(tmp_path):
    spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")
    ctl = _ctl()
    rng = np.random.default_rng(4)
    for i in range(2):
        run_row(spec, "CEA-v2-online", 20261026, _Judge(),
                lambda attempt: _StubRunner(3 if attempt == 0 else 2,
                                            wrong=attempt == 0),
                rng=rng, controller=ctl, run_id=f"replay-{i}", task_index=i)
    log = tmp_path / "events.jsonl"
    with log.open("w", encoding="utf-8") as fh:
        for e in ctl.events:
            fh.write(json.dumps(e, sort_keys=True) + "\n")
    re = OnlineEvolutionController.replay(log, pareto_front_path=FRONT,
                                          manifest_path=MANIFEST)
    a, b = ctl.state_dict(), re.state_dict()
    assert [c["genome_id"] for c in a["population"]] == \
           [c["genome_id"] for c in b["population"]]
    assert [(c["n"], c["successes"], c["costs"], c["calls"])
            for c in a["population"]] == \
           [(c["n"], c["successes"], c["costs"], c["calls"])
            for c in b["population"]]
