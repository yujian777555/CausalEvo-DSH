"""CausalPolicyAdapter tests (P4-R1.1-S2, hardened P4-R1.3-S6): real
controller call + real frozen Pareto genome consumption. The front hash is
pinned by the independent frozen manifest configs/phase3_artifact_manifest.json
— the adapter must verify against it and never self-certify. Offline only."""

import hashlib
import json
from pathlib import Path

import pytest

from causalevo.evolution.adapter import ADAPTER_VERSION, CausalPolicyAdapter, canonical_sha256
from causalevo.evolution.policy import ACTIONS, LinUCBPolicy

REPO = Path(__file__).resolve().parents[1]
FRONT = REPO / "results" / "phase3" / "evolution" / "pareto_front.json"
MANIFEST = REPO / "configs" / "phase3_artifact_manifest.json"
FRONT_REL = "results/phase3/evolution/pareto_front.json"


def _front_sha() -> str:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return manifest["artifacts"][FRONT_REL]["sha256"]


def _cea_v1(**kw) -> CausalPolicyAdapter:
    return CausalPolicyAdapter.cea_v1(FRONT, expected_sha256=_front_sha(), **kw)


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


def test_manifest_pins_current_front():
    """The frozen manifest must pin the artifact as it exists on disk
    (EOL-canonical: identical in dev worktrees and clean clones)."""
    assert canonical_sha256(FRONT) == _front_sha()


def test_cea_v1_loads_real_pareto_genome():
    adapter = _cea_v1()
    assert adapter.genome is not None
    assert adapter.provenance["genome_id"] == adapter.genome.genome_id
    assert len(adapter.provenance["pareto_front_sha256"]) == 64
    assert adapter.provenance["train_fitness"]


def test_cea_v1_provenance_hash_is_manifest_hash():
    adapter = _cea_v1()
    assert adapter.provenance["pareto_front_sha256"] == _front_sha()


def test_cea_v1_from_manifest_loads_and_pins():
    adapter = CausalPolicyAdapter.cea_v1_from_manifest(FRONT, MANIFEST)
    assert adapter.genome is not None
    assert adapter.provenance["pareto_front_sha256"] == _front_sha()


def test_cea_v1_genome_id_verification():
    adapter = _cea_v1()
    with pytest.raises(ValueError):
        _cea_v1(genome_id="000000000000")
    # the real id works
    _cea_v1(genome_id=adapter.genome.genome_id)


def test_cea_v1_no_expected_hash_rejected():
    """No self-certification: loading without an external expected hash fails."""
    with pytest.raises(ValueError):
        CausalPolicyAdapter.cea_v1(FRONT)
    with pytest.raises(ValueError):
        CausalPolicyAdapter.cea_v1(FRONT, expected_sha256=None)
    with pytest.raises(ValueError):
        CausalPolicyAdapter.cea_v1(FRONT, expected_sha256="")


def test_cea_v1_wrong_expected_hash_rejected():
    with pytest.raises(ValueError):
        CausalPolicyAdapter.cea_v1(FRONT, expected_sha256="0" * 64)


def test_cea_v1_tampered_front_rejected(tmp_path):
    """A one-byte change must fail verification against the manifest hash."""
    data = bytearray(FRONT.read_bytes())
    data[10] ^= 0x01
    tampered = tmp_path / "pareto_front.json"
    tampered.write_bytes(bytes(data))
    with pytest.raises(ValueError):
        CausalPolicyAdapter.cea_v1(tampered, expected_sha256=_front_sha())
    with pytest.raises(ValueError):
        CausalPolicyAdapter.cea_v1_from_manifest(tampered, MANIFEST)


def test_cea_v1_from_manifest_rejects_unpinned_artifact(tmp_path):
    outside = tmp_path / "pareto_front.json"
    outside.write_bytes(FRONT.read_bytes())
    with pytest.raises(ValueError):
        CausalPolicyAdapter.cea_v1_from_manifest(outside, MANIFEST)


def test_cea_v1_front_members_reverify_on_every_read(tmp_path):
    """_front_members re-checks the pinned hash on every read: tampering AFTER
    a successful load must still fail closed."""
    copied = tmp_path / "pareto_front.json"
    copied.write_bytes(FRONT.read_bytes())
    adapter = CausalPolicyAdapter.cea_v1(copied, expected_sha256=_front_sha())
    pick = adapter.select_genome(failure_kind="none", edited=True, invalid=False)
    assert pick["genome"] is not None
    data = bytearray(copied.read_bytes())
    data[10] ^= 0x01
    copied.write_bytes(bytes(data))
    with pytest.raises(ValueError):
        adapter.select_genome(failure_kind="none", edited=True, invalid=False)


def test_cea_v1_text_derives_from_genome_not_hardcoded():
    adapter = _cea_v1()
    out = adapter.intervention_for(failure_kind="none", edited=True, invalid=False)
    active = [g for g, v in adapter.genome.as_dict().items() if v > 0]
    if "tool_validation" in active:
        assert "read, write, edit" in out["text"]
    if "verification_level" in active:
        assert "re-read" in out["text"]
    assert out["genome_id"] == adapter.genome.genome_id


def test_cea_v1_infra_failure_escalates_no_retry():
    adapter = _cea_v1()
    out = adapter.intervention_for(failure_kind="unknown_cost", edited=False, invalid=False)
    assert out["text"] is None
    assert "escalate" in out["reason"]


def test_cea_v1_wrong_mode_guards():
    adapter = _cea_v1()
    with pytest.raises(RuntimeError):
        adapter.select({"failure_type": "unknown"}, list(ACTIONS))
    adapter0 = CausalPolicyAdapter.cea_v0(_trained_snapshot())
    with pytest.raises(RuntimeError):
        adapter0.intervention_for(failure_kind="none", edited=False, invalid=False)


def test_select_genome_branch_coverage_distinct_genomes():
    """Failure-conditioned branches must reach DIFFERENT front members where
    the frozen front provides them (no docker needed)."""
    adapter = _cea_v1()
    edited = adapter.select_genome(failure_kind="none", edited=True, invalid=False)
    invalid = adapter.select_genome(failure_kind="none", edited=True, invalid=True)
    no_edit = adapter.select_genome(failure_kind="none", edited=False, invalid=False)
    # each branch lands on the gene matching its observable evidence
    assert edited["genome"].as_dict()["tool_validation"] > 0
    assert "tool-validation" in edited["reason"]
    assert invalid["genome"].as_dict()["verification_level"] > 0
    assert "verification-heavy" in invalid["reason"]
    assert no_edit["genome"].as_dict()["read_before_write"] > 0
    assert "read-first" in no_edit["reason"]
    # the frozen front (pinned by the manifest) contains distinct members for
    # all three branches, so the picks MUST be distinct genomes
    ids = {edited["genome_id"], invalid["genome_id"], no_edit["genome_id"]}
    assert len(ids) == 3, f"branches collapsed onto the same genome: {ids}"
    active_sets = {
        tuple(sorted(g for g, v in p["genome"].as_dict().items() if v > 0))
        for p in (edited, invalid, no_edit)
    }
    assert len(active_sets) == 3


def test_select_genome_infra_returns_no_genome():
    adapter = _cea_v1()
    for kind in ("unknown_cost", "budget_stop", "transport", "protocol"):
        pick = adapter.select_genome(failure_kind=kind, edited=True, invalid=False)
        assert pick["genome"] is None
        assert f"infra failure {kind}" in pick["reason"]


def test_adapter_marks_own_version_not_old_pilot():
    adapter = _cea_v1()
    assert adapter.provenance["pareto_front_path"].endswith("pareto_front.json")
    assert ADAPTER_VERSION == "r1.3"
