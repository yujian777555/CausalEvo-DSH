# CausalEvo-DSH Handoff — R1.12 closeout + R1.13 offline experiment

Repository: yujian777555/CausalEvo-DSH, branch main. Re-query current origin/main at session start. Role protocol: GPT Planner → Kimi Executor → GPT Planner review. Do not mix other projects.

## Current status
R1.12 FIX5 remains REQUEST_CHANGES for one narrow issue: scripts/clean_clone_check.py::_remote_sha() must catch OSError (including FileNotFoundError), return None, and cause main() to return 3 before any temp-dir/clone/install side effects. FIX5 symlink classification and Holm primary exclusion passed Planner source review. Executor-reported FIX5 tests: 687 passed/1 skipped full; 46 passed/1 skipped focused. Planner did not rerun; GitHub check-runs were 0.

## User priority
User requested faster experimental progress. GPT authorizes immediate offline-only R1.13-E0; do not wait for the R1.12 final clean-clone gate to start simulation.

## Why
R1.12 had 5 behavioral observations, one evolve event, and zero NSGA-III parent/survivor calls. At the first evolve there were four measured candidates and n_parents=4, so all four passed through without NSGA-III. The fifth observation did not trigger the next evolve. Do not claim live NSGA-III was tested.

## Next work
Read planner/latest_plan.md and planner/experiments/CE-DSH-P4-R1.13-FAST-CEA-MECHANISM.md. The executor prompt is planner/experiments/CE-DSH-P4-R1.13-EXECUTOR-PROMPT.md.

E0: 10 seeds × 4 regimes × 7 arms, full horizons; remove the obsolete episode-15 structural truncation guard only after tests prove the current bounded controller terminates. Preserve a watchdog, test population cap and deterministic replay. Save outputs under results/phase4/r13-offline/ and label synthetic_mechanism_test.

E1: if E0 passes, implement a separate CCP-NSGA3 context-conditioned Pareto variant and matched random-parent ablation. Use 10 screening seeds and, if promising, 30 separate confirmation seeds. Do not change CEA-v2 in place. If it does not beat random-parent, report failure.

## Authorization
Offline CPU simulation only; DeepSeek calls=0, new spend=CNY 0, no balance query, no live pilot/canary, no Phase 5. R1.12 CNY 2 budget is spent. Future live validation requires separate explicit budget authorization. Do not modify R1.12 raw data or Phase 0–3/R1.9 frozen artifacts.

## Final gate
All tracked changes before exact-final-SHA clean-clone. No tracked edits after the gate. Report raw commands/output and stop for GPT Planner review; do not self-accept.
