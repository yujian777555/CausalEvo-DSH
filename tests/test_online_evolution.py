"""OnlineEvolutionController (CEA-v2) unit tests (P4-R1.8 Task B invariants).
Deterministic, offline, zero API. Uses the REAL manifest-pinned Pareto front."""

import json
from pathlib import Path

import pytest

from causalevo.evolution.online_evolution import (OnlineEvolutionController,
                                                  OnlineEvolutionError,
                                                  effective_phenotype)

REPO = Path(__file__).resolve().parents[1]
FRONT = REPO / "results" / "phase3" / "evolution" / "pareto_front.json"
MANIFEST = REPO / "configs" / "phase3_artifact_manifest.json"

CTX = {"failure_type": "tool", "edited": True, "invalid": False,
       "failure_kind": "none"}


def _ctl():
    return OnlineEvolutionController(pareto_front_path=FRONT,
                                     manifest_path=MANIFEST)


def _behavioral(success=True, cost=0.002, calls=2):
    return {"success": success, "cost_cny": cost, "calls": calls,
            "failure_kind": "none"}


def test_init_dedupes_effective_phenotypes():
    ctl = _ctl()
    phenotypes = [c.phenotype for c in ctl.population]
    assert len(phenotypes) == len(set(phenotypes)), "unique effective phenotypes"
    # the frozen front has 6 members but only 4 unique genomes; the deduped
    # active population must not exceed the unique-phenotype count
    assert len(ctl.population) <= 4
    assert all(c.born_generation == 0 for c in ctl.population)


def test_reserved_genes_do_not_inflate_diversity():
    from causalevo.evolution.genome import InterventionGenome
    g_plain = InterventionGenome((1, 0, 0, 0, 0, 0))
    g_reserved = InterventionGenome((1, 0, 0, 0, 1, 2))  # reflection+retry
    assert effective_phenotype(g_plain) == effective_phenotype(g_reserved)


def test_manifest_mismatch_fails_closed(tmp_path):
    bad = tmp_path / "front.json"
    bad.write_text(json.dumps(json.loads(FRONT.read_text())), encoding="utf-8")
    with pytest.raises(OnlineEvolutionError):
        OnlineEvolutionController(pareto_front_path=bad, manifest_path=MANIFEST)


def test_select_returns_versions_and_genome():
    ctl = _ctl()
    sel = ctl.select(CTX, "ep-1")
    assert sel["genome_id"] and sel["policy_version"] == "cea-v2-r1.8"
    assert sel["population_version"] == 0
    assert "unmeasured" in sel["reason"]


def test_observe_updates_and_changes_later_selection():
    ctl = _ctl()
    first = ctl.select(CTX, "ep-1")
    # make the initially selected candidate FAIL repeatedly and another win
    ctl.observe("ep-1", CTX, first["genome_id"], _behavioral(success=False))
    ctl.observe("ep-2", CTX, first["genome_id"], _behavioral(success=False))
    # pick whatever the controller now selects and reward it
    second = ctl.select(CTX, "ep-3")
    ctl.observe("ep-3", CTX, second["genome_id"], _behavioral(success=True))
    ctl.observe("ep-4", CTX, second["genome_id"], _behavioral(success=True))
    third = ctl.select(CTX, "ep-5")
    assert third["genome_id"] == second["genome_id"], \
        "measured success must change later selection (update affects choice)"


def test_duplicate_episode_rejected():
    ctl = _ctl()
    sel = ctl.select(CTX, "ep-1")
    ctl.observe("ep-1", CTX, sel["genome_id"], _behavioral())
    with pytest.raises(OnlineEvolutionError):
        ctl.observe("ep-1", CTX, sel["genome_id"], _behavioral())


def test_unknown_cost_stops_learning():
    ctl = _ctl()
    sel = ctl.select(CTX, "ep-1")
    with pytest.raises(OnlineEvolutionError):
        ctl.observe("ep-1", CTX, sel["genome_id"],
                    {"success": False, "cost_cny": None, "calls": 1,
                     "failure_kind": "none"})
    with pytest.raises(OnlineEvolutionError):
        ctl.select(CTX, "ep-2")


def test_infra_outcome_no_behavioral_update_no_retry():
    ctl = _ctl()
    sel = ctl.select(CTX, "ep-1")
    out = ctl.observe("ep-1", CTX, sel["genome_id"],
                      {"success": False, "cost_cny": None, "calls": 0,
                       "failure_kind": "unknown_cost"})
    assert out["updated"] is False
    cand = next(c for c in ctl.population if c.genome_id == sel["genome_id"])
    assert cand.n == 0, "infra outcome must not touch behavior statistics"


def test_evolution_step_produces_lineaged_offspring():
    ctl = _ctl()
    initial_ids = {c.genome_id for c in ctl.population}
    for i in range(4):  # update_every = 4
        sel = ctl.select(CTX, f"ep-{i}")
        ctl.observe(f"ep-{i}", CTX, sel["genome_id"],
                    _behavioral(success=i % 2 == 0))
    assert ctl.evolution_updates == 1
    assert ctl.population_version == 1
    new = [c for c in ctl.population if c.genome_id not in initial_ids]
    assert new, "offspring entered the population"
    assert all(c.parent_ids for c in new), "lineage recorded"
    assert all(c.born_generation == 1 for c in new)
    phenotypes = [c.phenotype for c in ctl.population]
    assert len(phenotypes) == len(set(phenotypes)), "phenotype dedupe held"


def test_offspring_eligible_and_explored_not_proven():
    ctl = _ctl()
    for i in range(4):
        sel = ctl.select(CTX, f"ep-{i}")
        ctl.observe(f"ep-{i}", CTX, sel["genome_id"], _behavioral())
    offspring = [c for c in ctl.population if c.born_generation == 1]
    assert offspring and all(not c.measured for c in offspring)
    # an unmeasured offspring may be selected via exploration, but its
    # statistics stay untouched until actually observed
    sel = ctl.select(CTX, "ep-next")
    cand = next(c for c in ctl.population if c.genome_id == sel["genome_id"])
    if not cand.measured:
        assert "explore" in sel["reason"]


def test_bounded_population():
    ctl = _ctl()
    ctl.config["max_population"] = 8
    for i in range(16):  # force multiple evolve steps
        ctl.select(CTX, f"ep-{i}")
        sel = ctl.select(CTX, f"ep-{i}")
        ctl.observe(f"ep-{i}", CTX, sel["genome_id"],
                    _behavioral(success=i % 2 == 0))
    assert len(ctl.population) <= 8


def test_deterministic_replay(tmp_path):
    ctl = _ctl()
    for i in range(8):
        sel = ctl.select(CTX, f"ep-{i}")
        ctl.observe(f"ep-{i}", CTX, sel["genome_id"],
                    _behavioral(success=i % 3 == 0))
    log = tmp_path / "events.jsonl"
    with log.open("w", encoding="utf-8") as fh:
        for e in ctl.events:
            fh.write(json.dumps(e, sort_keys=True) + "\n")
    re = OnlineEvolutionController.replay(log, pareto_front_path=FRONT,
                                          manifest_path=MANIFEST)
    a, b = ctl.state_dict(), re.state_dict()
    assert a["population_version"] == b["population_version"]
    assert [c["genome_id"] for c in a["population"]] == \
           [c["genome_id"] for c in b["population"]]
    assert [ (c["n"], c["successes"]) for c in a["population"]] == \
           [ (c["n"], c["successes"]) for c in b["population"]]


def test_history_up_to_excludes_future():
    ctl = _ctl()
    for i in range(6):
        sel = ctl.select(CTX, f"ep-{i}")
        ctl.observe(f"ep-{i}", CTX, sel["genome_id"], _behavioral())
    past = ctl.history_up_to(3)
    assert len(past["events"]) == 3
    assert all(e["episode_id"] in {"ep-0", "ep-1", "ep-2"}
               for e in past["events"] if e.get("episode_id"))


def test_no_livelock_when_phenotype_space_exhausted():
    """R1.9 CEA-V2-D1 regression: many evolve steps must TERMINATE even when
    no novel effective phenotype remains (previously an infinite loop)."""
    import time
    ctl = _ctl()
    ctl.config["max_population"] = 100  # no eviction pressure -> space exhausts
    t0 = time.monotonic()
    for i in range(40):  # 10 evolve steps; old code livelocked at ~4
        sel = ctl.select(CTX, f"ep-{i}")
        ctl.observe(f"ep-{i}", CTX, sel["genome_id"],
                    _behavioral(success=i % 2 == 0))
    elapsed = time.monotonic() - t0
    assert elapsed < 30, f"controller livelocked ({elapsed:.1f}s)"
    assert ctl.evolution_updates >= 1
    assert any(e.get("phenotype_space_exhausted") for e in ctl.events
               if e.get("kind") == "evolve"), \
        "exhaustion must be reported honestly, not hidden"


def test_bounded_population_terminates_with_eviction():
    """With a small archive, eviction keeps making room: no livelock either."""
    import time
    ctl = _ctl()
    ctl.config["max_population"] = 4
    t0 = time.monotonic()
    for i in range(40):
        sel = ctl.select(CTX, f"ep-{i}")
        ctl.observe(f"ep-{i}", CTX, sel["genome_id"],
                    _behavioral(success=i % 2 == 0))
    assert time.monotonic() - t0 < 30
    assert len(ctl.population) <= 4


def test_state_serializable_and_config_hashed():
    ctl = _ctl()
    d = ctl.state_dict()
    json.dumps(d)  # must serialize
    assert d["config_sha256"] and d["population_version"] == 0
    ctl2 = _ctl()
    assert ctl2.state_dict()["config_sha256"] == d["config_sha256"], \
        "same config -> same hash (deterministic)"
