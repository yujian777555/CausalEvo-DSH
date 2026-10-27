"""Offline test for cumulative round-cap accounting (canary/interruption/
resume never resets the cap). No docker, no live calls."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from run_phase4_r19_pilot import GLOBAL_CAP_CNY, _round_spend


def _mk_run(tmp_path, name, settled_costs, unresolved_reserved):
    d = tmp_path / name
    (d / "proxy-ledger").mkdir(parents=True)
    entries = []
    for i, c in enumerate(settled_costs):
        rid = f"r{i}"
        entries.append({"request_id": rid, "state": "RESERVED",
                        "reserved_cny": 0.15704064, "scope": "s"})
        entries.append({"request_id": rid, "state": "SENT"})
        entries.append({"request_id": rid, "state": "SETTLED", "cost_cny": c})
    for rid in unresolved_reserved:
        entries.append({"request_id": rid, "state": "RESERVED",
                        "reserved_cny": 0.15704064, "scope": "s"})
        entries.append({"request_id": rid, "state": "SENT"})
    (d / "proxy-ledger" / "ledger.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return d


def test_round_spend_sums_settled_and_unknown_bound(tmp_path):
    canary = _mk_run(tmp_path, "canary", [0.01, 0.02], [])
    aborted = _mk_run(tmp_path, "aborted", [0.03], ["u1"])
    other = _mk_run(tmp_path, "other", [0.005], [])
    settled, unknown = _round_spend([canary, aborted, other])
    assert settled == pytest.approx(0.065)
    assert unknown == pytest.approx(0.15704064)
    remaining = GLOBAL_CAP_CNY - settled - unknown
    assert remaining == pytest.approx(2.00 - 0.065 - 0.15704064)
    assert remaining < GLOBAL_CAP_CNY, "previous spend must reduce, never reset"


def test_round_spend_empty_runs_have_no_unknown(tmp_path):
    canary = _mk_run(tmp_path, "canary", [0.03], [])
    settled, unknown = _round_spend([canary])
    assert settled == pytest.approx(0.03)
    assert unknown == 0.0
    assert GLOBAL_CAP_CNY - settled - unknown == pytest.approx(1.97)
