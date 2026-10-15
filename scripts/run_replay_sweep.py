"""Phase 3.1 replay sweep: fill the complete reward matrix.

For every (case, task, intervention) in {3 cases} x {2 tasks} x {library}:
run the original tape once, then the transformed tape once, record the paired
outcome. All offline (container world + tape provider); zero API cost.

Output: results/phase3/replay_sweep/sweep_results.jsonl
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.counterfactual.replay import apply_tape_transform, run_single  # noqa: E402
from causalevo.eval.executor import DockerExecutor  # noqa: E402
from causalevo.eval.judge import Judge  # noqa: E402
from causalevo.eval.runtime_budget import RuntimeBudget  # noqa: E402
from causalevo.eval.scenarios import SCENARIOS, scenario_tape  # noqa: E402
from causalevo.eval.task_spec import load_all_tasks  # noqa: E402
from causalevo.eval.trace import provenance_block  # noqa: E402
from causalevo.eval.workspace_factory import WorkspaceFactory  # noqa: E402
from causalevo.failure_dataset.builder import SCENARIO_GROUND_TRUTH  # noqa: E402
from causalevo.intervention.generator import INTERVENTION_LIBRARY  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase3" / "replay_sweep"
IMAGE = "causalevo-dsh-agent:0.2.1"
PATCH = REPO / "configs" / "dsh_task_patch.yml"
CASES = ["bad_tool_blocks_write", "broken_write", "wrong_fix"]


def _budget() -> RuntimeBudget:
    return RuntimeBudget(max_provider_calls=8, max_total_output_tokens=4096,
                         max_tool_calls=12, wall_time_s=240)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    judge = Judge(DockerExecutor())
    specs = load_all_tasks(REPO / "benchmarks" / "tasks")[:2]
    rows = []
    for scenario in CASES:
        for spec in specs:
            tape = scenario_tape(spec, SCENARIOS[scenario], max_calls=12)
            factory = WorkspaceFactory()
            original = run_single(spec, tape, _budget(), image=IMAGE, patch_path=PATCH,
                                  network="ceval-net", judge=judge, factory=factory,
                                  run_tag=f"sw-{scenario[:12]}-{spec.task_id}-o")
            factory.destroy_all()
            for iv in INTERVENTION_LIBRARY:
                cf_tape, changes = apply_tape_transform(
                    tape, iv.tape_transform, entry_file=spec.entry_file,
                    fixed_content=spec.reference_fixed.read_text(encoding="utf-8"))
                factory = WorkspaceFactory()
                cfx = run_single(spec, cf_tape, _budget(), image=IMAGE, patch_path=PATCH,
                                 network="ceval-net", judge=judge, factory=factory,
                                 run_tag=f"sw-{iv.stable_id()}")
                factory.destroy_all()
                rows.append({
                    "scenario": scenario,
                    "true_failure": SCENARIO_GROUND_TRUTH[scenario],
                    "task_id": spec.task_id,
                    "task_split": spec.split,
                    "intervention_id": iv.intervention_id,
                    "tape_transform": iv.tape_transform,
                    "original_success": original["success"],
                    "cf_success": cfx["success"],
                    "success_delta": int(cfx["success"]) - int(original["success"]),
                    "original_ledger": original["ledger"],
                    "cf_ledger": cfx["ledger"],
                    "cost_delta_cny": round(
                        cfx["ledger"]["known_cost_cny"] - original["ledger"]["known_cost_cny"], 10),
                    "changed_steps": changes,
                })
                print(f"{scenario} {spec.task_id} {iv.intervention_id}: "
                          f"{original['success']} -> {cfx['success']}", flush=True)
    with (OUT / "sweep_results.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    (OUT / "manifest.json").write_text(json.dumps({
        "created_by": "scripts/run_replay_sweep.py",
        "cases": CASES, "tasks": [s.task_id for s in specs],
        "interventions": [i.intervention_id for i in INTERVENTION_LIBRARY],
        "rows": len(rows), "provenance": provenance_block(),
        "honesty": "tape-transform simulated mechanisms; zero API spend; not real-model evidence",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("rows:", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
