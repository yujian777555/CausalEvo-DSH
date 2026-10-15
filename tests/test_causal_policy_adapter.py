"""CausalPolicyAdapter tests (P4-R1.1-S2): real controller call + real frozen
Pareto genome consumption. Offline only."""

from pathlib import Path

import pytest

from causalevo.evolution.adapter import ADAPTER_VERSION, CausalPolicyAdapter
from causalevo.evolution.policy import ACTIONS, LinUCBPolicy

REPO = Path(__file__).resolve().parents[1]
FRONT = REPO / "results" / "phase3" / "evolution" / "pareto_front.json"


def _trained_snapshot():
    p = LinUCBPolicy(alpha=0.5)
    s = {"failure_type": "tool_failure"}
    for _ in range(5):
        p.update(s, "lib:tool_failure", 1.0)
    return p.to_dict()


def test_cea_v0_calls_real_controller():
    adapter = CausalPolicyAdapter.cea_v0(_trained_snapshot())
    out = adapter.select({"failure_type": "tool_failure"}, list(ACTIONS))
    assert out["selected_action"] == "lib:tool_failure"
    assert out["policy_version"].startswith("B2-cea-v0-linucb@")
    assert out["adapter_version"] == ADAPTER_VERSION
    assert out["deployment"] == "frozen-no-update"


def test_cea_v0_never_updates_during_selection():
    adapter = CausalPolicyAdapter.cea_v0(_trained_snapshot())
    before = adapter.controller.policy.updates
    adapter.select({"failure_type": "unknown"}, list(ACTIONS))
    assert adapter.controller.policy.updates == before  # frozen deployment


def test_cea_v0_policy_version_changes_only_with_training():
    snap = _trained_snapshot()
    a1 = CausalPolicyAdapter.cea_v0(snap)
    a2 = CausalPolicyAdapter.cea_v0(snap)
    assert a1.select({"failure_type": "unknown"}, ACTIONS) ["policy_version"] == \
        a2.select({"failure_type": "unknown"}, ACTIONS)["policy_version"]


def test_cea_v1_loads_real_pareto_genome():
    adapter = CausalPolicyAdapter.cea_v1(FRONT)
    assert adapter.genome is not None
    assert adapter.provenance["genome_id"] == adapter.genome.genome_id
    assert len(adapter.provenance["pareto_front_sha256"]) == 64
    assert adapter.provenance["train_fitness"]


def test_cea_v1_genome_id_verification():
    adapter = CausalPolicyAdapter.cea_v1(FRONT)
    with pytest.raises(ValueError):
        CausalPolicyAdapter.cea_v1(FRONT, genome_id="000000000000")
    # the real id works
    CausalPolicyAdapter.cea_v1(FRONT, genome_id=adapter.genome.genome_id)


def test_cea_v1_text_derives_from_genome_not_hardcoded():
    adapter = CausalPolicyAdapter.cea_v1(FRONT)
    out = adapter.intervention_for(failure_kind="none", edited=True, invalid=False)
    active = [g for g, v in adapter.genome.as_dict().items() if v > 0]
    if "tool_validation" in active:
        assert "read, write, edit" in out["text"]
    if "verification_level" in active:
        assert "re-read" in out["text"]
    assert out["genome_id"] == adapter.genome.genome_id


def test_cea_v1_infra_failure_escalates_no_retry():
    adapter = CausalPolicyAdapter.cea_v1(FRONT)
    out = adapter.intervention_for(failure_kind="unknown_cost", edited=False, invalid=False)
    assert out["text"] is None
    assert "escalate" in out["reason"]


def test_cea_v1_wrong_mode_guards():
    adapter = CausalPolicyAdapter.cea_v1(FRONT)
    with pytest.raises(RuntimeError):
        adapter.select({"failure_type": "unknown"}, list(ACTIONS))
    adapter0 = CausalPolicyAdapter.cea_v0(_trained_snapshot())
    with pytest.raises(RuntimeError):
        adapter0.intervention_for(failure_kind="none", edited=False, invalid=False)


def test_adapter_marks_own_version_not_old_pilot():
    adapter = CausalPolicyAdapter.cea_v1(FRONT)
    assert adapter.provenance["pareto_front_path"].endswith("pareto_front.json")
    assert ADAPTER_VERSION == "r1.1"
