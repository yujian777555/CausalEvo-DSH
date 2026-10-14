"""Intervention schema + generator tests (P2.3-S1/S2)."""

import pytest

from causalevo.analysis.schema import FailureCategory
from causalevo.diagnosis.models import DiagnosisResult
from causalevo.intervention.generator import (
    INTERVENTION_LIBRARY,
    NO_INTERVENTION,
    generate_intervention,
)
from causalevo.intervention.schema import CandidateIntervention, InterventionType


def _intervention(**kw):
    base = dict(
        intervention_id="t1", target_failure="tool_failure",
        intervention_type="tool_intervention", description="d",
        required_change="c", expected_effect="e", confidence="medium",
        tape_transform="identity",
    )
    base.update(kw)
    return CandidateIntervention(**base)


def test_valid_intervention():
    _intervention().validate()


def test_bad_target_failure_rejected():
    with pytest.raises(ValueError):
        _intervention(target_failure="nope").validate()


def test_bad_type_rejected():
    with pytest.raises(ValueError):
        _intervention(intervention_type="magic").validate()


def test_bad_confidence_rejected():
    with pytest.raises(ValueError):
        _intervention(confidence="sure").validate()


def test_missing_required_fields_rejected():
    with pytest.raises(ValueError):
        _intervention(intervention_id="").validate()


def test_serialization_roundtrip():
    iv = _intervention()
    assert CandidateIntervention.from_json(iv.to_json()) == iv


def test_stable_id_deterministic():
    assert _intervention().stable_id() == _intervention().stable_id()
    assert _intervention(description="different").stable_id() != _intervention().stable_id()


def _diag(ftype, conf=0.9, abstained=False):
    return DiagnosisResult(trace_id="t", failure_type=ftype, evidence=[],
                           confidence=conf, abstained=abstained, model="test")


@pytest.mark.parametrize("cat", [c.value for c in FailureCategory])
def test_generator_covers_every_failure_category(cat):
    iv = generate_intervention(_diag(cat))
    assert iv.target_failure == cat
    iv.validate()


def test_generator_tool_failure_maps_tool_intervention():
    iv = generate_intervention(_diag("tool_failure"))
    assert iv.intervention_type == InterventionType.TOOL.value
    assert iv.tape_transform == "replace_unknown_tool_with_read"


def test_generator_planning_maps_planning():
    iv = generate_intervention(_diag("planning_failure"))
    assert iv.intervention_type == InterventionType.PLANNING.value


def test_generator_verification_maps_verification():
    iv = generate_intervention(_diag("verification_failure"))
    assert iv.tape_transform == "append_readback_and_fix"


def test_generator_strategy_maps_strategy():
    iv = generate_intervention(_diag("strategy_failure"))
    assert iv.tape_transform == "break_repeat_with_read"


def test_generator_unknown_maps_noop():
    iv = generate_intervention(_diag("unknown", abstained=True))
    assert iv.intervention_type == InterventionType.NONE.value
    assert iv.tape_transform == "identity"


def test_library_all_valid_and_unique_ids():
    ids = set()
    for iv in INTERVENTION_LIBRARY:
        iv.validate()
        ids.add(iv.intervention_id)
    assert len(ids) == len(INTERVENTION_LIBRARY)


def test_no_intervention_constant():
    NO_INTERVENTION.validate()
    assert NO_INTERVENTION.tape_transform == "identity"
