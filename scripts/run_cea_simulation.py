"""Phase 3.1 offline evolution simulation (CEA-v0).

Episodes = (scenario, task) failure states repeated over rounds, strictly
time-ordered. Rewards come ONLY from the replay sweep matrix (measured
success_delta - lambda*cost_delta), never from model output.

Arms: B0 random, B1 rule, B2 LinUCB. Ablations: A1/A2 history features,
A3 plain outcome reward vs A4 causal delta reward. Time split: early rounds
train, late rounds evaluated without updates.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from causalevo.evolution.controller import CausalEvolutionController  # noqa: E402
from causalevo.evolution.memory import Episode, EpisodeMemory  # noqa: E402
from causalevo.evolution.policy import ACTIONS, LinUCBPolicy, RandomPolicy, RulePolicy  # noqa: E402
from causalevo.evolution.reward import DEFAULT_LAMBDA, compute_reward  # noqa: E402
from causalevo.eval.trace import provenance_block  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SWEEP = REPO / "results" / "phase3" / "replay_sweep" / "sweep_results.jsonl"
OUT = REPO / "results" / "phase3" / "cea"
SEED = 20261014
ROUNDS = 10
TRAIN_ROUNDS = 7  # time split: rounds >= TRAIN_ROUNDS are eval-only


def load_matrix():
    rows = [json.loads(l) for l in SWEEP.read_text(encoding="utf-8").splitlines()]
    matrix = {}
    for r in rows:
        matrix[(r["scenario"], r["task_id"], r["intervention_id"])] = r
    return matrix, rows


def failure_state(row):
    return {"failure_type": row["true_failure"],
            "prompt_chars": len(row.get("task_id", "")) * 10,  # coarse proxy, fixed
            "n_visible_checks": 3}


def run_arm(policy, episodes, matrix, *, causal_reward: bool, oracle):
    ctl = CausalEvolutionController(policy, EpisodeMemory())
    history = []
    cum_reward = 0.0
    cum_regret = 0.0
    curve = []
    eval_stats = {"n": 0, "top1": 0, "success": 0, "reward": 0.0, "regret": 0.0}
    for ep in episodes:
        state = failure_state(ep["state_row"])
        candidates = list(ACTIONS)
        sel = ctl.select_intervention(state, candidates)
        action = sel["selected_action"]
        row = matrix[(ep["scenario"], ep["task_id"], action)]
        if causal_reward:
            reward = compute_reward(row["success_delta"], row["cost_delta_cny"], DEFAULT_LAMBDA)
        else:
            reward = float(row["cf_success"])  # plain outcome, no causal delta
        best = oracle[(ep["scenario"], ep["task_id"])]
        is_eval = ep["round"] >= TRAIN_ROUNDS
        if not is_eval:
            ctl.record_and_update(ep["episode_id"], state, candidates, action, reward,
                                  update_note="train")
        else:
            # eval window: episode is recorded (auditable) but the policy is
            # NOT updated — time-split generalization
            ctl.memory.append(Episode(ep["episode_id"], state, candidates, action, reward,
                                      "eval-no-update"))
        cum_reward += reward
        cum_regret += best - reward
        curve.append({"episode_id": ep["episode_id"], "round": ep["round"],
                      "reward": reward, "cum_reward": cum_reward,
                      "cum_regret": cum_regret, "eval": is_eval,
                      "policy_version": sel["policy_version"]})
        if is_eval:
            eval_stats["n"] += 1
            eval_stats["top1"] += int(action == ep["oracle_action"])
            eval_stats["success"] += int(row["success_delta"] > 0)
            eval_stats["reward"] += reward
            eval_stats["regret"] += best - reward
        history.append({
            "episode_id": ep["episode_id"], "round": ep["round"],
            "failure_state": state, "candidate_actions": candidates,
            "selected_action": action, "reward": reward,
            "update": "eval-no-update" if is_eval else "applied",
            "policy_version": sel["policy_version"],
        })
    n = eval_stats["n"]
    return history, curve, {
        "n_eval": n,
        "top1_accuracy": eval_stats["top1"] / n if n else None,
        "successful_intervention_rate": eval_stats["success"] / n if n else None,
        "mean_eval_reward": eval_stats["reward"] / n if n else None,
        "mean_eval_regret": eval_stats["regret"] / n if n else None,
        "cum_reward_all": cum_reward,
    }


def main(out_dir: Path | None = None) -> int:
    global OUT
    if out_dir is not None:
        OUT = Path(out_dir)
    OUT.mkdir(parents=True, exist_ok=True)
    matrix, rows = load_matrix()
    states = sorted({(r["scenario"], r["task_id"]) for r in rows})
    oracle: dict = {}
    oracle_action: dict = {}
    for key in states:
        best_id, best_r = max(
            ((a, compute_reward(matrix[(key[0], key[1], a)]["success_delta"],
                                  matrix[(key[0], key[1], a)]["cost_delta_cny"], DEFAULT_LAMBDA))
             for a in ACTIONS),
            key=lambda t: t[1])
        oracle[key] = best_r
        oracle_action[key] = best_id

    episodes = []
    eid = 0
    for rnd in range(ROUNDS):
        for key in states:
            state_row = next(r for r in rows if (r["scenario"], r["task_id"]) == key)
            episodes.append({"episode_id": eid, "round": rnd, "scenario": key[0],
                             "task_id": key[1], "state_row": state_row,
                             "oracle_action": oracle_action[key]})
            eid += 1

    arms = {
        "B0-random": (RandomPolicy(SEED), True),
        "B1-rule": (RulePolicy(), True),
        "B2-cea-v0": (LinUCBPolicy(alpha=0.5), True),
    }
    histories = {}
    results = {}
    curves = {}
    for name, (policy, causal) in arms.items():
        h, c, res = run_arm(policy, episodes, matrix, causal_reward=causal, oracle=oracle)
        histories[name] = h
        results[name] = res
        curves[name] = c

    # Ablations (all LinUCB): A1 no-history vs A2 history; A3 plain vs A4 causal
    abl = {}
    h, _, res = run_arm(LinUCBPolicy(alpha=0.5, use_history=False), episodes, matrix,
                        causal_reward=True, oracle=oracle)
    abl["A1_no_history"] = res
    h, _, res = run_arm(LinUCBPolicy(alpha=0.5, use_history=True), episodes, matrix,
                        causal_reward=True, oracle=oracle)
    abl["A2_with_history"] = res
    h, _, res = run_arm(LinUCBPolicy(alpha=0.5), episodes, matrix,
                        causal_reward=False, oracle=oracle)
    abl["A3_plain_outcome_reward"] = res
    h, _, res = run_arm(LinUCBPolicy(alpha=0.5), episodes, matrix,
                        causal_reward=True, oracle=oracle)
    abl["A4_causal_reward"] = res

    with (OUT / "episode_history.jsonl").open("w", encoding="utf-8") as fh:
        for h in histories["B2-cea-v0"]:
            fh.write(json.dumps(h, ensure_ascii=False, sort_keys=True) + "\n")
    (OUT / "learning_curve.json").write_text(json.dumps(curves, indent=1), encoding="utf-8")
    (OUT / "baseline_results.json").write_text(json.dumps({
        "seed": SEED, "rounds": ROUNDS, "train_rounds": TRAIN_ROUNDS,
        "lambda_cny": DEFAULT_LAMBDA, "results": results,
        "note": "rewards from replay sweep matrix (simulated interventions); not real-model evidence",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "ablation_results.json").write_text(json.dumps(abl, indent=2), encoding="utf-8")
    (OUT / "algorithm_config.json").write_text(json.dumps({
        "algorithm": "CEA-v0 disjoint LinUCB", "alpha": 0.5, "actions": ACTIONS,
        "state_layout": "onehot(failure_type=7) + prompt_chars/2000 + n_visible/10 (+history rates in A2)",
        "reward": "success_delta - lambda*max(0,cost_delta_cny)",
        "seed": SEED, "provenance": provenance_block(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v["mean_eval_reward"] for k, v in results.items()}, indent=1))
    print(json.dumps({k: v["mean_eval_reward"] for k, v in abl.items()}, indent=1))
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    raise SystemExit(main(Path(args.out) if args.out else None))
