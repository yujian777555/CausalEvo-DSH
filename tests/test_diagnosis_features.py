"""Diagnosis feature extraction tests (P2.2-S1)."""

import json
from pathlib import Path

from causalevo.diagnosis.features import (
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    extract_features,
)
from causalevo.failure_dataset.builder import iter_traces

REPO = Path(__file__).resolve().parents[1]


def _one_trace(scenario: str) -> dict:
    for trace, _run, _pk, sc in iter_traces(REPO / "results" / "phase1" / "r2-offline"):
        if sc == scenario:
            return trace
    raise AssertionError(f"no trace for {scenario}")


def test_feature_shape_and_types():
    f = extract_features(_one_trace("bad_tool_call"))
    d = f.as_dict()
    for col in FEATURE_COLUMNS:
        assert col in d
    for col in CATEGORICAL_COLUMNS:
        assert col in d
    assert isinstance(d["tool_calls"], int)
    assert 0.0 <= d["action_diversity"] <= 1.0


def test_noop_trace_features():
    f = extract_features(_one_trace("noop"))
    assert f.tool_calls == 0
    assert f.edited_workspace is False


def test_tool_spam_features():
    f = extract_features(_one_trace("tool_over_budget"))
    assert f.budget_stop is True
    assert f.repeat_max_run >= 3


def test_provider_error_features():
    f = extract_features(_one_trace("provider_error"))
    assert f.failure_kind == "unknown_cost"
    assert f.n_unknown_spend >= 1


def test_correct_fix_features():
    f = extract_features(_one_trace("correct_fix"))
    assert f.edited_workspace is True
    assert f.visible_passed and f.sealed_passed


def test_no_forbidden_content_in_features():
    f = extract_features(_one_trace("wrong_fix"))
    text = json.dumps(f.as_dict())
    assert "reasoning" not in text.lower()
    assert "sealed" not in text or "sealed_passed" in text  # only the boolean flag
    assert "holdout" not in text
