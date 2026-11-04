Kimi Executor — start the CausalEvo-DSH fast-track experiment.

1. Re-query origin/main. Fix scripts/clean_clone_check.py::_remote_sha() to catch OSError and return None. Add a FileNotFoundError test proving main returns 3 and no temp directory, clone, venv or install occurs.
2. Do not wait for the final clean-clone gate to start R1.13-E0. Read planner/experiments/CE-DSH-P4-R1.13-FAST-CEA-MECHANISM.md.
3. Add tests for online_evolution.py bounded offspring generation, max population and deterministic replay.
4. Remove the obsolete episode-15 structural truncation guard in scripts/run_cea_v2_offline.py only after tests prove the current controller terminates. Keep a watchdog.
5. Run 10 deterministic seeds × 4 frozen regimes × 7 arms, full horizons. Include Random, Rule, Static Pareto, Frozen LinUCB, CEA-v2, no-variation and no-update. Record all metrics and actual NSGA-III parent/survivor calls. Save outputs only under results/phase4/r13-offline/.
6. If E0 passes, implement separate CCP-NSGA3 with per-context success/cost/call fitness and a matched random-parent ablation. Do not modify CEA-v2 in place. Use 10 screening seeds; only if promising, freeze and run 30 separate confirmation seeds.
7. Report negative results. Positive NSGA-III counters alone are not improvement evidence. Synthetic outputs are not real-agent efficacy.
8. No DeepSeek calls, no spend, no balance query, no live pilot/canary, no Phase 5. R1.12 CNY 2 budget is spent. Do not modify R1.12 raw data or Phase 0–3/R1.9 frozen artifacts.
9. Update executor report, status, latest plan and handoff before final exact-SHA clean-clone. Commit/push, verify main and clean worktree, run final gate, then stop for GPT Planner review. Do not self-accept.