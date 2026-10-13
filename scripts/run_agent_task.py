"""Run Phase 1 agent tasks through the containerized Harness bridge.

Default is --fake: a protocol-level fake provider, offline, zero cost.
--live is hard-gated: it requires DEEPSEEK_API_KEY plus the one-off Planner
authorization CE_DSH_LIVE_AUTH=phase1-pilot; without it the CLI refuses
before any socket is opened.

Usage:
  .venv/Scripts/python.exe scripts/run_agent_task.py --fake --scenario noop
  .venv/Scripts/python.exe scripts/run_agent_task.py --live   # refused without auth
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.eval.agent_pipeline import run_agent_tasks  # noqa: E402
from causalevo.eval.executor import DockerExecutor  # noqa: E402
from causalevo.eval.fake_provider import FakeProvider  # noqa: E402
from causalevo.eval.harness_agent import (  # noqa: E402
    ContainerHarnessRunner,
    require_live_authorization,
)
from causalevo.eval.judge import Judge  # noqa: E402
from causalevo.eval.policy import B0, B1, POLICIES  # noqa: E402
from causalevo.eval.runtime_budget import RuntimeBudget  # noqa: E402
from causalevo.eval.task_spec import load_all_tasks  # noqa: E402
from causalevo.eval.scenarios import SCENARIOS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fake", action="store_true", help="offline fake provider (default)")
    mode.add_argument("--live", action="store_true", help="real API; requires one-off authorization")
    parser.add_argument("--scenario", default="noop", choices=sorted(SCENARIOS))
    parser.add_argument("--policy", default="B0-fixed-harness", choices=sorted(POLICIES))
    parser.add_argument("--tasks", type=int, default=None, help="limit number of tasks")
    parser.add_argument("--split", default=None, choices=["train", "dev", "sealed_test"])
    parser.add_argument("--out", default=str(REPO_ROOT / "results" / "phase1" / "r2-offline"))
    args = parser.parse_args()

    specs = load_all_tasks(REPO_ROOT / "benchmarks" / "tasks")
    if args.split:
        specs = [s for s in specs if s.split == args.split]
    if args.tasks:
        specs = specs[: args.tasks]
    policy = POLICIES[args.policy]

    def budget_factory() -> RuntimeBudget:
        return RuntimeBudget(
            max_provider_calls=policy.budget.max_provider_calls,
            max_total_output_tokens=policy.budget.max_total_output_tokens,
            max_tool_calls=policy.budget.max_tool_calls,
            wall_time_s=policy.budget.wall_time_s,
        )

    if args.live:
        require_live_authorization()  # refuses unless explicitly authorized
        print("live mode is not scheduled in CE-DSH-P1-R2; aborting.")
        return 2

    judge_executor = DockerExecutor()
    judge = Judge(judge_executor)
    scenario_factory = SCENARIOS[args.scenario]

    def provider_factory(spec):
        return FakeProvider(scenario_factory(spec))

    result = run_agent_tasks(
        specs, policy, judge, judge_executor,
        Path(args.out),
        provider_factory=provider_factory,
        budget_factory=budget_factory,
        image="causalevo-dsh-agent:0.1.0",
        patch_path=REPO_ROOT / "configs" / "dsh_task_patch.yml",
        provider_kind="fake",
        split_seed=20261010,
        config={"scenario": args.scenario, "policy": args.policy,
                "split": args.split or "all", "tasks": len(specs)},
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
    print("run_dir:", result["run_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
