"""CEA-v2 fake-provider/container integration (R1.8 Task D / R1.9 Task A).
Runs scripts/run_phase4_r19_pilot.py --offline-smoke (real Docker agent
containers + fake provider tapes) and asserts the update loop is REAL."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from causalevo.eval.executor import docker_available

REPO = Path(__file__).resolve().parents[1]
AGENT_IMAGE = "causalevo-dsh-agent:0.2.1"


def _img(name: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", name],
                          capture_output=True, timeout=15).returncode == 0


pytestmark = pytest.mark.skipif(
    not (docker_available() and _img(AGENT_IMAGE) and _img("python:3.11-slim")),
    reason="docker/images unavailable")


@pytest.fixture(scope="module")
def smoke():
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "run_phase4_r19_pilot.py"),
                           "--offline-smoke"],
                          capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    out = Path(proc.stdout.strip().split("smoke run_dir:")[-1].strip())
    records = [json.loads(l) for l in (out / "records.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    events = [json.loads(l) for l in (out / "events.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    state = json.loads((out / "controller_state.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    return out, records, events, state, manifest


def test_selected_genome_changes_retry_intervention_text(smoke):
    _, records, _, _, _ = smoke
    cea = [r for r in records if r["arm"] == "CEA-v2-online" and r["retried"]]
    assert cea, "CEA-v2 must execute retry rows"
    for r in cea:
        assert r["selected_genome_id"], "genome recorded per row"
        assert r["intervention_text"], "intervention text derived and injected"
        assert r["policy_version"] == "cea-v2.1-r1.10"
        assert r["selection_reason"]


def test_judge_and_settled_cost_feed_controller(smoke):
    _, records, events, _, _ = smoke
    behavioral = [e for e in events if e.get("kind") == "behavioral"]
    assert behavioral, "settled observations must reach the controller"
    for e in behavioral:
        assert isinstance(e["success"], bool)
        assert e["cost_cny"] >= 0 and e["calls"] >= 0, "measured cost/calls"
    cea = [r for r in records if r["arm"] == "CEA-v2-online" and r["retried"]]
    assert any(r["controller_update"] and r["controller_update"].get("updated")
               for r in cea)


def test_later_selection_changes_from_observations(smoke):
    _, records, events, state, _ = smoke
    cea = [r for r in records if r["arm"] == "CEA-v2-online" and r["retried"]]
    # after update_every=4 behavioral observations a real evolutionary step ran
    assert any(e.get("kind") == "evolve" for e in events), "evolutionary step fired"
    assert state["population_version"] >= 1
    offspring = [c for c in state["population"] if c["born_generation"] >= 1]
    assert offspring and all(c["parent_ids"] for c in offspring), "lineage"
    # the evolve step fires at the observation of the 4th behavioral row, so
    # that row's population_version_after must be >= 1 (later state changed)
    after = [r.get("population_version_after") for r in cea]
    assert any(v is not None and v >= 1 for v in after), \
        "evolve must advance the population version after an observation"


def test_infra_no_retry_no_behavioral_update(smoke):
    _, records, events, _, _ = smoke
    infra = [r for r in records if r.get("scenario") == "infra_unknown_cost"]
    assert infra, "infra scenario present"
    for r in infra:
        assert not r["retried"], "infra must not be retried"
        assert r["attempt_1_status"] in ("unknown_cost", "budget_stop",
                                         "transport", "protocol")
    infra_events = [e for e in events if e.get("kind") == "infra"]
    assert infra_events, "infra event recorded without behavioral learning"


def test_deterministic_replay_of_smoke_event_log(smoke):
    out, _, _, state, _ = smoke
    from causalevo.evolution.online_evolution import OnlineEvolutionController
    re = OnlineEvolutionController.replay(
        out / "events.jsonl",
        pareto_front_path=REPO / "results/phase3/evolution/pareto_front.json",
        manifest_path=REPO / "configs/phase3_artifact_manifest.json")
    a, b = state, re.state_dict()
    assert a["population_version"] == b["population_version"]
    assert [c["genome_id"] for c in a["population"]] == \
           [c["genome_id"] for c in b["population"]]


def test_no_cot_or_sealed_content_in_artifacts(smoke):
    out, _, _, _, manifest = smoke
    blob = json.dumps(manifest)
    assert manifest["evidence_class"] == "adapter_integration_smoke"
    assert "NOT real-model efficacy" in blob
    for path in out.iterdir():
        if path.suffix in (".jsonl", ".json"):
            text = path.read_text(encoding="utf-8")
            assert "chain_of_thought" not in text
            assert "sealed_test" not in text
