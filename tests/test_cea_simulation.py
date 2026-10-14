"""CEA simulation artifact tests (P3.1-S4/S5/S7)."""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase3" / "cea"
SWEEP = REPO / "results" / "phase3" / "replay_sweep" / "sweep_results.jsonl"


def test_sweep_matrix_complete():
    rows = [json.loads(l) for l in SWEEP.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 42  # 3 cases x 2 tasks x 7 interventions
    keys = {(r["scenario"], r["task_id"], r["intervention_id"]) for r in rows}
    assert len(keys) == 42


def test_cea_artifacts_exist():
    for name in ("algorithm_config.json", "episode_history.jsonl",
                 "baseline_results.json", "learning_curve.json",
                 "ablation_results.json"):
        assert (OUT / name).is_file(), name


def test_episode_history_schema_and_order():
    rows = [json.loads(l) for l in (OUT / "episode_history.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows
    ids = [r["episode_id"] for r in rows]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    for r in rows:
        assert {"episode_id", "failure_state", "candidate_actions",
                "selected_action", "reward", "update"} <= set(r)


def test_eval_episodes_never_update():
    rows = [json.loads(l) for l in (OUT / "episode_history.jsonl").read_text(encoding="utf-8").splitlines()]
    eval_rows = [r for r in rows if r.get("update") == "eval-no-update"]
    train_rows = [r for r in rows if r.get("update") != "eval-no-update"]
    assert eval_rows and train_rows
    assert min(r["episode_id"] for r in eval_rows) > max(r["episode_id"] for r in train_rows)


def test_baseline_results_fields():
    res = json.loads((OUT / "baseline_results.json").read_text(encoding="utf-8"))
    assert {"B0-random", "B1-rule", "B2-cea-v0"} <= set(res["results"])
    for arm in res["results"].values():
        assert {"n_eval", "top1_accuracy", "successful_intervention_rate",
                "mean_eval_reward", "mean_eval_regret", "cum_reward_all"} <= set(arm)


def test_learning_curve_monotone_episodes():
    curves = json.loads((OUT / "learning_curve.json").read_text(encoding="utf-8"))
    for arm, pts in curves.items():
        ids = [p["episode_id"] for p in pts]
        assert ids == sorted(ids)


def test_ablation_arms_present():
    abl = json.loads((OUT / "ablation_results.json").read_text(encoding="utf-8"))
    assert {"A1_no_history", "A2_with_history",
            "A3_plain_outcome_reward", "A4_causal_reward"} <= set(abl)


def test_simulation_reproducible(tmp_path):
    before = json.loads((OUT / "baseline_results.json").read_text(encoding="utf-8"))
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "run_cea_simulation.py"),
                           "--out", str(tmp_path)],
                          capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr[-400:]
    after = json.loads((tmp_path / "baseline_results.json").read_text(encoding="utf-8"))
    assert before["results"]["B2-cea-v0"]["mean_eval_reward"] == \
        after["results"]["B2-cea-v0"]["mean_eval_reward"]
