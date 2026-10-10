#!/usr/bin/env python3
"""Phase 0 cache benchmark CLI.

Default is --dry-run (offline fake provider, zero cost, no key needed).
--live is an explicit opt-in: it requires DEEPSEEK_API_KEY in the environment,
boots DeepSeek Harness with the no-tools patch profile, and enforces the CNY
budget gate before every single call.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.benchmark import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    Benchmark,
    load_config,
    require_live_key,
)
from causalevo.runner import FakeRunner, HarnessRunner  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATCH = REPO_ROOT / "configs" / "dsh_bench_patch.yml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="offline fake provider (default)")
    mode.add_argument("--live", action="store_true", help="real DeepSeek API via DeepSeek Harness")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--calls", type=int, default=None, help="override calls per group")
    parser.add_argument("--max-cny", type=float, default=None, help="override budget cap (CNY)")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)

    live = bool(args.live)
    config = load_config(args.config)
    if args.calls is not None:
        if args.calls < 1:
            parser.error("--calls must be >= 1")
        object.__setattr__(config, "calls_per_group", args.calls)
    if args.max_cny is not None:
        if args.max_cny <= 0:
            parser.error("--max-cny must be positive")
        object.__setattr__(config, "max_cny", args.max_cny)

    run_id = args.run_id or uuid.uuid4().hex[:8]
    output_dir = args.output_dir or (REPO_ROOT / "results" / "phase0" / ("live" if live else "dry-run"))

    if live:
        require_live_key()
        balance_before = None
        try:
            from causalevo.balance import query_balance_cny

            balance_before = query_balance_cny(os.environ["DEEPSEEK_API_KEY"])
            print(f"platform balance before run: {balance_before:.2f} CNY")
            if balance_before < config.max_cny:
                print(
                    f"note: platform balance {balance_before:.2f} CNY is below the "
                    f"authorized cap {config.max_cny:.2f} CNY; effective cap tightened to balance"
                )
                object.__setattr__(config, "max_cny", balance_before)
        except Exception as exc:
            print(f"WARNING: balance preflight failed ({type(exc).__name__}: {exc}); "
                  "continuing with configured cap only (reconciliation unavailable)")
        dsh_home = output_dir / "dsh_home"
        workspace = output_dir / "workspace"
        dsh_home.mkdir(parents=True, exist_ok=True)
        workspace.mkdir(parents=True, exist_ok=True)
        runner = HarnessRunner(
            dsh_home=str(dsh_home),
            workspace=str(workspace),
            patch_path=str(DEFAULT_PATCH),
            model=config.model,
            reasoning_effort=config.reasoning_effort,
            max_tokens=config.max_tokens,
        )
    else:
        runner = FakeRunner()

    bench = Benchmark(config=config, runner=runner, output_dir=output_dir, run_id=run_id, live=live)
    preflight = bench.preflight()
    print("=== Phase 0 cache benchmark preflight ===")
    print(json.dumps(preflight, indent=2, ensure_ascii=False))
    if live and not preflight["budget_ok"]:
        print("REFUSING: worst-case total exceeds budget cap; no live call was made.")
        return 2

    summary = bench.run()
    if live and balance_before is not None:
        try:
            from causalevo.balance import query_balance_cny

            balance_after = query_balance_cny(os.environ["DEEPSEEK_API_KEY"])
            summary["balance_reconciliation"] = {
                "balance_before_cny": balance_before,
                "balance_after_cny": balance_after,
                "billed_delta_cny": round(balance_before - balance_after, 6),
                "note": "platform-billed delta in CNY (ground truth; billing may lag)",
            }
            (output_dir / "summary.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            summary["balance_reconciliation"] = {"error": f"{type(exc).__name__}: {exc}"}
    print("=== summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"evidence written to: {output_dir}")
    return 0 if summary["aborted_reason"] is None else 3


if __name__ == "__main__":
    raise SystemExit(main())
