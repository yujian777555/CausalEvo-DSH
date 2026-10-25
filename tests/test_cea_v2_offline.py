"""Tests for scripts/run_cea_v2_offline.py (CE-DSH-P4-R1.8 Task C).

Runs the deterministic synthetic-validation driver via subprocess (offline,
no docker, <60s per run) and asserts over the produced artifacts:
all regimes/arms present; prequential order (an update event for episode i
appears only after episode i's observation); cumulative regret finite and
recorded per arm; ablations present; reruns byte-identical; adaptation lag
measured on the shift regime; and no artifact anywhere declares a real-model
improvement (evidence_class must stay synthetic_mechanism_test).

Unit tests cover: an observation changes later selection after a shift;
duplicate episode_id is rejected; the no-update ablation keeps
population_version == 0.
"""

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

_spec = importlib.util.spec_from_file_location(
    "run_cea_v2_offline", REPO / "scripts" / "run_cea_v2_offline.py")
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)

from causalevo.evolution.online_evolution import (  # noqa: E402
    OnlineEvolutionController, OnlineEvolutionError)

REGIMES = ("stationary_contextual", "abrupt_shift",
           "success_cost_tradeoff", "iid_noise")
ARMS = ("random", "rule", "static_pareto", "linucb_frozen", "cea_v2")
ABLATIONS = ("cea_v2_no_update", "cea_v2_no_variation",
             "cea_v2_no_context", "cea_v2_single_objective")
CONTROLLER_ARMS = ("cea_v2",) + ABLATIONS
LIVELOCK = "controller_livelock_phenotype_exhaustion"


def _run_driver(out_root: Path) -> Path:
    proc = subprocess.run(
        [sys.executable, "scripts/run_cea_v2_offline.py",
         "--out-root", str(out_root), "--quiet"],
        cwd=REPO, capture_output=True, text=True, timeout=55)
    assert proc.returncode == 0, (
        f"driver failed:\nSTDOUT\n{proc.stdout[-2000:]}\nSTDERR\n{proc.stderr[-2000:]}")
    runs = sorted(out_root.glob("run-*"))
    assert len(runs) == 1, f"expected exactly one run dir, got {runs}"
    return runs[0]


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    d1 = _run_driver(tmp_path_factory.mktemp("cea_v2_a"))
    d2 = _run_driver(tmp_path_factory.mktemp("cea_v2_b"))
    return d1, d2


@pytest.fixture(scope="module")
def run_dir(two_runs):
    return two_runs[0]


def _load(run_dir: Path, name: str):
    if name.endswith(".jsonl"):
        return [json.loads(l) for l in
                (run_dir / name).read_text(encoding="utf-8").splitlines()
                if l.strip()]
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def episodes(run_dir):
    return _load(run_dir, "episodes.jsonl")


@pytest.fixture(scope="module")
def summary(run_dir):
    return _load(run_dir, "summary.json")


# --------------------------------------------------------------- subprocess
def test_outputs_exist(run_dir):
    for name in ("manifest.json", "episodes.jsonl", "summary.json",
                 "ablations.json"):
        assert (run_dir / name).is_file(), f"missing {name}"


def test_all_regimes_and_arms_present(episodes, summary, run_dir):
    seen = {(r["regime"], r["arm"]) for r in episodes}
    expected = {(g, a) for g in REGIMES for a in ARMS + ABLATIONS}
    assert seen == expected, f"missing rows: {expected - seen}"
    assert set(summary["results"]) == set(REGIMES)
    for g in REGIMES:
        assert set(summary["results"][g]) == set(ARMS)
    ablations = _load(run_dir, "ablations.json")
    assert set(ablations["results"]) == set(REGIMES)
    for g in REGIMES:
        assert set(ablations["results"][g]) == set(ABLATIONS)


def test_prequential_order(episodes):
    """The population version used at SELECT time for episode i must equal the
    version produced by updates of episodes < i only: an update event belongs
    to the episode whose observation preceded it, never to a future one."""
    by_key: dict[tuple, list] = {}
    for r in episodes:
        by_key.setdefault((r["regime"], r["arm"]), []).append(r)
    for (regime, arm), rows in by_key.items():
        rows.sort(key=lambda r: r["episode_index"])
        assert [r["episode_index"] for r in rows] == list(range(len(rows))), \
            f"{regime}/{arm}: episode stream has gaps or duplicates"
        if arm not in CONTROLLER_ARMS:
            for r in rows:
                assert r["update_event"] is None
                assert r["population_version_at_select"] is None
            continue
        if arm == "cea_v2_no_update":
            for r in rows:
                assert r["population_version_at_select"] == 0
                assert r["update_event"]["updated"] is False
            continue
        version = 0
        for r in rows:
            assert r["population_version_at_select"] == version, (
                f"{regime}/{arm} ep{r['episode_index']}: selection used "
                f"population_version {r['population_version_at_select']} but "
                f"only version {version} could have been produced by earlier "
                "episodes (future-row access)")
            ue = r["update_event"]
            if ue and ue.get("evolved"):
                assert ue["population_version"] == version + 1
                version = ue["population_version"]


def test_cumulative_regret_finite_and_consistent(episodes, summary):
    by_key: dict[tuple, list] = {}
    for r in episodes:
        by_key.setdefault((r["regime"], r["arm"]), []).append(r)
    for (regime, arm), rows in by_key.items():
        rows.sort(key=lambda r: r["episode_index"])
        total = 0.0
        prev = -1e-18
        for r in rows:
            regret = r["reward"]["regret"]
            assert math.isfinite(regret) and regret >= -1e-12
            total += regret
            assert r["cumulative_regret"] == pytest.approx(total)
            assert r["cumulative_regret"] >= prev - 1e-9, "regret must be monotone"
            prev = r["cumulative_regret"]
        assert math.isfinite(total)
        doc = summary if arm in ARMS else None
        if doc is not None:
            s = doc["results"][regime][arm]
            assert s["cumulative_regret"] == pytest.approx(total)
            assert math.isfinite(s["cumulative_regret"])


def test_ablations_present(run_dir):
    ablations = _load(run_dir, "ablations.json")
    assert set(ablations["ablations"]) == set(ABLATIONS)
    assert ablations["ablations"]["cea_v2_no_update"]["no_observe"] is True
    assert ablations["ablations"]["cea_v2_no_variation"]["config_delta"] == \
        {"mutation_p": 0.0, "n_offspring": 0}
    assert ablations["ablations"]["cea_v2_no_context"]["scrub_context"] is True
    assert ablations["ablations"]["cea_v2_single_objective"]["config_delta"] == \
        {"lambda_cost": 0.0, "lambda_calls": 0.0}
    for g in REGIMES:
        for a in ABLATIONS:
            s = ablations["results"][g][a]
            assert math.isfinite(s["cumulative_regret"])
            assert s["episodes_completed"] >= 1


def test_deterministic_rerun(two_runs):
    d1, d2 = two_runs
    for name in ("episodes.jsonl", "summary.json", "ablations.json"):
        a = (d1 / name).read_bytes()
        b = (d2 / name).read_bytes()
        assert a == b, f"{name} differs between identical-seed reruns"


def test_adaptation_lag_measured_on_shift_regime(summary, run_dir):
    ablations = _load(run_dir, "ablations.json")
    docs = [summary["results"]["abrupt_shift"],
            ablations["results"]["abrupt_shift"]]
    for doc in docs:
        for arm, s in doc.items():
            lag = s["adaptation_lag"]
            assert lag["shift_episode"] == 8
            assert lag["target_phenotype"] == \
                ["replace_unknown_tool_with_read", "append_readback_and_fix"]
            assert lag["post_shift_oracle_phenotype"] == ["append_readback_and_fix"]
            assert lag["post_shift_tool_episodes"] >= 0
            assert lag["first_hit_lag"] is None or lag["first_hit_lag"] >= 0
            assert lag["stable_lag_80pct_window10"] is None or \
                lag["stable_lag_80pct_window10"] >= 0
            assert lag["reason"]
    # the full-horizon adaptive ablation must yield a concrete measurement
    nv = ablations["results"]["abrupt_shift"]["cea_v2_no_variation"]["adaptation_lag"]
    assert nv["first_hit_lag"] is not None
    # frozen arms must honestly report non-adaptation
    for arm in ("rule", "static_pareto", "linucb_frozen"):
        lag = summary["results"]["abrupt_shift"][arm]["adaptation_lag"]
        assert lag["stable_lag_80pct_window10"] is None
        assert "never" in lag["reason"]
    # the livelocked main arm records why its window is unmeasurable
    lag = summary["results"]["abrupt_shift"]["cea_v2"]["adaptation_lag"]
    assert lag["stable_lag_80pct_window10"] is None
    assert "livelock" in lag["reason"] or "never" in lag["reason"]


def test_no_arm_declared_real_model_improvement(run_dir):
    def _strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for k, v in obj.items():
                yield from _strings(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from _strings(v)

    for name in ("manifest.json", "summary.json", "ablations.json"):
        doc = _load(run_dir, name)
        assert doc["evidence_class"] == "synthetic_mechanism_test", name
        assert doc["real_agent_improvement_evidence"] is False, name
        assert "NOT evidence of real-agent improvement" in doc["note"], name
        for s in _strings(doc):
            low = s.lower()
            if "real-agent improvement" in low or "real-model improvement" in low:
                assert "not" in low, (
                    f"{name}: affirmative improvement claim: {s[:160]}")
    manifest = _load(run_dir, "manifest.json")
    assert manifest["provider"].startswith("none")
    assert manifest["config_sha256"] and manifest["environment_sha256"]
    assert manifest["seeds"]["master"] == 20261024


def test_livelock_defect_disclosed_and_consistent(summary):
    assert any(d["id"] == "CEA-V2-D1" for d in summary["known_defects"])
    for g in REGIMES:
        s = summary["results"][g]["cea_v2"]
        assert s["terminated"] == LIVELOCK
        detail = s["termination_detail"]
        assert detail["unique_phenotypes"] > 16 - detail["n_offspring"]
        assert detail["at_episode_index"] == s["episodes_completed"]
        assert s["evolution_updates"] >= 1, "evolution must have run pre-livelock"


def test_infra_episodes_no_behavioral_update(episodes):
    """Infra outcomes must never produce a behavioral update, for any arm."""
    for r in episodes:
        if r["context"]["failure_kind"] == "budget_stop":
            assert r["reward"]["success"] is False
            assert r["reward"]["regret"] == 0.0
            if r["arm"] in CONTROLLER_ARMS and r["arm"] != "cea_v2_no_update":
                assert r["update_event"]["updated"] is False
    # full-horizon controller ablation must actually have seen infra episodes
    nv = [r for r in episodes if r["arm"] == "cea_v2_no_variation"
          and r["context"]["failure_kind"] == "budget_stop"]
    assert nv, "no_variation ablation saw no infra episodes"


# ------------------------------------------------------------- unit (in-proc)
def test_observation_changes_selection_after_shift():
    """After a reward shift, observing failures of the incumbent must change a
    later selection (the controller's reason for existing)."""
    ctl = OnlineEvolutionController(pareto_front_path=driver.FRONT,
                                    manifest_path=driver.MANIFEST)
    ctx = driver.context_for("tool", infra=False)
    sel0 = ctl.select(ctx, "u-0")
    for i in range(2):  # regime phase A: incumbent works
        ctl.observe(f"u-{i}", ctx, sel0["genome_id"],
                    {"success": True, "cost_cny": 0.0009, "calls": 4,
                     "failure_kind": "none"})
    sel1 = ctl.select(ctx, "u-2")
    assert sel1["genome_id"] == sel0["genome_id"], "success must reinforce"
    for i in range(2, 4):  # regime shift: the incumbent now fails
        ctl.observe(f"u-{i}", ctx, sel1["genome_id"],
                    {"success": False, "cost_cny": 0.0009, "calls": 4,
                     "failure_kind": "none"})
    sel2 = ctl.select(ctx, "u-4")
    assert sel2["genome_id"] != sel1["genome_id"], \
        "post-shift observations must change a later selection"


def test_duplicate_episode_rejected():
    ctl = OnlineEvolutionController(pareto_front_path=driver.FRONT,
                                    manifest_path=driver.MANIFEST)
    ctx = driver.context_for("tool", infra=False)
    sel = ctl.select(ctx, "dup-0")
    outcome = driver.env_outcome("stationary_contextual", 0, "tool",
                                 tuple(sel["phenotype"]))
    ctl.observe("dup-0", ctx, sel["genome_id"], outcome)
    with pytest.raises(OnlineEvolutionError):
        ctl.observe("dup-0", ctx, sel["genome_id"], outcome)


def test_no_update_ablation_keeps_population_version_zero():
    res = driver.run_arm("stationary_contextual", "cea_v2_no_update")
    s = res["summary"]
    assert s["final_population_version"] == 0
    assert s["evolution_updates"] == 0
    assert s["episodes_completed"] == s["episodes_total"]
    picks = {r["selected"]["genome_id"] for r in res["rows"]}
    assert len(picks) == 1, "no-update arm must freeze its selection"


def test_env_outcome_deterministic_and_consistent_envelope():
    a = driver.env_outcome("stationary_contextual", 0, "tool", (driver.T, driver.R, driver.B))
    b = driver.env_outcome("stationary_contextual", 0, "tool", (driver.T, driver.R, driver.B))
    assert a == b
    # same episode/context/phenotype => same outcome for every arm (shared stream)
    o1 = driver.oracle_score("abrupt_shift", 100, "tool")
    o2 = driver.oracle_score("abrupt_shift", 100, "tool")
    assert o1 == o2
    # the shift really flips the best phenotype for the tool context
    before = driver.oracle_score("abrupt_shift", 7, "tool")
    after = driver.oracle_score("abrupt_shift", 8, "tool")
    assert before != after
