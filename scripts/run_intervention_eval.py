"""Phase 2.3 counterfactual intervention evaluation (offline, zero API).

Case matrix (2 tasks each, docker container world, fake provider tapes):
- case_tool: scenario bad_tool_blocks_write (tool_failure) — intervention
  replaces the unknown tool with the mandatory read, unblocking the write.
- case_verification: scenario broken_write (verification_failure) —
  intervention appends read-back + corrected write.
- case_ineffective: scenario wrong_fix (knowledge_failure) + STRATEGY
  intervention that changes nothing — expected no improvement (control).

Arms per case: B0 identity, B1 random (seeded), B2 rule (failure->default),
B3 diagnosis-guided (rule diagnoser -> generator).
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.counterfactual.replay import (  # noqa: E402
    apply_tape_transform,
    replay_pair,
    run_single,
)
from causalevo.diagnosis.models import RuleDiagnoser  # noqa: E402
from causalevo.eval.executor import DockerExecutor  # noqa: E402
from causalevo.eval.judge import Judge  # noqa: E402
from causalevo.eval.runtime_budget import RuntimeBudget  # noqa: E402
from causalevo.eval.scenarios import SCENARIOS, scenario_tape  # noqa: E402
from causalevo.eval.task_spec import load_all_tasks  # noqa: E402
from causalevo.eval.trace import provenance_block  # noqa: E402
from causalevo.eval.workspace_factory import WorkspaceFactory  # noqa: E402
from causalevo.failure_dataset.builder import SCENARIO_GROUND_TRUTH  # noqa: E402
from causalevo.intervention.generator import (  # noqa: E402
    INTERVENTION_LIBRARY,
    NO_INTERVENTION,
    generate_intervention,
)

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase2" / "intervention"
IMAGE = "causalevo-dsh-agent:0.2.0"
PATCH = REPO / "configs" / "dsh_task_patch.yml"
NETWORK = "ceval-net"

CASES = [
    ("case_tool", "bad_tool_blocks_write"),
    ("case_verification", "broken_write"),
    ("case_ineffective", "wrong_fix"),
]

# Control case design: every non-B0 arm receives the SAME deliberately
# mismatched intervention (strategy intervention against a knowledge
# failure). Its transform is a no-op on this tape, so any improvement would
# disprove the control.
MISMATCHED_CONTROL = next(i for i in INTERVENTION_LIBRARY if i.target_failure == "strategy_failure")


def _budget() -> RuntimeBudget:
    # replay envelope (recorded; separate from the frozen B0/B1 agent envelope
    # and identical across all four arms within each case)
    return RuntimeBudget(max_provider_calls=8, max_total_output_tokens=4096,
                         max_tool_calls=12, wall_time_s=240)


def _pseudo_trace(spec, arm_result) -> dict:
    return {
        "trace_id": "replay", "task_id": spec.task_id, "run_id": "cf",
        "states": {
            "visible_tests_passed": arm_result["judge"]["visible"],
            "sealed_tests_passed": arm_result["judge"]["sealed"],
            "invalid": arm_result["judge"]["invalid"],
            "timeout": arm_result["outcome_kind"] == "timeout",
            "budget_stop": arm_result["outcome_kind"] in ("budget_stop", "unknown_cost"),
        },
        "agent": {"failure_kind": arm_result["outcome_kind"],
                  "ledger": arm_result["ledger"],
                  "events_slim": arm_result["events_slim"]},
        "judge": {"invalid_reason": "x" if arm_result["judge"]["invalid"] else None,
                  "visible_passed": arm_result["judge"]["visible"]},
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    judge = Judge(DockerExecutor())
    specs = load_all_tasks(REPO / "benchmarks" / "tasks")[:2]
    rng = random.Random(20261014)
    results = []

    for case_id, scenario in CASES:
        true_failure = SCENARIO_GROUND_TRUTH[scenario]
        is_control = case_id == "case_ineffective"
        for spec in specs:
            tape = scenario_tape(spec, SCENARIOS[scenario], max_calls=12)
            arms: dict[str, object] = {}
            arms["B0-no-intervention"] = NO_INTERVENTION
            arms["B1-random"] = rng.choice(
                [i for i in INTERVENTION_LIBRARY if i.tape_transform != "identity"])
            # B2: rule mapping from the KNOWN injected failure type
            from causalevo.diagnosis.models import DiagnosisResult
            arms["B2-rule"] = generate_intervention(DiagnosisResult(
                trace_id=spec.task_id, failure_type=true_failure, evidence=[],
                confidence=0.9, abstained=False, model="ground-truth"))
            # B3: diagnosis-guided — run original, diagnose, then intervene
            factory = WorkspaceFactory()
            orig = run_single(spec, tape, _budget(), image=IMAGE, patch_path=PATCH,
                              network=NETWORK, judge=judge, factory=factory,
                              run_tag=case_id + "-b3-diag")
            factory.destroy_all()
            diagnosis = RuleDiagnoser().diagnose(_pseudo_trace(spec, orig))
            arms["B3-diagnosis-guided"] = generate_intervention(diagnosis)
            if is_control:
                # control case: all non-B0 arms get the mismatched intervention
                arms["B1-random"] = MISMATCHED_CONTROL
                arms["B2-rule"] = MISMATCHED_CONTROL
                arms["B3-diagnosis-guided"] = MISMATCHED_CONTROL

            for arm_name, intervention in arms.items():
                res = replay_pair(
                    spec, tape, intervention, scenario=scenario, baseline=arm_name,
                    image=IMAGE, patch_path=PATCH, network=NETWORK,
                    budget=_budget(), judge=judge,
                    case_id=f"{case_id}--{spec.task_id}--{arm_name}")
                res.intervention["diagnosed_failure"] = (
                    diagnosis.failure_type if arm_name == "B3-diagnosis-guided" else None)
                results.append(res)
                print(f"{case_id} {arm_name}: {res.original_success} -> {res.counterfactual_success}")

    with (OUT / "counterfactual_results.jsonl").open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(r.to_jsonl() + "\n")

    comparison = _baseline_comparison(results)
    (OUT / "baseline_comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "sample_cases.json").write_text(
        json.dumps([r.as_dict() for r in results[:4]], indent=2, ensure_ascii=False),
        encoding="utf-8")
    (OUT / "intervention_manifest.json").write_text(json.dumps({
        "created_by": "scripts/run_intervention_eval.py",
        "cases": [c[0] for c in CASES],
        "arms": ["B0-no-intervention", "B1-random", "B2-rule", "B3-diagnosis-guided"],
        "replay_budget_envelope": _budget().snapshot() | {"note": "identical across arms; separate from frozen B0/B1 agent envelope"},
        "provenance": provenance_block(),
        "honesty": "tape-transform simulated interventions; NOT evidence of real-model improvement",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(comparison["per_arm"], indent=1))
    return 0


def _baseline_comparison(results):
    per_arm: dict = {}
    for r in results:
        arm = per_arm.setdefault(r.baseline, {"cases": 0, "improved": 0, "no_change": 0,
                                              "regressed": 0, "cost_delta_cny": 0.0})
        arm["cases"] += 1
        if r.success_delta > 0:
            arm["improved"] += 1
        elif r.success_delta < 0:
            arm["regressed"] += 1
        else:
            arm["no_change"] += 1
        arm["cost_delta_cny"] += r.cost_delta_cny
    n_cases = len({r.case_id.split("--")[0] for r in results})
    orig_success = sum(1 for r in results if r.baseline == "B0-no-intervention"
                       and r.original_success)
    intervened = [r for r in results if r.baseline != "B0-no-intervention"]
    gain = None
    if intervened:
        p_int = sum(1 for r in intervened if r.counterfactual_success) / len(intervened)
        p_orig = sum(1 for r in intervened if r.original_success) / len(intervened)
        gain = p_int - p_orig
    return {
        "n_case_instances": len(results),
        "n_cases": n_cases,
        "original_success_rate_B0": orig_success / max(1, sum(1 for r in results if r.baseline == "B0-no-intervention")),
        "intervention_gain": gain,
        "per_arm": per_arm,
        "note": "transform-simulated effects; paired comparison; NOT real-model evidence",
    }


if __name__ == "__main__":
    raise SystemExit(main())
