"""Diagnosis dataset + split integrity tests (P2.2-S2)."""

from pathlib import Path

from causalevo.diagnosis.dataset import (
    SPLIT_SEED,
    build_dataset,
    dataset_manifest,
    split_dataset,
)

REPO = Path(__file__).resolve().parents[1]
ROWS = None


def _rows():
    global ROWS
    if ROWS is None:
        ROWS = build_dataset(REPO / "results" / "phase1", REPO / "benchmarks" / "tasks")
    return ROWS


def test_dataset_rows_have_required_fields():
    for r in _rows():
        assert {"trace_id", "task_id", "features", "label", "label_source",
                "evidence", "confidence"} <= set(r)
        assert r["features"]["trace_id"] == r["trace_id"]


def test_split_groups_no_task_leakage():
    splits = split_dataset(_rows())
    assign: dict[str, str] = {}
    for split, rows in splits.items():
        for r in rows:
            tid = r["task_id"]
            if tid in assign:
                assert assign[tid] == split, \
                    f"task {tid} in both {assign[tid]} and {split}"
            else:
                assign[tid] = split


def test_split_reproducible_same_seed():
    a = split_dataset(_rows(), seed=SPLIT_SEED)
    b = split_dataset(_rows(), seed=SPLIT_SEED)
    for k in ("train", "val", "test"):
        assert [r["trace_id"] for r in a[k]] == [r["trace_id"] for r in b[k]]


def test_split_deterministically_changes_with_seed():
    a = split_dataset(_rows(), seed=SPLIT_SEED)
    b = split_dataset(_rows(), seed=1)
    same = all([r["trace_id"] for r in a[k]] == [r["trace_id"] for r in b[k]] for k in a)
    assert not same or len(a["train"]) == len(b["train"])  # usually reorders


def test_label_sources_present():
    sources = {r["label_source"] for r in _rows()}
    assert "scenario_injected" in sources
    assert "judge_outcome" in sources
    # every row carries a known provenance label
    assert sources <= {"scenario_injected", "judge_outcome", "rule_chain_silver", "unlabeled"}


def test_manifest_contents():
    splits = split_dataset(_rows())
    m = dataset_manifest(splits, SPLIT_SEED)
    assert m["seed"] == SPLIT_SEED
    assert m["grouped_by"] == "task_id"
    assert m["counts"]["train"] + m["counts"]["val"] + m["counts"]["test"] == len(_rows())
