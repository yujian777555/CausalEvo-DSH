"""Diagnosis model tests (P2.2-S3/S4/S5/S7): fit, abstain, serialize, evidence."""

import json
from pathlib import Path

import pytest

from causalevo.diagnosis.dataset import build_dataset, split_dataset
from causalevo.diagnosis.models import (
    EmbeddingDiagnoser,
    FeatureLRDiagnoser,
    RuleDiagnoser,
    to_candidate_intervention,
)
from causalevo.failure_dataset.builder import iter_traces

REPO = Path(__file__).resolve().parents[1]

_rows = None
_splits = None
_traces = None


def _data():
    global _rows, _splits, _traces
    if _rows is None:
        _rows = build_dataset(REPO / "results" / "phase1", REPO / "benchmarks" / "tasks")
        _splits = split_dataset(_rows)
        _traces = {t[0]["trace_id"]: t[0]
                   for t in iter_traces(REPO / "results" / "phase1")}
    return _rows, _splits, _traces


def _labeled_train():
    _, splits, _ = _data()
    return [r for r in splits["train"] if r["label"]]


def test_b0_rules_diagnoses_without_training():
    _, _, traces = _data()
    trace = next(iter(traces.values()))
    res = RuleDiagnoser().diagnose(trace)
    assert res.model == "B0-rules"
    assert res.trace_id == trace["trace_id"]


def test_b1_fit_predict():
    _, splits, _ = _data()
    m = FeatureLRDiagnoser()
    m.fit(_labeled_train())
    row = next(r for r in splits["val"] if r["label"])
    res = m.diagnose_row(row)
    assert res.failure_type in m.classes_ + ["unknown"]
    assert 0.0 <= res.confidence <= 1.0
    assert res.evidence


def test_b1_abstains_below_threshold():
    _, splits, _ = _data()
    m = FeatureLRDiagnoser(abstain_threshold=1.01)  # above any probability
    m.fit(_labeled_train())
    row = next(r for r in splits["val"] if r["label"])
    res = m.diagnose_row(row)
    assert res.abstained and res.failure_type == "unknown"


def test_b1_never_abstains_at_zero_threshold():
    _, splits, _ = _data()
    m = FeatureLRDiagnoser(abstain_threshold=0.0)
    m.fit(_labeled_train())
    row = next(r for r in splits["val"] if r["label"])
    assert not m.diagnose_row(row).abstained


def test_b1_serialization_roundtrip(tmp_path):
    _, splits, _ = _data()
    m = FeatureLRDiagnoser()
    m.fit(_labeled_train())
    path = tmp_path / "m.pkl"
    m.save(path)
    m2 = FeatureLRDiagnoser.load(path)
    row = next(r for r in splits["val"] if r["label"])
    assert m.diagnose_row(row).failure_type == m2.diagnose_row(row).failure_type
    assert m.diagnose_row(row).confidence == pytest.approx(m2.diagnose_row(row).confidence)


def test_b1_evidence_refs_are_real_trace_fields():
    _, splits, traces = _data()
    m = FeatureLRDiagnoser()
    m.fit(_labeled_train())
    row = next(r for r in splits["val"] if r["label"])
    res = m.diagnose_row(row, trace=traces[row["trace_id"]])
    assert res.evidence
    trace = traces[row["trace_id"]]
    for entry in res.evidence:
        assert entry.startswith("feature:")
        body, _, ref = entry.partition(" @")
        name, _, value = body[len("feature:"):].partition("=")
        assert name in row["features"]
        assert str(row["features"][name]) == value
        if ref:
            node = trace
            for part in ref.split("."):
                assert isinstance(node, dict) and part in node, f"ref {ref} not in trace"
                node = node[part]
            assert node is not None


def test_b2_embedding_fit_predict():
    _, splits, traces = _data()
    m = EmbeddingDiagnoser()
    m.fit(_labeled_train(), traces)
    trace = traces[next(r["trace_id"] for r in splits["val"] if r["label"])]
    res = m.diagnose(trace)
    assert res.failure_type in m.classes_ + ["unknown"]
    assert res.evidence


def test_b2_abstention():
    _, splits, traces = _data()
    m = EmbeddingDiagnoser(abstain_threshold=1.01)
    m.fit(_labeled_train(), traces)
    trace = traces[next(r["trace_id"] for r in splits["val"] if r["label"])]
    assert m.diagnose(trace).failure_type == "unknown"


def test_unfitted_models_raise():
    m = FeatureLRDiagnoser()
    with pytest.raises(RuntimeError):
        m.diagnose_row({"trace_id": "x", "features": {}})


def test_reproducibility_same_data_same_predictions():
    _, splits, _ = _data()
    a = FeatureLRDiagnoser()
    a.fit(_labeled_train())
    b = FeatureLRDiagnoser()
    b.fit(_labeled_train())
    row = next(r for r in splits["val"] if r["label"])
    assert a.diagnose_row(row).failure_type == b.diagnose_row(row).failure_type


def test_candidate_intervention_interface():
    _, _, traces = _data()
    res = RuleDiagnoser().diagnose(next(iter(traces.values())))
    ci = to_candidate_intervention(res)
    again = type(ci).from_json(ci.to_json())
    assert again.failure_type == ci.failure_type
    assert again.intervention_kind


def test_no_cot_in_model_evidence():
    _, splits, _ = _data()
    m = FeatureLRDiagnoser()
    m.fit(_labeled_train())
    row = next(r for r in splits["val"] if r["label"])
    res = m.diagnose_row(row)
    assert all("reasoning" not in e.lower() for e in res.evidence)
