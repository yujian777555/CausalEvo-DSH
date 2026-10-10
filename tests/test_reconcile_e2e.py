"""F2.3: offline end-to-end samples — run benchmark into a CSV, then reconcile
that CSV and require every internal-consistency check to pass. Fully offline."""

import json
from pathlib import Path

from causalevo.benchmark import Benchmark, load_config
from causalevo.reconcile import reconcile

from test_benchmark import _config
from test_failure_metering import (
    LocallyRejected,
    MeteredFlakyRunner,
    TransportFailNoUsage,
)


def _bench(tmp_path, runner, retries=1):
    bench = Benchmark(config=_config(calls_per_group=1, max_retries=retries), runner=runner,
                      output_dir=tmp_path, run_id="pytest", live=False)
    summary = bench.run()
    recon = reconcile(tmp_path / "calls.csv")
    return summary, recon


def test_metered_fail_then_retry_success_csv_reconciles(tmp_path):
    summary, recon = _run = _bench(tmp_path, MeteredFlakyRunner())
    assert summary["ok_calls"] == 4
    assert recon["all_checks_ok"], json.dumps(recon["checks"], indent=2)
    overall = recon["overall"]
    assert overall["metered_attempts"] == 8  # 4 failed-with-usage + 4 ok
    assert overall["unknown_spend_attempts"] == 0
    assert overall["cost_completeness"] == "complete"


def test_local_rejected_csv_reconciles_with_zero_cost(tmp_path):
    summary, recon = _bench(tmp_path, LocallyRejected())
    assert recon["all_checks_ok"], json.dumps(recon["checks"], indent=2)
    assert recon["overall"]["cost_cny_tiered"] == 0
    assert recon["overall"]["cost_completeness"] == "complete"


def test_unknown_cost_csv_reconciles_and_flags_incomplete(tmp_path):
    summary, recon = _bench(tmp_path, TransportFailNoUsage())
    assert summary["overall"]["unknown_spend_calls"] == 1
    assert recon["all_checks_ok"], json.dumps(recon["checks"], indent=2)
    assert recon["overall"]["unknown_spend_attempts"] == 1
    assert recon["overall"]["cost_completeness"] == "partial_unknown"
