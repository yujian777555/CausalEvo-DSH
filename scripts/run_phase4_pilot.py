"""Phase 4 pilot driver. --dry-run (default, fake tape, zero cost) | --live
(double-gated: DEEPSEEK_API_KEY + CE_DSH_LIVE_AUTH=phase1-pilot + budget cap).

Writes results/phase4/<mode>/<run_id>/{tasks.jsonl, manifest.json}.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from causalevo.budget import BudgetGate  # noqa: E402
from causalevo.eval.executor import DockerExecutor  # noqa: E402
from causalevo.eval.harness_agent import (  # noqa: E402
    ContainerHarnessRunner,
    require_live_authorization,
)
from causalevo.eval.judge import Judge  # noqa: E402
from causalevo.eval.live_pilot import ARMS, run_task_arm, set_api_key  # noqa: E402
from causalevo.eval.networks import ProviderContainer  # noqa: E402
from causalevo.eval.task_spec import load_all_tasks  # noqa: E402
from causalevo.eval.trace import new_run_id, provenance_block  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
IMAGE = "causalevo-dsh-agent:0.2.1"
PATCH = REPO / "configs" / "dsh_task_patch.yml"
SEEDS = [20261014, 20261015]
BUDGET_CAP_CNY = 3.00

WRONG = "def _wrong():\n    return None\n"


def _attempt_tape(spec, attempt: int):
    """Dry-run tapes: attempt 0 writes a wrong fix; attempt 1 writes the
    reference fix (simulating a successful intervention)."""
    fixed = spec.reference_fixed.read_text(encoding="utf-8")
    content = fixed if attempt == 1 else (
        f"def {spec.function}(*a, **k):\n    return None\n")
    return {str(i): a for i, a in enumerate([
        [["tool_call", "read", {"file_path": spec.entry_file}]],
        [["tool_call", "write", {"file_path": spec.entry_file, "content": content}]],
        [["text", "done"]],
    ])}


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--tasks", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    live = bool(args.live)

    specs = load_all_tasks(REPO / "benchmarks" / "tasks")
    if args.tasks:
        specs = specs[: args.tasks]

    providers: list = []
    provider_holder: dict = {}

    def make_runner(attempt: int) -> ContainerHarnessRunner:
        if live:
            return ContainerHarnessRunner(
                image=IMAGE, patch_path=PATCH, model="deepseek-flash",
                reasoning_effort="low", max_tokens=256, provider_kind="live",
                provider_endpoint=None, network="bridge")
        tape = _attempt_tape(_current_spec[0], attempt)
        provider = ProviderContainer(tape)
        provider.__enter__()
        providers.append(provider)
        return ContainerHarnessRunner(
            image=IMAGE, patch_path=PATCH, model="deepseek-flash",
            reasoning_effort="low", max_tokens=256, provider_kind="fake",
            provider_endpoint=provider.endpoint, network="ceval-net")

    if live:
        require_live_authorization()
        from causalevo.balance import query_balance_cny
        import os
        key = os.environ["DEEPSEEK_API_KEY"]
        set_api_key(key)
        balance = query_balance_cny(key)
        cap = min(BUDGET_CAP_CNY, balance)
        print(f"live pilot: balance={balance:.2f} cap={cap:.2f}")
    else:
        set_api_key("sk-fake-offline-no-cost")
        cap = BUDGET_CAP_CNY

    gate = BudgetGate(cap_cny=cap, worst_case_per_call_cny=0.02)
    judge = Judge(DockerExecutor())
    run_id = f"phase4-{'live' if live else 'dry'}-{new_run_id()}"
    out_dir = Path(args.out) if args.out else REPO / "results" / "phase4" / ("live" if live else "dry-run")
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    aborted = None
    _current_spec = [None]
    try:
        for seed in SEEDS:
            rng = np.random.default_rng(seed)
            for spec in specs:
                _current_spec[0] = spec
                for arm in ARMS:
                    try:
                        gate.check_can_start(1)
                    except Exception as exc:
                        aborted = f"budget gate: {exc}"
                        break
                    res = run_task_arm(spec, arm, seed, judge, run_id,
                                       rng=rng, gate=gate, make_runner=make_runner)
                    rows.append(res.as_dict())
                    with (run_dir / "tasks.jsonl").open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(res.as_dict(), ensure_ascii=False) + "\n")
                    print(f"{seed} {spec.task_id} {arm}: a1={res.attempt1_success} "
                              f"final={res.final_success} cost={res.cost_cny}", flush=True)
                    if res.abort_reason:
                        aborted = f"fail-closed at {spec.task_id}/{arm}: {res.abort_reason}"
                        break
                if aborted:
                    break
            if aborted:
                break
    finally:
        for p in providers:
            try:
                p.__exit__(None, None, None)
            except Exception:
                pass

    manifest = {
        "run_id": run_id, "live": live, "seeds": SEEDS, "arms": ARMS,
        "task_count": len(specs), "rows": len(rows),
        "budget_cap_cny": cap, "spent_cny": gate.spent_cny,
        "aborted": aborted,
        "provenance": provenance_block(),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    print(f"rows={len(rows)} spent={gate.spent_cny:.4f} aborted={aborted}")
    print("run_dir:", run_dir)
    return 0 if aborted is None else 3


if __name__ == "__main__":
    raise SystemExit(main())
