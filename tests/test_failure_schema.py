"""Failure schema validation + taxonomy integrity (P2.1-S1)."""

import pytest

from causalevo.analysis.schema import (
    Confidence,
    CounterfactualCase,
    EvidenceItem,
    FailureCategory,
    FailureReport,
    TAXONOMY,
)


def _report(**kw):
    base = dict(
        task_id="t", run_id="r", outcome="failed",
        failure_type=FailureCategory.TOOL.value,
        evidence=[EvidenceItem("tool_error", "events_slim tool/call", "unknown tool: x")],
        confidence=Confidence.MEDIUM.value,
        causal_scope="trajectory+judge only",
        repair_direction="schema 校验前置",
    )
    base.update(kw)
    return FailureReport(**base)


def test_taxonomy_has_six_categories_plus_unknown():
    assert len(TAXONOMY) == 7
    assert FailureCategory.UNKNOWN in TAXONOMY
    for cat, meta in TAXONOMY.items():
        assert meta["observable_evidence"] and meta["hidden_cause_hypothesis"]


def test_valid_report_passes():
    _report().validate()


def test_bad_failure_type_rejected():
    with pytest.raises(ValueError):
        _report(failure_type="made_up").validate()


def test_bad_confidence_rejected():
    with pytest.raises(ValueError):
        _report(confidence="very-sure").validate()


def test_success_must_not_carry_failure_type():
    with pytest.raises(ValueError):
        _report(outcome="success").validate()


def test_abstention_requires_evidence_of_insufficiency():
    with pytest.raises(ValueError):
        _report(failure_type="unknown", evidence=[]).validate()


def test_evidence_item_shape():
    e = EvidenceItem("timeout", "states.timeout", "true")
    assert e.as_dict() == {"kind": "timeout", "ref": "states.timeout", "detail": "true"}


def test_report_roundtrip():
    rep = _report()
    again = FailureReport.from_dict(rep.as_dict())
    assert again.failure_type == rep.failure_type


def test_counterfactual_case_roundtrip():
    case = CounterfactualCase(
        original_trace={"trace_id": "x"},
        failure_label="tool_failure",
        candidate_intervention={"kind": "add_step", "description": "validate tool args"},
        replay_config={"seed": 42, "budget_policy": "B0"},
    )
    case2 = CounterfactualCase.from_json(case.to_json())
    assert case2.failure_label == "tool_failure"


def test_counterfactual_case_validation():
    with pytest.raises(ValueError):
        CounterfactualCase({}, "tool_failure",
                           {"kind": "x"},  # missing description
                           {"seed": 1, "budget_policy": "B0"}).validate()
    with pytest.raises(ValueError):
        CounterfactualCase({}, "tool_failure",
                           {"kind": "x", "description": "y"},
                           {"seed": 1}).validate()  # missing budget_policy
    with pytest.raises(ValueError):
        CounterfactualCase({}, "not_a_category",
                           {"kind": "x", "description": "y"},
                           {"seed": 1, "budget_policy": "B0"}).validate()
