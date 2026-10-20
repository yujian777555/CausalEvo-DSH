"""P4-R1.3-S6: offline adapter-integration smoke driver E2E.

Runs scripts/run_phase4_v2_offline.py (fake provider, agent containers,
real judges — zero API spend) and asserts the produced records prove the
adapter branches actually trigger on four distinct failure scenarios for both
arms. Evidence class is adapter_integration_smoke only.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from causalevo.eval.executor import docker_available

REPO = Path(__file__).resolve().parents[1]
AGENT_IMAGE = "causalevo-dsh-agent:0.2.1"
SCENARIOS = ("edited_failing", "invalid_syntax", "no_edit", "infra_unknown_cost")
ARMS = ("B4-v2", "B5-v2")


def _img(name: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", name],
                          capture_output=True, timeout=15).returncode == 0


pytestmark = pytest.mark.skipif(
    not (docker_available() and _img(AGENT_IMAGE) and _img("python:3.11-slim")),
    reason="docker/images unavailable")


def _manifest_front_sha() -> str:
    manifest = json.loads(
        (REPO / "configs" / "phase3_artifact_manifest.json").read_text(
            encoding="utf-8"))
    return manifest["artifacts"]["results/phase3/evolution/pareto_front.json"]["sha256"]


@pytest.fixture(scope="module")
def run_dir() -> Path:
    before = set((REPO / "results" / "phase4" / "v2-offline").glob("run-*"))
    proc = subprocess.run(
        [sys.executable, "scripts/run_phase4_v2_offline.py"],
        cwd=REPO, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, (
        f"driver failed:\nSTDOUT\n{proc.stdout[-3000:]}\nSTDERR\n{proc.stderr[-3000:]}")
    after = set((REPO / "results" / "phase4" / "v2-offline").glob("run-*"))
    new = sorted(after - before, key=lambda p: p.stat().st_mtime)
    assert new, f"driver produced no new run dir:\n{proc.stdout[-2000:]}"
    return new[-1]


@pytest.fixture(scope="module")
def records(run_dir) -> list[dict]:
    rows = [json.loads(l) for l in
            (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert rows, "records.jsonl is empty"
    return rows


def _row(records, arm, scenario):
    match = [r for r in records
             if r["arm"] == arm and r["scenario"] == scenario]
    assert len(match) == 1, f"missing row {arm}/{scenario}"
    return match[0]


def test_all_scenarios_both_arms(records):
    assert {(r["arm"], r["scenario"]) for r in records} == \
        {(a, s) for a in ARMS for s in SCENARIOS}
    for r in records:
        assert r["experiment_version"] == "p4-r1.3-v2"
        assert r["policy_updated"] is False


def test_observable_evidence_computed_not_hardcoded(records):
    for arm in ARMS:
        assert _row(records, arm, "no_edit")["failure_state"]["edited"] is False
        assert _row(records, arm, "edited_failing")["failure_state"]["edited"] is True
        assert _row(records, arm, "invalid_syntax")["failure_state"]["edited"] is True
        assert _row(records, arm, "invalid_syntax")["failure_state"]["invalid"] is True
        assert _row(records, arm, "edited_failing")["failure_state"]["invalid"] is False


def test_b5_branches_pick_distinct_genomes(records):
    edited = _row(records, "B5-v2", "edited_failing")
    invalid = _row(records, "B5-v2", "invalid_syntax")
    no_edit = _row(records, "B5-v2", "no_edit")
    # branch labels are always recorded honestly
    assert "tool-validation" in edited["reason"]
    assert "verification-heavy" in invalid["reason"]
    assert "read-first" in no_edit["reason"]
    picks = [edited, invalid, no_edit]
    if all(p["selected_genome"] is not None for p in picks):
        ids = {p["selected_genome"] for p in picks}
        assert len(ids) == 3, (
            f"the pinned front provides distinct members per branch; picks "
            f"collapsed: {ids}")
    else:
        # front lacks a matching member somewhere: the reason must say so
        for p in picks:
            if p["selected_genome"] is None:
                assert "fallback" in p["reason"] or "no retry" in p["reason"]
    for p in picks:
        assert p["pareto_front_sha256"] == _manifest_front_sha()


def test_infra_unknown_cost_no_retry_both_arms(records):
    for arm in ARMS:
        row = _row(records, arm, "infra_unknown_cost")
        assert row["failure_state"]["failure_kind"] == "unknown_cost"
        assert row["attempt2"] is None, f"{arm} retried an infra failure"
        assert row["intervention_text"] is None
    b5 = _row(records, "B5-v2", "infra_unknown_cost")
    assert b5["selected_genome"] is None
    assert "infra failure unknown_cost" in b5["reason"]
    b4 = _row(records, "B4-v2", "infra_unknown_cost")
    assert b4["selected_action"] == "lib:execution_failure"
    assert "no retry" in b4["reason"]


def test_b4_rows_carry_frozen_policy_provenance(records):
    for scenario in SCENARIOS:
        row = _row(records, "B4-v2", scenario)
        assert len(row["policy_snapshot_sha256"]) == 64
        assert row["policy_version"].startswith("B2-cea-v0-linucb@")
        assert row["selected_action"].startswith("lib:")
        assert row["policy_updated"] is False
        assert row["reason"]


def test_behavioral_rows_retried_and_judged(records):
    for arm in ARMS:
        for scenario in ("edited_failing", "invalid_syntax", "no_edit"):
            row = _row(records, arm, scenario)
            assert row["attempt2"] == "ran"
            assert row["final_success"] is True, (
                f"{arm}/{scenario}: fix tape + intervention must pass the judge")


def test_run_manifest_evidence_class(run_dir):
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence_class"] == "adapter_integration_smoke"
    assert "NOT algorithm generalization" in manifest["note"]
    assert manifest["experiment_version"] == "p4-r1.3-v2"
    assert manifest["pareto_front_sha256"] == _manifest_front_sha()
