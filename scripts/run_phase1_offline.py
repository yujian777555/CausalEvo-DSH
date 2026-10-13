"""Run the Phase 1 offline pipeline: all microtasks x B0/B1.

Usage: .venv/Scripts/python.exe scripts/run_phase1_offline.py [--mode noop|oracle|break] [--executor docker|local]
Offline only; no API calls; fake agent outcomes are pipeline evidence, not
model performance.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from causalevo.eval.executor import DockerExecutor, LocalTrustedExecutor  # noqa: E402
from causalevo.eval.judge import Judge  # noqa: E402
from causalevo.eval.pipeline import run_offline  # noqa: E402
from causalevo.eval.policy import B0, B1, check_budget_parity  # noqa: E402
from causalevo.eval.task_spec import load_all_tasks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="noop", choices=["noop", "oracle", "break"])
    parser.add_argument("--executor", default="docker", choices=["docker", "local"])
    parser.add_argument("--out", default=str(REPO_ROOT / "results" / "phase1" / "offline"))
    args = parser.parse_args()

    specs = load_all_tasks(REPO_ROOT / "benchmarks" / "tasks")
    check_budget_parity(B0, B1)
    executor = DockerExecutor() if args.executor == "docker" else LocalTrustedExecutor.for_trusted_content()
    judge = Judge(executor)
    out_dir = Path(args.out)

    for policy in (B0, B1):
        cfg = yaml.safe_load(
            (REPO_ROOT / "configs" / f"phase1_{'b0' if policy is B0 else 'b1'}.yaml")
            .read_text(encoding="utf-8"))
        result = run_offline(
            specs, policy, judge, executor, out_dir,
            fake_mode=args.mode,
            split_seed=20261010,
            config=cfg,
        )
        print(policy.policy_id, json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
