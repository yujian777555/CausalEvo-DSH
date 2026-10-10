"""F1: the committed live CSV is the source of truth; aggregates must match it.

Planner's independent audit (planner/reviews/CE-DSH-P0-R1-review.md) computed
these constants from the raw CSV. This test re-derives them and fails on any
drift, so reports can never again hand-copy wrong totals.
"""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from causalevo.benchmark import aggregate_rows
from causalevo.reconcile import reconcile

CSV_PATH = Path(__file__).resolve().parents[1] / "results" / "phase0" / "live" / "calls.csv"

EXPECTED = {
    "rows": 100,
    "uncached_input_tokens": 27316,
    "cache_read_tokens": 29184,
    "total_prompt_tokens": 56500,
    "output_tokens": 3833,
    "weighted_cache_hit_rate": 29184 / 56500,
    "cost_cny_tiered": 0.0460417392,
    "finish": {"completed": 59, "max-tokens": 41},
    "max_tokens_by_group": {"A": 0, "B": 13, "C": 10, "D": 18},
    "csv_sha256": "1961bdd81a7f6a4ad4169d6f246530ed3df3170f70948f85de13ca136e364c59",
}


@pytest.fixture(scope="module")
def rows():
    assert CSV_PATH.exists(), "committed live CSV missing"
    return list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))


def test_csv_immutable_hash(rows):
    digest = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    assert digest == EXPECTED["csv_sha256"], "raw CSV changed — it must stay immutable"


def test_totals_match_planner_audit(rows):
    assert len(rows) == EXPECTED["rows"]
    assert sum(int(r["uncached_input_tokens"]) for r in rows) == EXPECTED["uncached_input_tokens"]
    assert sum(int(r["cache_read_tokens"]) for r in rows) == EXPECTED["cache_read_tokens"]
    assert sum(int(r["total_prompt_tokens"]) for r in rows) == EXPECTED["total_prompt_tokens"]
    assert sum(int(r["output_tokens"]) for r in rows) == EXPECTED["output_tokens"]


def test_finish_reason_distribution(rows):
    dist = {}
    for r in rows:
        dist[r["finish_reason"]] = dist.get(r["finish_reason"], 0) + 1
    assert dist == EXPECTED["finish"]
    for group, count in EXPECTED["max_tokens_by_group"].items():
        actual = sum(1 for r in rows if r["group"] == group and r["finish_reason"] == "max-tokens")
        assert actual == count, f"group {group}: {actual} max-tokens != {count}"


def test_aggregate_rows_matches_expected(rows):
    agg = aggregate_rows(rows)
    assert agg["uncached_input_tokens"] == EXPECTED["uncached_input_tokens"]
    assert agg["cache_read_tokens"] == EXPECTED["cache_read_tokens"]
    assert agg["total_prompt_tokens"] == EXPECTED["total_prompt_tokens"]
    assert agg["output_tokens_all_attempts"] == EXPECTED["output_tokens"]
    assert abs(agg["weighted_cache_hit_rate"] - EXPECTED["weighted_cache_hit_rate"]) < 1e-12
    assert abs(agg["cost_cny_tiered"] - EXPECTED["cost_cny_tiered"]) < 1e-6
    assert agg["provider_attempts"] == 100
    assert agg["cache_write_reported"] is False


def test_group_sums_equal_overall(rows):
    overall = aggregate_rows(rows)
    for group in "ABCD":
        g = aggregate_rows([r for r in rows if r["group"] == group])
        assert g["logical_calls"] == 25
        for key in ("uncached_input_tokens", "cache_read_tokens", "total_prompt_tokens"):
            assert isinstance(g[key], int)
    for key in ("uncached_input_tokens", "cache_read_tokens", "total_prompt_tokens",
                "output_tokens_all_attempts"):
        assert sum(
            aggregate_rows([r for r in rows if r["group"] == g])[key] for g in "ABCD"
        ) == overall[key]


def test_reconcile_writes_consistent_artifacts(tmp_path):
    recon = reconcile(CSV_PATH)
    assert recon["all_checks_ok"], json.dumps(recon["checks"], indent=2)
    assert recon["source_csv_sha256"] == EXPECTED["csv_sha256"]
    assert recon["overall"]["cache_read_tokens"] == EXPECTED["cache_read_tokens"]


def test_summary_json_consistent_with_csv():
    summary_path = CSV_PATH.parent / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    overall = summary["overall"]
    assert overall["cache_read_tokens"] == EXPECTED["cache_read_tokens"]
    assert overall["total_prompt_tokens"] == EXPECTED["total_prompt_tokens"]
    assert abs(overall["weighted_cache_hit_rate"] - EXPECTED["weighted_cache_hit_rate"]) < 1e-12
